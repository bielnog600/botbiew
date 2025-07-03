import asyncio
import time
import traceback
from datetime import datetime
from typing import Dict, Optional

from config import settings
from services.exnova_service import AsyncExnovaService
from services.supabase_service import SupabaseService
from analysis.strategy import STRATEGIES
from analysis.technical import get_m15_sr_zones
from core.data_models import TradeSignal

class TradingBot:
    def __init__(self):
        self.supabase = SupabaseService(settings.SUPABASE_URL, settings.SUPABASE_KEY)
        self.exnova = AsyncExnovaService(settings.EXNOVA_EMAIL, settings.EXNOVA_PASSWORD)
        self.is_running = True
        self.bot_config: Dict = {}
        self.martingale_state: Dict[str, Dict[str, float]] = {}
        self.is_trade_active = False

    async def logger(self, level: str, message: str):
        print(f"[{level.upper()}] {message}", flush=True)
        await self.supabase.insert_log(level, message)

    async def run(self):
        await self.logger('INFO', 'Bot a iniciar...')
        await self.exnova.connect()
        await self.logger('SUCCESS', 'Conexão com a Exnova estabelecida.')

        while self.is_running:
            try:
                self.bot_config = await self.supabase.get_bot_config()
                status = self.bot_config.get('status', 'PAUSED')
                if status == 'RUNNING':
                    if not self.is_trade_active:
                        await self.logger('INFO', 'Bot livre. Iniciando ciclo de análise...')
                        await self.trading_cycle()
                    else:
                        await self.logger('INFO', 'Aguardando resultado da operação ativa...')
                        await asyncio.sleep(settings.BOT_CONFIG_POLL_INTERVAL)
                else:
                    await self.logger('INFO', 'Bot em modo PAUSADO. Aguardando...')
                    await asyncio.sleep(settings.BOT_CONFIG_POLL_INTERVAL)
            except Exception as e:
                await self.logger('ERROR', f"Erro no loop principal: {e}")
                traceback.print_exc()
                await asyncio.sleep(settings.BOT_CONFIG_POLL_INTERVAL)

    async def trading_cycle(self):
        await self.exnova.change_balance(self.bot_config.get('account_type', 'PRACTICE'))
        assets = await self.exnova.get_open_assets()
        assets = assets[:settings.MAX_ASSETS_TO_MONITOR]
        await self.logger('INFO', f"Monitorando ativos: {assets}")
        await self._wait_for_next_candle()
        for asset in assets:
            if self.is_trade_active:
                break
            await self._process_asset(asset)

    async def _wait_for_next_candle(self):
        now = datetime.now()
        wait = (60 - now.second) + 2 if now.second > 2 else 2 - now.second
        await self.logger('DEBUG', f"Aguardando {wait}s até próximo candle...")
        await asyncio.sleep(wait)

    async def _process_asset(self, full_name: str):
        try:
            base = full_name.split('-')[0]
            await self.logger('INFO', f"[{full_name}] Analisando setup...")
            m1 = self.exnova.get_historical_candles(base, 60, 20)
            m15 = self.exnova.get_historical_candles(base, 900, 4)
            m1_candles, m15_candles = await asyncio.gather(m1, m15)
            if not m1_candles or not m15_candles:
                return
            resistance, support = get_m15_sr_zones(m15_candles)
            zones = {'resistance': resistance, 'support': support}
            for strat in STRATEGIES:
                direction = strat.analyze(m1_candles, zones)
                if direction:
                    await self.logger('SUCCESS', f"[{full_name}] Sinal: {direction.upper()} ({strat.name})")
                    last = m1_candles[-1]
                    signal = TradeSignal(
                        pair=base,
                        direction=direction,
                        strategy=strat.name,
                        setup_candle_open=last.open,
                        setup_candle_high=last.max,
                        setup_candle_low=last.min,
                        setup_candle_close=last.close
                    )
                    await self._execute_and_wait(signal, full_name)
                    return
        except Exception as e:
            await self.logger('ERROR', f"Erro processando {full_name}: {e}")
            traceback.print_exc()

    def _get_entry_value(self, asset: str) -> float:
        base = self.bot_config.get('entry_value', settings.ENTRY_VALUE)
        if not self.bot_config.get('use_martingale', settings.USE_MARTINGALE):
            return base
        state = self.martingale_state.get(asset, {'level': 0, 'last_value': base})
        if state['level'] == 0:
            return base
        return round(state['last_value'] * self.bot_config.get('martingale_factor', settings.MARTINGALE_FACTOR), 2)

    async def _execute_and_wait(self, signal: TradeSignal, full_name: str):
        self.is_trade_active = True
        try:
            entry_value = self._get_entry_value(signal.pair)
            sid = await self.supabase.insert_trade_signal(signal)
            if not sid:
                await self.logger('ERROR', f"[{signal.pair}] Falha ao registrar sinal")
                return
            order_id = await self.exnova.execute_trade(entry_value, full_name, signal.direction, 1)
            if not order_id:
                await self.logger('ERROR', f"[{signal.pair}] Falha execução da ordem")
                await self.supabase.update_trade_result(sid, 'REJEITADO')
                return

            await self.logger('INFO', f"[{signal.pair}] Ordem {order_id} enviada. Aguardando resultado oficial…")

            # Polling oficial pelo lucro
            deadline = time.time() + 75
            resultado_lucro: Optional[float] = None
            while time.time() < deadline:
                await self.logger('DEBUG', f"[{signal.pair}] Polling oficial: check_win_v4({order_id})")
                status_data = await self.exnova.check_win_v4(order_id)
                await self.logger('DEBUG', f"[{signal.pair}] status_data={status_data!r}")
                if status_data:
                    status_bool, lucro = status_data
                    resultado_lucro = lucro
                    await self.logger('DEBUG', f"[{signal.pair}] API retornou status={status_bool}, lucro={lucro}")
                    break
                await asyncio.sleep(0.5)

            # Interpretação do resultado pelo lucro
            if resultado_lucro is None:
                result = 'UNKNOWN'
                await self.logger('WARNING', f"[{signal.pair}] Sem resposta oficial da API, marcado como UNKNOWN.")
            elif resultado_lucro == 0:
                result = 'DRAW'
                await self.logger('WARNING', f"[{signal.pair}] RESULTADO: EMPATE (lucro=0).")
            elif resultado_lucro > 0:
                result = 'WIN'
                self.martingale_state[signal.pair] = {'level': 0, 'last_value': entry_value}
                await self.logger('SUCCESS', f"[{signal.pair}] RESULTADO: WIN — Lucro: {resultado_lucro:.2f}")
            else:
                result = 'LOSS'
                lvl = self.martingale_state.get(signal.pair, {}).get('level', 0) + 1
                max_lv = self.bot_config.get('martingale_levels', settings.MARTINGALE_LEVELS)
                if lvl <= max_lv:
                    self.martingale_state[signal.pair] = {'level': lvl, 'last_value': entry_value}
                else:
                    self.martingale_state[signal.pair] = {'level': 0, 'last_value': settings.ENTRY_VALUE}
                await self.logger('ERROR', f"[{signal.pair}] RESULTADO: LOSS — Prejuízo: {resultado_lucro:.2f}")

            # Grava resultado no Supabase
            martingale_lv = self.martingale_state.get(signal.pair, {}).get('level', 0)
            await self.supabase.update_trade_result(sid, result, martingale_lv)
        except Exception as e:
            await self.logger('ERROR', f"Erro em _execute_and_wait para {signal.pair}: {e}")
            traceback.print_exc()
        finally:
            self.is_trade_active = False
            await self.logger('INFO', 'Pronto para próxima operação')
