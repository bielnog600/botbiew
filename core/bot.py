# core/bot.py
import asyncio
import time
import traceback
import sys # Importa o módulo do sistema para poder sair
from datetime import datetime, timezone
from typing import List, Dict, Optional

from config import settings
from services.exnova_service import AsyncExnovaService
from services.supabase_service import SupabaseService
from analysis.strategy import STRATEGIES
from core.data_models import TradeSignal, ActiveTrade, Candle

class TradingBot:
    def __init__(self):
        self.supabase = SupabaseService(settings.SUPABASE_URL, settings.SUPABASE_KEY)
        self.exnova = AsyncExnovaService(settings.EXNOVA_EMAIL, settings.EXNOVA_PASSWORD)
        self.is_running = True
        self.bot_config = {}
        self.trade_queue = asyncio.Queue()
        self.cooldown_assets = set()
        self.martingale_state: Dict[str, Dict] = {}
        # Guarda o timestamp do último reinício solicitado para evitar loops
        self.last_restart_request: Optional[datetime] = None

    async def logger(self, level: str, message: str):
        print(f"[{level.upper()}] {message}", flush=True)
        await self.supabase.insert_log(level, message)

    async def run(self):
        await self.logger('INFO', 'Bot a iniciar...')
        await self.exnova.connect()
        await self.logger('SUCCESS', f"Conexão com a Exnova estabelecida.")
        
        asyncio.create_task(self._result_checker_loop())

        while self.is_running:
            try:
                self.bot_config = await self.supabase.get_bot_config()
                
                # Lógica de Reinício
                restart_ts_str = self.bot_config.get('restart_requested_at')
                if restart_ts_str:
                    # Converte a string ISO para um objeto datetime ciente do fuso horário
                    restart_ts = datetime.fromisoformat(restart_ts_str).replace(tzinfo=timezone.utc)
                    if self.last_restart_request is None or restart_ts > self.last_restart_request:
                        await self.logger('WARNING', "Pedido de reinício recebido do painel. A encerrar...")
                        self.is_running = False
                        # sys.exit(0) é uma forma limpa de terminar o processo.
                        # O Coolify irá detetar que o processo terminou e irá reiniciá-lo automaticamente.
                        sys.exit(0) 
                
                if self.bot_config.get('status') == 'RUNNING':
                    await self.logger('INFO', "Bot em modo RUNNING. A iniciar ciclo de negociação...")
                    await self.trading_cycle()
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

        current_balance = await self.exnova.get_current_balance()
        if current_balance is not None:
            await self.supabase.update_current_balance(current_balance)

        open_assets = await self.exnova.get_open_assets()
        assets_to_trade = [asset for asset in open_assets if asset not in self.cooldown_assets]
        assets_to_trade = assets_to_trade[:settings.MAX_CONCURRENT_ASSETS]
        
        await self.logger('INFO', f"Ativos a serem monitorizados: {assets_to_trade}")

        trading_tasks = [asyncio.create_task(self._process_asset_task(asset)) for asset in assets_to_trade]
        
        if not trading_tasks:
            await asyncio.sleep(55)
            return
            
        done, pending = await asyncio.wait(trading_tasks, timeout=55)
        for task in pending:
            task.cancel()

    async def _wait_for_next_candle(self):
        now = datetime.now()
        wait_time = (60 - now.second) + 2 if now.second > 2 else 2 - now.second
        await asyncio.sleep(wait_time)

    async def _process_asset_task(self, full_asset_name: str):
        try:
            await self._wait_for_next_candle()
            
            clean_asset_name = full_asset_name.split('-')[0]
            candles = await self.exnova.get_historical_candles(clean_asset_name, 60, 100)
            if not candles: return

            for strategy in STRATEGIES:
                direction = strategy.analyze(candles)
                if direction:
                    await self.logger('SUCCESS', f"[{full_asset_name}] Sinal confirmado! Direção: {direction.upper()}, Estratégia: {strategy.name}")
                    
                    self.cooldown_assets.add(full_asset_name)
                    asyncio.create_task(self._remove_from_cooldown(full_asset_name, 300))
                    
                    last_candle = candles[-1]
                    signal = TradeSignal(
                        pair=clean_asset_name, 
                        direction=direction, 
                        strategy=strategy.name,
                        setup_candle_open=last_candle.open,
                        setup_candle_high=last_candle.max,
                        setup_candle_low=last_candle.min,
                        setup_candle_close=last_candle.close
                    )
                    await self._execute_trade(signal, full_asset_name)
                    break 
        except asyncio.CancelledError:
            pass
        except Exception as e:
            await self.logger('ERROR', f"Erro ao processar o ativo {full_asset_name}: {e}")
            traceback.print_exc()

    async def _remove_from_cooldown(self, asset: str, delay: int):
        await asyncio.sleep(delay)
        self.cooldown_assets.discard(asset)
        await self.logger('INFO', f"[{asset}] Cooldown terminado. O ativo voltou a ser analisado.")

    def _get_entry_value(self, asset: str) -> float:
        base_value = self.bot_config.get('entry_value', 1.0)
        use_mg = self.bot_config.get('use_martingale', False)
        if not use_mg: return base_value
        asset_mg_state = self.martingale_state.get(asset, {'level': 0, 'last_value': base_value})
        if asset_mg_state['level'] == 0: return base_value
        mg_factor = self.bot_config.get('martingale_factor', 2.3)
        next_value = asset_mg_state['last_value'] * mg_factor
        return round(next_value, 2)

    async def _execute_trade(self, signal: TradeSignal, full_asset_name: str):
        try:
            entry_value = self._get_entry_value(signal.pair)
            balance_before = await self.exnova.get_current_balance()
            if balance_before is None:
                await self.logger('ERROR', f"[{signal.pair}] Não foi possível obter o saldo antes da operação. A abortar.")
                return

            signal_id = await self.supabase.insert_trade_signal(signal)
            if not signal_id:
                await self.logger('ERROR', f"[{signal.pair}] Falha ao registrar sinal.")
                return

            order_id = await self.exnova.execute_trade(entry_value, full_asset_name, signal.direction, 1)
            if order_id:
                await self.logger('SUCCESS', f"[{signal.pair}] Ordem {order_id} (sinal ID: {signal_id}) enviada.")
                active_trade = ActiveTrade(
                    order_id=str(order_id), 
                    signal_id=signal_id, 
                    pair=signal.pair, 
                    entry_value=entry_value,
                    balance_before=balance_before
                )
                await self.trade_queue.put(active_trade)
            else:
                await self.logger('ERROR', f"[{signal.pair}] Falha na execução da ordem na Exnova para '{full_asset_name}'.")
                await self.supabase.update_trade_result(signal_id, "REJEITADO")
        except Exception as e:
            await self.logger('ERROR', f"Exceção não tratada em _execute_trade para {signal.pair}: {e}")
            traceback.print_exc()

    async def _result_checker_loop(self):
        while self.is_running:
            try:
                trade = await self.trade_queue.get()
                asyncio.create_task(self._check_and_process_single_trade(trade))
                self.trade_queue.task_done()
            except Exception as e:
                await self.logger('ERROR', f"Erro no loop de verificação de resultados: {e}")

    async def _check_and_process_single_trade(self, trade: ActiveTrade):
        try:
            await self.logger('INFO', f"[{trade.pair}] Operação {trade.order_id} em andamento. A aguardar expiração...")
            await asyncio.sleep(65)

            await self.logger('INFO', f"[{trade.pair}] Expiração da ordem {trade.order_id}. A verificar saldo...")
            balance_after = await self.exnova.get_current_balance()
            
            result = "UNKNOWN"
            if balance_after is not None:
                if balance_after > trade.balance_before:
                    result = "WIN"
                else:
                    result = "LOSS"
            
            current_mg_level = self.martingale_state.get(trade.pair, {}).get('level', 0)
            update_success = await self.supabase.update_trade_result(trade.signal_id, result, current_mg_level)
            
            if update_success:
                await self.logger('SUCCESS', f"[{trade.pair}] Resultado da ordem {trade.order_id} atualizado para {result}.")
            else:
                await self.logger('ERROR', f"[{trade.pair}] FALHA CRÍTICA ao atualizar o resultado da ordem {trade.order_id} no Supabase.")
            
            self._update_martingale_state(trade.pair, result, trade.entry_value)

        except Exception as e:
            await self.logger('ERROR', f"Exceção não tratada em _check_and_process_single_trade para {trade.pair}: {e}")
            traceback.print_exc()

    def _update_martingale_state(self, asset: str, result: str, last_value: float):
        if not self.bot_config.get('use_martingale', False): return
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
