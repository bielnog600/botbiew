import asyncio
import time
import traceback
from datetime import datetime
from typing import Dict

from config import settings
from services.exnova_service import AsyncExnovaService
from services.supabase_service import SupabaseService
from analysis.strategy import STRATEGIES
from analysis.technical import get_m15_sr_zones
from core.data_models import TradeSignal

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

        # espera candle de entrada
        now = datetime.utcnow()
        wait = (60 - now.second) + 2 if now.second > 2 else 2 - now.second
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
                await self._execute_and_wait(signal, full_name)
                # **aqui não retornamos** — continua analisando as demais estratégias
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

    async def _execute_and_wait(self, signal: TradeSignal, full_name: str):
        self.is_trade_active = True
        try:
            # balance before
            bal_before = await self.exnova.get_current_balance()

            entry_value = self._get_entry_value(signal.pair)
            sid = await self.supabase.insert_trade_signal(signal)
            if not sid:
                await self.logger('ERROR', f"[{signal.pair}] falha ao inserir sinal")
                self.is_trade_active = False
                return

            oid = await self.exnova.execute_trade(
                entry_value, full_name, signal.direction.lower(), 1
            )
            if not oid:
                await self.logger('ERROR', f"[{signal.pair}] falha ao executar ordem")
                await self.supabase.update_trade_result(sid, 'REJEITADO')
                self.is_trade_active = False
                return

            await self.logger('INFO', f"[{signal.pair}] Ordem {oid} enviada, aguardando expiração…")

            # espera expiração + small buffer
            await asyncio.sleep(65)

            # balance after
            bal_after = await self.exnova.get_current_balance()

            if bal_before is None or bal_after is None:
                result = 'UNKNOWN'
                await self.logger('WARNING', f"[{signal.pair}] Não foi possível ler saldo antes/depois")
            else:
                delta = bal_after - bal_before
                if delta > 0:
                    result = 'WIN'
                elif delta < 0:
                    result = 'LOSS'
                else:
                    result = 'DRAW'
                await self.logger('INFO', f"[{signal.pair}] ΔSaldo = {delta:.2f} → {result}")

            # persiste resultado e novo saldo
            mg_lv = self.martingale_state.get(signal.pair, {}).get('level', 0)
            await self.supabase.update_trade_result(sid, result, mg_lv)
            await self.supabase.update_current_balance(bal_after or 0.0)

            # ajusta martingale
            if result == 'WIN':
                self.martingale_state[signal.pair] = {'level': 0, 'last_value': entry_value}
            elif result == 'LOSS':
                lvl = mg_lv + 1
                max_lv = self.bot_config.get('martingale_levels', 2)
                if lvl <= max_lv:
                    self.martingale_state[signal.pair] = {'level': lvl, 'last_value': entry_value}
                else:
                    self.martingale_state[signal.pair] = {'level': 0, 'last_value': settings.ENTRY_VALUE}

        except Exception as e:
            await self.logger('ERROR', f"_execute_and_wait({signal.pair}) falhou: {e}")
            traceback.print_exc()
        finally:
            self.is_trade_active = False
            await self.logger('INFO', 'Pronto para próxima operação')
