import asyncio
import time
import traceback
from datetime import datetime, timedelta
from threading import Thread
from typing import Dict

from config import settings
from services.exnova_service import AsyncExnovaService
from services.supabase_service import SupabaseService
from analysis.strategy import STRATEGIES
from analysis.technical import get_m15_sr_zones
from core.data_models import TradeSignal

def compra_thread_sync(
    exnova_api,              # instância síncrona Exnova
    full_name: str,          # nome completo do ativo
    entry_value: float,      # valor da entrada
    direction: str,          # 'call' ou 'put'
    expiration: int,         # expiração em minutos
    signal_id: int,          # ID do sinal no Supabase
    supabase_service,        # instância SupabaseService
    target_ts: float         # timestamp UNIX de disparo
):
    """
    Thread síncrona que aguarda até target_ts e dispara a ordem diretamente
    pela API síncrona, depois faz polling e atualiza o Supabase.
    """
    # espera até o momento exato (com buffer)
    delay = max(target_ts - time.time(), 0)
    time.sleep(delay)

    # abre posição
    status, order_id = exnova_api.buy(entry_value, full_name, direction, expiration)
    if not status:
        # ordem rejeitada
        supabase_service.update_trade_result(signal_id, "REJEITADO")
        return

    # polling síncrono até confirmação (até 75s)
    deadline = time.time() + (expiration * 60) + 15
    lucro = None
    while time.time() < deadline:
        res = exnova_api.check_win_v4(order_id)
        if res and isinstance(res, tuple):
            resultado_str, ganho = res
            lucro = ganho
            break
        time.sleep(0.5)

    # interpreta resultado
    if lucro is None:
        resultado = "UNKNOWN"
    elif lucro > 0:
        resultado = "WIN"
    elif lucro < 0:
        resultado = "LOSS"
    else:
        resultado = "DRAW"

    # atualiza Supabase
    supabase_service.update_trade_result(signal_id, resultado)
    # opcional: atualizar saldo imediato
    try:
        new_balance = exnova_api.get_balance()
        supabase_service.update_current_balance(float(new_balance))
    except:
        pass


class TradingBot:
    def __init__(self):
        self.supabase = SupabaseService(settings.SUPABASE_URL, settings.SUPABASE_KEY)
        self.exnova   = AsyncExnovaService(settings.EXNOVA_EMAIL, settings.EXNOVA_PASSWORD)
        self.is_running      = True
        self.bot_config: Dict = {}
        self.martingale_state: Dict[str, Dict] = {}
        self.is_trade_active = False

    async def logger(self, level: str, message: str):
        ts = datetime.utcnow().isoformat()
        print(f"[{ts}] [{level.upper()}] {message}", flush=True)
        await self.supabase.insert_log(level, message)

    async def run(self):
        await self.logger('DEBUG', f"Configurado MAX_ASSETS_TO_MONITOR = {settings.MAX_ASSETS_TO_MONITOR}")
        await self.logger('INFO', 'Bot a iniciar...')
        status = await self.exnova.connect()
        if status:
            await self.logger('SUCCESS', 'Conexão com a Exnova estabelecida.')
        else:
            await self.logger('ERROR', 'Falha na conexão com a Exnova.')
            return

        # registra saldo inicial
        bal = await self.exnova.get_current_balance()
        if bal is not None:
            await self.supabase.update_current_balance(bal)
            await self.logger('INFO', f"Saldo inicial: {bal:.2f}")

        while self.is_running:
            try:
                # atualiza saldo
                bal = await self.exnova.get_current_balance()
                if bal is not None:
                    await self.supabase.update_current_balance(bal)
                    await self.logger('DEBUG', f"Saldo atualizado: {bal:.2f}")

                self.bot_config = await self.supabase.get_bot_config()
                status = self.bot_config.get('status', 'PAUSED')
                if status == 'RUNNING' and not self.is_trade_active:
                    await self.logger('INFO', 'Iniciando ciclo de análise...')
                    await self.trading_cycle()
                else:
                    await asyncio.sleep(settings.BOT_CONFIG_POLL_INTERVAL)
            except Exception as e:
                await self.logger('ERROR', f"Loop principal falhou: {e}")
                traceback.print_exc()
                await asyncio.sleep(settings.BOT_CONFIG_POLL_INTERVAL)

    async def trading_cycle(self):
        await self.exnova.change_balance(self.bot_config.get('account_type', 'PRACTICE'))

        assets = await self.exnova.get_open_assets()
        assets = assets[: settings.MAX_ASSETS_TO_MONITOR]
        await self.logger('INFO', f"Ativos: {assets}")

        # espera candle de entrada (buffer de 1.5s)
        now = datetime.utcnow()
        target_dt = (now.replace(second=0, microsecond=0) + timedelta(minutes=1)) - timedelta(seconds=1.5)
        wait = max(target_dt.timestamp() - time.time(), 0)
        await self.logger('DEBUG', f"Aguardando {wait:.2f}s até entrada otimizada...")
        await asyncio.sleep(wait)

        for full in assets:
            if self.is_trade_active:
                break
            await self._process_asset(full)

    async def _process_asset(self, full_name: str):
        try:
            base = full_name.split('-')[0]
            # busca velas
            m1, m15 = await asyncio.gather(
                self.exnova.get_historical_candles(base, 60, 20),
                self.exnova.get_historical_candles(base, 900, 4),
            )
            if not m1 or not m15:
                return

            res, sup = get_m15_sr_zones(m15)
            zones = {'resistance': res, 'support': sup}

            for strat in STRATEGIES:
                direction = strat.analyze(m1, zones)
                await self.logger('DEBUG', f"[{full_name}] Estratégia {strat.name} → {direction!r}")
                if not direction:
                    continue

                last = m1[-1]
                signal = TradeSignal(
                    pair=base,
                    direction=direction,
                    strategy=strat.name,
                    setup_candle_open=last.open,
                    setup_candle_high=last.max,
                    setup_candle_low=last.min,
                    setup_candle_close=last.close,
                )
                await self._execute_with_thread(signal, full_name)
                # Sem return: continua testando outras estratégias
        except Exception as e:
            await self.logger('ERROR', f"Erro em _process_asset({full_name}): {e}")
            traceback.print_exc()

    def _get_entry_value(self, asset: str) -> float:
        base = self.bot_config.get('entry_value', settings.ENTRY_VALUE)
        if not self.bot_config.get('use_martingale', False):
            return base
        state = self.martingale_state.get(asset, {'level': 0, 'last_value': base})
        if state['level'] == 0:
            return base
        return round(state['last_value'] * self.bot_config.get('martingale_factor', 2.3), 2)

    async def _execute_with_thread(self, signal: TradeSignal, full_name: str):
        """
        Em vez do fluxo assíncrono padrão, dispara uma thread síncrona no momento exato.
        """
        self.is_trade_active = True
        try:
            entry_value = self._get_entry_value(signal.pair)
            sid = await self.supabase.insert_trade_signal(signal)
            if not sid:
                await self.logger('ERROR', f"[{signal.pair}] falha ao inserir sinal")
                self.is_trade_active = False
                return

            # calcula target timestamp
            now = datetime.utcnow()
            target_dt = (now.replace(second=0, microsecond=0) + timedelta(minutes=1)) - timedelta(seconds=1.5)
            ts = target_dt.timestamp()

            # dispara thread que fará a ordem e atualizará o Supabase
            Thread(
                target=compra_thread_sync,
                args=(
                    self.exnova.api,
                    full_name,
                    entry_value,
                    signal.direction.lower(),
                    1,
                    sid,
                    self.supabase,
                    ts
                ),
                daemon=True
            ).start()

            await self.logger('INFO', f"[{signal.pair}] Sinal agendado para {target_dt.time()} — thread disparada.")
        except Exception as e:
            await self.logger('ERROR', f"_execute_with_thread({signal.pair}) falhou: {e}")
            traceback.print_exc()
        finally:
            self.is_trade_active = False
            await self.logger('INFO', 'Bot pronto para próxima operação')
