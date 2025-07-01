# core/bot.py
import asyncio
import time
from typing import List, Dict
from config import settings
from services.exnova_service import AsyncExnovaService
from services.supabase_service import SupabaseService
from analysis.strategy import STRATEGIES
from analysis.technical import calculate_volatility
from core.data_models import TradeSignal, ActiveTrade

class TradingBot:
    def __init__(self):
        self.exnova = AsyncExnovaService(settings.EXNOVA_EMAIL, settings.EXNOVA_PASSWORD)
        self.supabase = SupabaseService(settings.SUPABASE_URL, settings.SUPABASE_KEY)
        self.active_assets: List[str] = []
        self.trade_queue = asyncio.Queue()
        self.is_running = True

    async def run(self):
        """Ponto de entrada principal para a execução do bot."""
        await self.exnova.connect()
        
        print("Iniciando fase de catalogação de ativos...")
        # await self._catalog_assets() # Descomente para rodar a catalogação
        self.active_assets = await self.exnova.get_open_assets() # Temporário: pega todos
        self.active_assets = self.active_assets[:settings.MAX_CONCURRENT_ASSETS]
        print(f"Ativos selecionados para operar: {self.active_assets}")

        # print("Iniciando modo de aprendizagem...")
        # await self._learning_mode()

        print("Iniciando loop de negociação e verificação de resultados...")
        trading_tasks = [self._process_asset_task(asset) for asset in self.active_assets]
        result_checker_task = asyncio.create_task(self._result_checker_loop())
        
        await asyncio.gather(*trading_tasks, result_checker_task)

    async def _process_asset_task(self, asset: str):
        """Tarefa assíncrona que monitora e opera um único ativo."""
        print(f"Iniciando monitoramento para o ativo: {asset}")
        while self.is_running:
            try:
                candles = await self.exnova.get_historical_candles(asset, 60, 100)
                if not candles:
                    await asyncio.sleep(5)
                    continue

                volatility = calculate_volatility(candles, lookback=10)
                
                # FIX: Adiciona um log de "pulsação" para cada ciclo de análise
                print(f"[{time.strftime('%H:%M:%S')}] {asset}: Analisando {len(candles)} velas. Volatilidade: {volatility:.2f}")

                if volatility > 0.6: # Threshold de exemplo
                    # print(f"Ativo {asset} muito volátil ({volatility:.2f}), pulando ciclo.")
                    await asyncio.sleep(60)
                    continue
                
                for strategy in STRATEGIES:
                    direction = strategy.analyze(candles)
                    if direction:
                        print(f"Sinal gerado para {asset}: {direction.upper()} pela estratégia {strategy.name}")
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
            except Exception as e:
                print(f"Erro ao processar o ativo {asset}: {e}")
                await asyncio.sleep(30)

    async def _execute_trade(self, signal: TradeSignal):
        """Executa uma única operação de trade."""
        signal_id = await self.supabase.insert_trade_signal(signal)
        if not signal_id:
            print(f"Falha ao registrar sinal para {signal.asset}, a operação não será executada.")
            return

        print(f"Executando ordem {signal.direction.upper()} para {signal.asset}...")
        order_id = await self.exnova.execute_trade(1.0, signal.asset, signal.direction, 1)
        
        if order_id:
            print(f"Ordem {order_id} para o sinal {signal_id} enviada. Aguardando resultado.")
            active_trade = ActiveTrade(order_id=order_id, signal_id=signal_id, asset=signal.asset)
            await self.trade_queue.put(active_trade)
        else:
            await self.supabase.update_trade_result(signal_id, "ERROR")

    async def _result_checker_loop(self):
        """Loop de fundo que verifica o resultado das operações ativas."""
        while self.is_running:
            trade = await self.trade_queue.get()
            print(f"Verificando resultado para a ordem {trade.order_id}...")
            
            result = None
            while result is None:
                await asyncio.sleep(5)
                result = await self.exnova.check_trade_result(trade.order_id)

            print(f"Resultado recebido para a ordem {trade.order_id}: {result}")
            await self.supabase.update_trade_result(trade.signal_id, result)
            self.trade_queue.task_done()
