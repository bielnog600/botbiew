import asyncio
import traceback
from datetime import datetime
from typing import Dict, List

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
        self.martingale_state: Dict[str, Dict] = {}
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
                if self.bot_config.get('status') == 'RUNNING':
                    if not self.is_trade_active:
                        await self.logger('INFO', 'Bot livre. A iniciar ciclo de análise...')
                        await self.trading_cycle()
                    else:
                        await self.logger('INFO', 'A aguardar resultado da operação ativa...')
                        await asyncio.sleep(5)
                else:
                    await self.logger('INFO', 'Bot em modo PAUSADO. A aguardar...')
                    await asyncio.sleep(15)
            except Exception as e:
                await self.logger('ERROR', f"Erro fatal no loop principal: {e}")
                traceback.print_exc()
                await asyncio.sleep(30)

    async def trading_cycle(self):
        account_type = self.bot_config.get('account_type', 'PRACTICE')
        await self.exnova.change_balance(account_type)

        assets = await self.exnova.get_open_assets()
        assets = assets[:settings.MAX_ASSETS_TO_MONITOR]
        await self.logger('INFO', f"Ativos a serem monitorizados: {assets}")

        await self._wait_for_next_candle()
        for asset in assets:
            if self.is_trade_active:
                break
            await self._process_asset(asset)

    async def _wait_for_next_candle(self):
        now = datetime.now()
        wait = (60 - now.second) + 2 if now.second > 2 else 2 - now.second
        await self.logger('INFO', f"A aguardar {wait}s até fechamento da vela de entrada...")
        await asyncio.sleep(wait)

    async def _process_asset(self, full_asset_name: str):
        try:
            base = full_asset_name.split('-')[0]
            await self.logger('INFO', f"[{full_asset_name}] Ponto de entrada! Analisando...")
            m1_task = self.exnova.get_historical_candles(base, 60, 20)
            m15_task = self.exnova.get_historical_candles(base, 900, 4)
            m1_candles, m15_candles = await asyncio.gather(m1_task, m15_task)
            if not m1_candles or not m15_candles:
                return

            resistance, support = get_m15_sr_zones(m15_candles)
            zones = {'resistance': resistance, 'support': support}
            for strat in STRATEGIES:
                direction = strat.analyze(m1_candles, zones)
                if direction:
                    await self.logger('SUCCESS', f"[{full_asset_name}] Sinal: {direction.upper()} ({strat.name})")
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
                    await self._execute_and_wait(signal, full_asset_name)
                    return
        except Exception as e:
            await self.logger('ERROR', f"Erro ao processar ativo {full_asset_name}: {e}")
            traceback.print_exc()

    def _get_entry_value(self, asset: str) -> float:
        base = self.bot_config.get('entry_value', 1.0)
        if not self.bot_config.get('use_martingale', False):
            return base
        state = self.martingale_state.get(asset, {'level': 0, 'last_value': base})
        if state['level'] == 0:
            return base
        return round(state['last_value'] * self.bot_config.get('martingale_factor', 2.3), 2)

    async def _execute_and_wait(self, signal: TradeSignal, full_asset_name: str):
        self.is_trade_active = True
        try:
            entry_value = self._get_entry_value(signal.pair)
            sid = await self.supabase.insert_trade_signal(signal)
            if not sid:
                await self.logger('ERROR', f"[{signal.pair}] Falha ao registrar sinal.")
                return

            order_id = await self.exnova.execute_trade(entry_value, full_asset_name, signal.direction, 1)
            if not order_id:
                await self.logger('ERROR', f"[{signal.pair}] Falha na execução da ordem.")
                await self.supabase.update_trade_result(sid, 'REJEITADO')
                return

            await self.logger('SUCCESS', f"[{signal.pair}] Ordem {order_id} enviada. A aguardar fechamento da vela…")

            # espera fechamento da vela de expiração
            now = datetime.now()
            wait = (60 - now.second) + 2 if now.second > 2 else 2 - now.second
            await self.logger('DEBUG', f"Esperando {wait}s pela vela de expiração...")
            await asyncio.sleep(wait)

            # obtém as duas últimas velas
# obtém candle de expiração
            candles = await self.exnova.get_historical_candles(signal.pair, 60, 2)
            if len(candles) < 2:
                await self.logger('ERROR', f"[{signal.pair}] Velas insuficientes para inferir resultado.")
                result = 'UNKNOWN'
            else:
                entry_close   = candles[-2].close
                exp_candle    = candles[-1]
                candle_low    = exp_candle.min
                candle_high   = exp_candle.max
                await self.logger('DEBUG', f"[{signal.pair}] entry={entry_close}, low={candle_low}, high={candle_high}")

                if signal.direction.upper() == 'CALL':
        # ganhou se nem um instante a vela desceu abaixo do entry
                    result = 'WIN' if candle_low > entry_close else 'LOSS'
                else:  # PUT
        # ganhou se nem um instante a vela subiu acima do entry
                    result = 'WIN' if candle_high < entry_close else 'LOSS'


            # grava no Supabase
            mg = self.martingale_state.get(signal.pair, {}).get('level', 0)
            ok = await self.supabase.update_trade_result(sid, result, mg)
            if ok:
                await self.logger('SUCCESS', f"[{signal.pair}] Resultado: {result}.")
            else:
                await self.logger('ERROR', f"[{signal.pair}] Falha ao atualizar resultado.")

            # ajusta martingale
            if result == 'WIN':
                self.martingale_state[signal.pair] = {'level': 0, 'last_value': entry_value}
            else:
                lvl = self.martingale_state.get(signal.pair, {}).get('level', 0) + 1
                if lvl <= self.bot_config.get('martingale_levels', 2):
                    self.martingale_state[signal.pair] = {'level': lvl, 'last_value': entry_value}
                else:
                    self.martingale_state[signal.pair] = {'level': 0, 'last_value': self.bot_config.get('entry_value', 1.0)}

        except Exception as e:
            await self.logger('ERROR', f"Erro em _execute_and_wait para {signal.pair}: {e}")
            traceback.print_exc()
        finally:
            self.is_trade_active = False
            await self.logger('INFO', 'Bot pronto para próxima operação.')
