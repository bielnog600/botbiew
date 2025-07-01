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
        self.bot_config = {} # Armazena a configuração remota

    async def logger(self, level: str, message: str):
        """Envia logs para o console e para o Supabase."""
        print(f"[{level.upper()}] {message}")
        await self.supabase.insert_log(level, message)

    async def run(self):
        """Ponto de entrada principal para a execução do bot."""
        await self.logger('INFO', 'Bot a iniciar...')
        await self.exnova.connect()
        await self.logger('SUCCESS', f"Conexão com a Exnova estabelecida.")
        
        # Loop principal que verifica o status e as configurações do bot
        while self.is_running:
            try:
                self.bot_config = await self.supabase.get_bot_config()
                bot_status = self.bot_config.get('status', 'PAUSED')

                if bot_status == 'RUNNING':
                    await self.logger('INFO', 'Bot em modo RUNNING. A iniciar ciclo de negociação...')
                    # Aqui, passamos a configuração atual para o ciclo de negociação
                    await self.trading_loop()
                else:
                    await self.logger('INFO', 'Bot em modo PAUSADO. A aguardar...')
                    await asyncio.sleep(15) # Verifica o status com menos frequência quando pausado

            except Exception as e:
                await self.logger('ERROR', f"Erro fatal no loop principal: {e}")
                traceback.print_exc()
                await asyncio.sleep(30)

    async def trading_loop(self):
        """Executa um ciclo completo de busca e execução de trades."""
        await self.logger('INFO', f"A usar a conta: {self.bot_config.get('account_type', 'N/A')}")
        await self.exnova.change_balance(self.bot_config.get('account_type', 'PRACTICE'))

        self.active_assets = await self.exnova.get_open_assets()
        self.active_assets = self.active_assets[:settings.MAX_CONCURRENT_ASSETS]
        await self.logger('INFO', f"A monitorizar os seguintes ativos: {self.active_assets}")

        trading_tasks = [self._process_asset_task(asset) for asset in self.active_assets]
        result_checker_task = asyncio.create_task(self._result_checker_loop())
        
        # Executa as tarefas por um período antes de re-verificar a config
        # Isto evita que o bot fique preso aqui se o status mudar para PAUSED
        done, pending = await asyncio.wait(
            trading_tasks + [result_checker_task], 
            timeout=60, 
            return_when=asyncio.FIRST_COMPLETED
        )

        # Cancela as tarefas pendentes para o próximo ciclo
        for task in pending:
            task.cancel()


    async def _process_asset_task(self, asset: str):
        """Tarefa assíncrona que monitora e opera um único ativo."""
        while True: # O loop principal irá gerir o cancelamento desta tarefa
            try:
                candles = await self.exnova.get_historical_candles(asset, 60, 100)
                if not candles:
                    await asyncio.sleep(5)
                    continue

                volatility = calculate_volatility(candles, lookback=10)
                await self.logger('INFO', f"[{asset}] Análise - Velas: {len(candles)}, Volatilidade: {volatility:.2f}")

                if volatility > 0.7:
                    await asyncio.sleep(60)
                    continue
                
                for strategy in STRATEGIES:
                    direction = strategy.analyze(candles)
                    if direction:
                        await self.logger('SUCCESS', f"[{asset}] Sinal encontrado! Direção: {direction.upper()}, Estratégia: {strategy.name}")
                        signal = TradeSignal(
                            asset=asset,
                            direction=direction,
                            strategy=strategy.name,
                            volatility_score=volatility
                        )
                        asyncio.create_task(self._execute_trade(signal))
                        await asyncio.sleep(60)
                        break
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                await self.logger('WARNING', f"Tarefa para o ativo {asset} cancelada. A reiniciar ciclo.")
                break
            except Exception as e:
                await self.logger('ERROR', f"Erro ao processar o ativo {asset}: {e}")
                traceback.print_exc()
                await asyncio.sleep(30)

    async def _execute_trade(self, signal: TradeSignal):
        """Executa uma única operação de trade."""
        entry_value = self.bot_config.get('entry_value', 1.0)
        signal_id = await self.supabase.insert_trade_signal(signal)
        if not signal_id:
            await self.logger('ERROR', f"[{signal.asset}] Falha ao registrar sinal. A operação não será executada.")
            return

        await self.logger('INFO', f"[{signal.asset}] A executar ordem {signal.direction.upper()} com valor de {entry_value}...")
        order_id = await self.exnova.execute_trade(entry_value, signal.asset, signal.direction, 1)
        
        if order_id:
            await self.logger('SUCCESS', f"[{signal.asset}] Ordem {order_id} (sinal ID: {signal_id}) enviada. A aguardar resultado.")
            active_trade = ActiveTrade(order_id=order_id, signal_id=signal_id, asset=signal.asset)
            await self.trade_queue.put(active_trade)
        else:
            await self.logger('ERROR', f"[{signal.asset}] Falha na execução da ordem na Exnova.")
            await self.supabase.update_trade_result(signal_id, "ERROR")

    async def _result_checker_loop(self):
        """Loop de fundo que verifica o resultado das operações ativas."""
        while self.is_running:
            trade = await self.trade_queue.get()
            await self.logger('INFO', f"[{trade.asset}] A verificar resultado para a ordem {trade.order_id}...")
            
            result = None
            max_retries = 15 # Tenta por ~75 segundos
            for _ in range(max_retries):
                result = await self.exnova.check_trade_result(trade.order_id)
                if result:
                    break
                await asyncio.sleep(5)

            if result:
                await self.logger('SUCCESS' if result == 'WIN' else 'ERROR', f"[{trade.asset}] Resultado recebido para a ordem {trade.order_id}: {result}")
                await self.supabase.update_trade_result(trade.signal_id, result)
            else:
                await self.logger('WARNING', f"[{trade.asset}] Não foi possível obter o resultado para a ordem {trade.order_id} após várias tentativas.")
                await self.supabase.update_trade_result(trade.signal_id, "TIMEOUT")
            
            self.trade_queue.task_done()
