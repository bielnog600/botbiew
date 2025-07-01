# core/bot.py
import asyncio
import time
import traceback
from typing import List, Dict

from config import settings
from services.exnova_service import AsyncExnovaService
from services.supabase_service import SupabaseService
from analysis.strategy import STRATEGIES
from analysis.technical import calculate_volatility
from core.data_models import TradeSignal, ActiveTrade

class TradingBot:
    def __init__(self):
        self.supabase = SupabaseService(settings.SUPABASE_URL, settings.SUPABASE_KEY)
        self.exnova = AsyncExnovaService(settings.EXNOVA_EMAIL, settings.EXNOVA_PASSWORD)
        self.active_assets: List[str] = []
        self.trade_queue = asyncio.Queue()
        self.is_running = True
        self.bot_config = {}
        self.martingale_state: Dict[str, Dict] = {}

    async def logger(self, level: str, message: str):
        print(f"[{level.upper()}] {message}")
        await self.supabase.insert_log(level, message)

    async def run(self):
        await self.logger('INFO', 'Bot a iniciar...')
        await self.exnova.connect()
        await self.logger('SUCCESS', f"Conexão com a Exnova estabelecida.")
        
        while self.is_running:
            try:
                self.bot_config = await self.supabase.get_bot_config()
                bot_status = self.bot_config.get('status', 'PAUSED')

                if bot_status == 'RUNNING':
                    operation_mode = self.bot_config.get('operation_mode', 'CONSERVADOR')
                    await self.logger('INFO', f"Bot em modo RUNNING ({operation_mode}). A iniciar ciclo de negociação...")
                    await self.trading_loop()
                else:
                    await self.logger('INFO', 'Bot em modo PAUSADO. A aguardar...')
                    await asyncio.sleep(15)

            except Exception as e:
                await self.logger('ERROR', f"Erro fatal no loop principal: {e}")
                traceback.print_exc()
                await asyncio.sleep(30)

    async def trading_loop(self):
        account_type = self.bot_config.get('account_type', 'PRACTICE')
        await self.logger('INFO', f"A usar a conta: {account_type}")
        await self.exnova.change_balance(account_type)

        current_balance = await self.exnova.get_current_balance()
        if current_balance is not None:
            await self.supabase.update_current_balance(current_balance)
            await self.logger('INFO', f"Saldo da conta atualizado: ${current_balance:.2f}")

        self.active_assets = await self.exnova.get_open_assets()
        self.active_assets = self.active_assets[:settings.MAX_CONCURRENT_ASSETS]
        
        # FIX: Restaurado o código que estava em falta
        trading_tasks = [self._process_asset_task(asset) for asset in self.active_assets]
        result_checker_task = asyncio.create_task(self._result_checker_loop())
        
        # Executa as tarefas por um período antes de re-verificar a config
        done, pending = await asyncio.wait(
            trading_tasks + [result_checker_task], 
            timeout=60, 
            return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()

    # FIX: A função _process_asset_task que estava em falta foi restaurada.
    async def _process_asset_task(self, asset: str):
        operation_mode = self.bot_config.get('operation_mode', 'CONSERVADOR')
        volatility_threshold = 0.6 if operation_mode == 'CONSERVADOR' else 0.85

        while True:
            try:
                candles = await self.exnova.get_historical_candles(asset, 60, 100)
                if not candles:
                    await asyncio.sleep(5)
                    continue

                volatility = calculate_volatility(candles, lookback=10)
                
                for strategy in STRATEGIES:
                    direction = strategy.analyze(candles)
                    if direction:
                        await self.logger('SUCCESS', f"[{asset}] Sinal encontrado! Direção: {direction.upper()}, Estratégia: {strategy.name}")
                        
                        signal = TradeSignal(
                            pair=asset,
                            direction=direction,
                            strategy=strategy.name,
                            volatility_score=volatility
                        )
                        asyncio.create_task(self._execute_trade(signal))
                        await asyncio.sleep(60)
                        break
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                break
            except Exception as e:
                await self.logger('ERROR', f"Erro ao processar o ativo {asset}: {e}")
                traceback.print_exc()
                await asyncio.sleep(30)

    def _get_entry_value(self, asset: str) -> float:
        base_value = self.bot_config.get('entry_value', 1.0)
        use_mg = self.bot_config.get('use_martingale', False)

        if not use_mg:
            return base_value

        asset_mg_state = self.martingale_state.get(asset, {'level': 0, 'last_value': base_value})
        
        if asset_mg_state['level'] == 0:
            return base_value
        else:
            mg_factor = self.bot_config.get('martingale_factor', 2.3)
            next_value = asset_mg_state['last_value'] * mg_factor
            return round(next_value, 2)

    async def _execute_trade(self, signal: TradeSignal):
        try:
            entry_value = self._get_entry_value(signal.pair)
            
            signal_id = await self.supabase.insert_trade_signal(signal)
            if not signal_id:
                await self.logger('ERROR', f"[{signal.pair}] Falha ao registrar sinal. A operação não será executada.")
                return

            await self.logger('INFO', f"[{signal.pair}] A executar ordem {signal.direction.upper()} com valor de ${entry_value}...")
            order_id = await self.exnova.execute_trade(entry_value, signal.pair, signal.direction, 1)
            
            if order_id:
                await self.logger('SUCCESS', f"[{signal.pair}] Ordem {order_id} (sinal ID: {signal_id}) enviada.")
                
                active_trade = ActiveTrade(
                    order_id=str(order_id), 
                    signal_id=signal_id, 
                    pair=signal.pair, 
                    entry_value=entry_value
                )
                await self.trade_queue.put(active_trade)
            else:
                await self.logger('ERROR', f"[{signal.pair}] Falha na execução da ordem na Exnova.")
                await self.supabase.update_trade_result(signal_id, "ERROR")
        except Exception as e:
            await self.logger('ERROR', f"Exceção não tratada em _execute_trade para {signal.pair}: {e}")
            traceback.print_exc()

    async def _result_checker_loop(self):
        while self.is_running:
            trade = await self.trade_queue.get()
            
            result = None
            for _ in range(15):
                result = await self.exnova.check_trade_result(trade.order_id)
                if result: break
                await asyncio.sleep(5)

            if result:
                await self.logger('SUCCESS' if result == 'WIN' else 'ERROR', f"[{trade.pair}] Resultado da ordem {trade.order_id}: {result}")
                await self.supabase.update_trade_result(trade.signal_id, result)
                self._update_martingale_state(trade.pair, result, trade.entry_value)
            else:
                await self.logger('WARNING', f"[{trade.pair}] Timeout ao obter resultado da ordem {trade.order_id}.")
                await self.supabase.update_trade_result(trade.signal_id, "TIMEOUT")
            
            self.trade_queue.task_done()

    def _update_martingale_state(self, asset: str, result: str, last_value: float):
        if not self.bot_config.get('use_martingale', False):
            return

        max_levels = self.bot_config.get('martingale_levels', 2)
        current_level = self.martingale_state.get(asset, {}).get('level', 0)

        if result == 'WIN':
            self.martingale_state[asset] = {'level': 0, 'last_value': self.bot_config.get('entry_value', 1.0)}
            asyncio.create_task(self.logger('INFO', f"[{asset}] Martingale resetado após WIN."))
        elif result == 'LOSS':
            if current_level < max_levels:
                self.martingale_state[asset] = {'level': current_level + 1, 'last_value': last_value}
                asyncio.create_task(self.logger('WARNING', f"[{asset}] LOSS. A ativar Martingale nível {current_level + 1}."))
            else:
                self.martingale_state[asset] = {'level': 0, 'last_value': self.bot_config.get('entry_value', 1.0)}
                asyncio.create_task(self.logger('ERROR', f"[{asset}] Limite de Martingale ({max_levels}) atingido. A resetar."))
