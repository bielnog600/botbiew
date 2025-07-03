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

        open_assets = await self.exnova.get_open_assets()
        assets_to_trade = open_assets[:settings.MAX_ASSETS_TO_MONITOR]
        await self.logger('INFO', f"Ativos a serem monitorizados: {assets_to_trade}")

        await self._wait_for_next_candle()

        for full_asset_name in assets_to_trade:
            if self.is_trade_active:
                break
            await self._process_asset_task(full_asset_name)

    async def _wait_for_next_candle(self):
        now = datetime.now()
        target_second = 58
        if now.second < target_second:
            wait_time = target_second - now.second
        else:
            wait_time = (60 - now.second) + target_second
        await self.logger('INFO', f"A aguardar {wait_time}s para o ponto de entrada...")
        await asyncio.sleep(wait_time)

    async def _process_asset_task(self, full_asset_name: str):
        try:
            clean_asset_name = full_asset_name.split('-')[0]
            await self.logger('INFO', f"[{full_asset_name}] Ponto de entrada atingido. A analisar...")

            m1_task = self.exnova.get_historical_candles(clean_asset_name, 60, 20)
            m15_task = self.exnova.get_historical_candles(clean_asset_name, 900, 4)
            m1_candles, m15_candles = await asyncio.gather(m1_task, m15_task)
            if not m1_candles or not m15_candles:
                return

            resistance, support = get_m15_sr_zones(m15_candles)
            zones = {'resistance': resistance, 'support': support}

            for strategy in STRATEGIES:
                direction = strategy.analyze(m1_candles, zones)
                if direction:
                    await self.logger('SUCCESS', f"[{full_asset_name}] Sinal confirmado! Direção: {direction.upper()}, Estratégia: {strategy.name}")
                    last = m1_candles[-1]
                    signal = TradeSignal(
                        pair=clean_asset_name,
                        direction=direction,
                        strategy=strategy.name,
                        setup_candle_open=last.open,
                        setup_candle_high=last.max,
                        setup_candle_low=last.min,
                        setup_candle_close=last.close
                    )
                    await self._execute_and_wait_for_trade(signal, full_asset_name)
                    return
        except Exception as e:
            await self.logger('ERROR', f"Erro ao processar o ativo {full_asset_name}: {e}")
            traceback.print_exc()

    def _get_entry_value(self, asset: str) -> float:
        base_value = self.bot_config.get('entry_value', 1.0)
        if not self.bot_config.get('use_martingale', False):
            return base_value
        state = self.martingale_state.get(asset, {'level': 0, 'last_value': base_value})
        if state['level'] == 0:
            return base_value
        next_val = state['last_value'] * self.bot_config.get('martingale_factor', 2.3)
        return round(next_val, 2)

    async def _execute_and_wait_for_trade(self, signal: TradeSignal, full_asset_name: str):
        self.is_trade_active = True
        try:
            entry_value = self._get_entry_value(signal.pair)
            signal_id = await self.supabase.insert_trade_signal(signal)
            if not signal_id:
                await self.logger('ERROR', f"[{signal.pair}] Falha ao registrar sinal.")
                self.is_trade_active = False
                return

            order_id = await self.exnova.execute_trade(entry_value, full_asset_name, signal.direction, 1)
            if order_id:
                await self.logger('SUCCESS', f"[{signal.pair}] Ordem {order_id} enviada. A aguardar resultado...")

                expiration = time.time() + 75
                result = None
                while time.time() < expiration:
                    result_data = await self.exnova.check_win_v4(order_id)
                    if result_data and isinstance(result_data, tuple):
                        status, profit = result_data
                        if isinstance(status, bool):
                            result = 'WIN' if status else 'LOSS'
                            break
                        s = str(status).lower()
                        if s == 'win':
                            result = 'WIN'
                            break
                        if s in ('loss', 'lose'):
                            result = 'LOSS'
                            break
                    await asyncio.sleep(0.5)

                if result is None:
                    result = 'UNKNOWN'

                mg_level = self.martingale_state.get(signal.pair, {}).get('level', 0)
                updated = await self.supabase.update_trade_result(signal_id, result, mg_level)
                if updated:
                    await self.logger('SUCCESS', f"[{signal.pair}] Resultado da ordem {order_id} atualizado para {result}.")
                else:
                    await self.logger('ERROR', f"[{signal.pair}] Falha ao atualizar resultado da ordem {order_id} no Supabase.")

                # atualizar martingale
                self._update_martingale_state(signal.pair, result, entry_value)
            else:
                await self.logger('ERROR', f"[{signal.pair}] Falha na execução da ordem para {full_asset_name}.")
                await self.supabase.update_trade_result(signal_id, 'REJEITADO')
        except Exception as e:
            await self.logger('ERROR', f"Exceção em _execute_and_wait_for_trade para {signal.pair}: {e}")
            traceback.print_exc()
        finally:
            self.is_trade_active = False
            await self.logger('INFO', 'Bot libertado. Pronto para a próxima análise.')

    def _update_martingale_state(self, asset: str, result: str, last_value: float):
        if not self.bot_config.get('use_martingale', False):
            return
        max_lv = self.bot_config.get('martingale_levels', 2)
        curr = self.martingale_state.get(asset, {}).get('level', 0)
        if result == 'WIN':
            self.martingale_state[asset] = {'level': 0, 'last_value': self.bot_config.get('entry_value', 1.0)}
            asyncio.create_task(self.logger('INFO', f"[{asset}] Martingale resetado após WIN."))
        elif result == 'LOSS':
            if curr < max_lv:
                self.martingale_state[asset] = {'level': curr + 1, 'last_value': last_value}
                asyncio.create_task(self.logger('WARNING', f"[{asset}] LOSS. Martingale nível {curr + 1}."))
            else:
                self.martingale_state[asset] = {'level': 0, 'last_value': self.bot_config.get('entry_value', 1.0)}
                asyncio.create_task(self.logger('ERROR', f"[{asset}] Limite de Martingale atingido. Reset."))
