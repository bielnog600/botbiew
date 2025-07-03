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
        self.exnova   = AsyncExnovaService(
            settings.EXNOVA_EMAIL, settings.EXNOVA_PASSWORD
        )
        self.is_running      = True
        self.bot_config: Dict = {}
        self.martingale_state: Dict[str, Dict] = {}
        self.is_trade_active = False

    async def logger(self, level: str, message: str):
        ts = datetime.utcnow().isoformat()
        print(f"[{ts}] [{level.upper()}] {message}", flush=True)
        await self.supabase.insert_log(level, message)

    async def run(self):
        await self.logger('INFO', 'Bot a iniciar...')
        status = await self.exnova.connect()
        await self.logger('SUCCESS', 'Conexão com a Exnova estabelecida.' if status else 'Falha na Exnova')

        # registra e exibe saldo inicial
        bal = await self.exnova.get_current_balance()
        if bal is not None:
            await self.supabase.update_current_balance(bal)
            await self.logger('INFO', f"Saldo inicial: {bal:.2f}")

        while self.is_running:
            try:
                # a cada iteração, atualiza saldo
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
        # garante conta certa
        await self.exnova.change_balance(
            self.bot_config.get('account_type', 'PRACTICE')
        )

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
            m1, m15 = await asyncio.gather(
                self.exnova.get_historical_candles(base, 60, 20),
                self.exnova.get_historical_candles(base, 900, 4),
            )
            if not m1 or not m15:
                return

            res, sup = get_m15_sr_zones(m15)
            zones = {'resistance': res, 'support': sup}

            for strat in STRATEGIES:
                dir_ = strat.analyze(m1, zones)
                await self.logger(
                    'DEBUG',
                    f"[{full_name}] Estratégia {strat.name} → {dir_!r}"
                )
                if not dir_:
                    continue

                last = m1[-1]
                signal = TradeSignal(
                    pair=base,
                    direction=dir_,
                    strategy=strat.name,
                    setup_candle_open=last.open,
                    setup_candle_high=last.max,
                    setup_candle_low=last.min,
                    setup_candle_close=last.close,
                )
                await self._execute_and_wait(signal, full_name)
                return
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
        return round(
            state['last_value'] * self.bot_config.get('martingale_factor', 2.3), 2
        )

    async def _execute_and_wait(self, signal: TradeSignal, full_name: str):
        self.is_trade_active = True
        try:
            entry_value = self._get_entry_value(signal.pair)
            sid = await self.supabase.insert_trade_signal(signal)
            if not sid:
                await self.logger('ERROR', f"[{signal.pair}] falha ao inserir sinal")
                return

            oid = await self.exnova.execute_trade(
                entry_value, full_name, signal.direction.lower(), 1
            )
            if not oid:
                await self.logger('ERROR', f"[{signal.pair}] falha ao executar ordem")
                await self.supabase.update_trade_result(sid, 'REJEITADO')
                return

            await self.logger('INFO', f"[{signal.pair}] Ordem {oid} enviada, aguardando resultado…")

            # polling até 75s
            deadline = time.time() + 75
            resultado_lucro = None
            while time.time() < deadline:
                status_bool, lucro = await self.exnova.check_win_v4(oid)
                if status_bool is not None:
                    resultado_lucro = lucro
                    break
                await asyncio.sleep(0.5)

            if resultado_lucro is None:
                result = 'UNKNOWN'
                await self.logger('WARNING', f"[{signal.pair}] Sem resposta da API")
            elif resultado_lucro > 0:
                result = 'WIN'
                await self.logger('SUCCESS', f"[{signal.pair}] WIN — Lucro: {resultado_lucro:.2f}")
                self.martingale_state[signal.pair] = {'level': 0, 'last_value': entry_value}
            elif resultado_lucro < 0:
                result = 'LOSS'
                await self.logger('ERROR', f"[{signal.pair}] LOSS — Prejuízo: {resultado_lucro:.2f}")
                lvl = self.martingale_state.get(signal.pair, {}).get('level', 0) + 1
                max_lv = self.bot_config.get('martingale_levels', 2)
                if lvl <= max_lv:
                    self.martingale_state[signal.pair] = {'level': lvl, 'last_value': entry_value}
                else:
                    self.martingale_state[signal.pair] = {'level': 0, 'last_value': settings.ENTRY_VALUE}
            else:
                result = 'DRAW'
                await self.logger('INFO', f"[{signal.pair}] DRAW — Lucro zero")

            mg_lv = self.martingale_state.get(signal.pair, {}).get('level', 0)
            await self.supabase.update_trade_result(sid, result, mg_lv)

            # Atualiza saldo logo após cada resultado
            bal = await self.exnova.get_current_balance()
            if bal is not None:
                await self.supabase.update_current_balance(bal)
                await self.logger('INFO', f"Saldo pós-operação: {bal:.2f}")

        except Exception as e:
            await self.logger('ERROR', f"_execute_and_wait({signal.pair}) falhou: {e}")
            traceback.print_exc()
        finally:
            self.is_trade_active = False
            await self.logger('INFO', 'Pronto para próxima operação')
