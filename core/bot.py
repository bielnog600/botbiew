# core/bot.py
import asyncio
import time
import traceback
from datetime import datetime, timedelta
from typing import List, Dict

from config import settings
from services.exnova_service import AsyncExnovaService
from services.supabase_service import SupabaseService
from analysis.strategy import STRATEGIES
from analysis.technical import calculate_volatility
from core.data_models import TradeSignal, ActiveTrade, Candle

class TradingBot:
    def __init__(self):
        self.supabase = SupabaseService(settings.SUPABASE_URL, settings.SUPABASE_KEY)
        self.exnova = AsyncExnovaService(settings.EXNOVA_EMAIL, settings.EXNOVA_PASSWORD)
        self.active_assets: List[str] = []
        self.trade_queue = asyncio.Queue()
        self.is_running = True
        self.bot_config = {}
        self.martingale_state: Dict[str, Dict] = {}
        self.current_cycle_trades: List[Dict] = [] # Para rastrear wins/losses do ciclo atual

    async def logger(self, level: str, message: str):
        print(f"[{level.upper()}] {message}")
        await self.supabase.insert_log(level, message)

    async def _backtest_strategy(self, strategy, candles: List[Candle]) -> Dict:
        """Simula uma estratégia em dados históricos para calcular a assertividade."""
        wins, losses = 0, 0
        if len(candles) < 21: # Precisa de velas suficientes para o histórico e a próxima vela
            return {'win_rate': 0, 'total_trades': 0}

        for i in range(20, len(candles) - 1):
            historical_slice = candles[:i+1] # Analisa até a vela atual
            # A vela seguinte é usada para determinar o resultado
            next_candle = candles[i+1] 
            
            direction = strategy.analyze(historical_slice)
            if not direction:
                continue

            # Simula o resultado
            if direction == "call" and next_candle.close > historical_slice[-1].close:
                wins += 1
            elif direction == "call" and next_candle.close <= historical_slice[-1].close:
                losses += 1
            elif direction == "put" and next_candle.close < historical_slice[-1].close:
                wins += 1
            elif direction == "put" and next_candle.close >= historical_slice[-1].close:
                losses += 1
        
        total = wins + losses
        win_rate = (wins / total * 100) if total > 0 else 0
        return {'win_rate': win_rate, 'total_trades': total}

    async def _catalog_and_select_assets(self):
        """Cataloga todos os ativos e seleciona os melhores com base na performance."""
        await self.logger('INFO', "Iniciando fase de catalogação de ativos...")
        all_assets = await self.exnova.get_open_assets()
        
        best_assets = set()
        
        for asset in all_assets:
            clean_asset_name = asset.split('-')[0]
            candles = await self.exnova.get_historical_candles(clean_asset_name, 60, 300)
            if len(candles) < 50: continue

            for strategy in STRATEGIES:
                performance = await self._backtest_strategy(strategy, candles)
                await self.supabase.update_asset_performance(
                    asset=clean_asset_name,
                    strategy=strategy.name,
                    win_rate=performance['win_rate'],
                    total_trades=performance['total_trades']
                )
                
                if performance['win_rate'] >= 85:
                    await self.logger('SUCCESS', f"Ativo qualificado: {asset} com estratégia {strategy.name} ({performance['win_rate']:.2f}% de assertividade).")
                    best_assets.add(asset)

        self.active_assets = list(best_assets)
        if not self.active_assets:
            await self.logger('WARNING', "Nenhum ativo atingiu a meta de 85% de assertividade. O bot irá aguardar.")
        else:
            await self.logger('INFO', f"Catalogação concluída. Ativos selecionados para operar: {self.active_assets}")

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
                    if operation_mode == 'CONSERVADOR':
                        await self._run_conservative_cycle()
                    else:
                        await self.logger('INFO', f"Bot em modo AGRESSIVO. A iniciar ciclo de negociação...")
                        await self.trading_loop(use_all_assets=True, duration_minutes=None)
                else:
                    await self.logger('INFO', 'Bot em modo PAUSADO. A aguardar...')
                    await asyncio.sleep(15)

            except Exception as e:
                await self.logger('ERROR', f"Erro fatal no loop principal: {e}")
                traceback.print_exc()
                await asyncio.sleep(30)

    async def _run_conservative_cycle(self):
        """Executa o ciclo completo do modo conservador."""
        await self._catalog_and_select_assets()
        
        if not self.active_assets:
            await asyncio.sleep(300)
            return

        await self.logger('INFO', f"Iniciando ciclo de negociação de 5 minutos com os melhores ativos.")
        self.current_cycle_trades = []
        await self.trading_loop(use_all_assets=False, duration_minutes=5)

        wins = len([t for t in self.current_cycle_trades if t['result'] == 'WIN'])
        losses = len([t for t in self.current_cycle_trades if t['result'] == 'LOSS'])
        total = wins + losses
        win_rate = (wins / total * 100) if total > 0 else 100

        await self.logger('INFO', f"Ciclo de 5 minutos concluído. Performance: {wins} WINS, {losses} LOSSES ({win_rate:.2f}%).")

        if win_rate < 70:
            await self.logger('WARNING', "Performance do ciclo abaixo da meta. A recatalogar para encontrar melhores ativos.")
        else:
            await self.logger('SUCCESS', "Performance do ciclo acima da meta. A continuar com os mesmos ativos.")
            await asyncio.sleep(60)

    async def trading_loop(self, use_all_assets: bool, duration_minutes: Optional[int]):
        """Executa o loop de negociação principal."""
        account_type = self.bot_config.get('account_type', 'PRACTICE')
        await self.logger('INFO', f"A usar a conta: {account_type}")
        await self.exnova.change_balance(account_type)

        current_balance = await self.exnova.get_current_balance()
        if current_balance is not None:
            await self.supabase.update_current_balance(current_balance)

        if use_all_assets:
            self.active_assets = await self.exnova.get_open_assets()
            self.active_assets = self.active_assets[:settings.MAX_CONCURRENT_ASSETS]
        
        trading_tasks = [self._process_asset_task(asset) for asset in self.active_assets]
        result_checker_task = asyncio.create_task(self._result_checker_loop())
        
        all_tasks = trading_tasks + [result_checker_task]
        
        try:
            # Executa as tarefas pelo tempo definido ou indefinidamente
            await asyncio.wait(all_tasks, timeout=duration_minutes * 60 if duration_minutes else None, return_when=asyncio.FIRST_COMPLETED)
        finally:
            # Garante que todas as tarefas são canceladas ao sair do loop
            for task in all_tasks:
                task.cancel()

    async def _wait_for_entry_time(self):
        """Espera até o segundo 58 para analisar a vela que está a fechar."""
        now = datetime.now()
        second = now.second
        target_second = 58
        if second < target_second:
            wait_time = target_second - second
        else:
            wait_time = (60 - second) + target_second
        await asyncio.sleep(wait_time)

    async def _process_asset_task(self, full_asset_name: str):
        clean_asset_name = full_asset_name.split('-')[0]
        operation_mode = self.bot_config.get('operation_mode', 'CONSERVADOR')
        volatility_threshold = 0.6 if operation_mode == 'CONSERVADOR' else 0.85

        while True:
            try:
                await self._wait_for_entry_time()
                candles = await self.exnova.get_historical_candles(clean_asset_name, 60, 100)
                if not candles: continue

                volatility = calculate_volatility(candles, lookback=10)
                if volatility > volatility_threshold: continue
                
                for strategy in STRATEGIES:
                    direction = strategy.analyze(candles)
                    if direction:
                        await self.logger('SUCCESS', f"[{full_asset_name}] Sinal encontrado! Direção: {direction.upper()}, Estratégia: {strategy.name}")
                        signal = TradeSignal(pair=clean_asset_name, direction=direction, strategy=strategy.name, volatility_score=volatility)
                        asyncio.create_task(self._execute_trade(signal, full_asset_name))
                        break
            except asyncio.CancelledError:
                break
            except Exception as e:
                await self.logger('ERROR', f"Erro ao processar o ativo {full_asset_name}: {e}")
                traceback.print_exc()
                await asyncio.sleep(30)

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
            signal_id = await self.supabase.insert_trade_signal(signal)
            if not signal_id:
                await self.logger('ERROR', f"[{signal.pair}] Falha ao registrar sinal.")
                return

            order_id = await self.exnova.execute_trade(entry_value, full_asset_name, signal.direction, 1)
            if order_id:
                await self.logger('SUCCESS', f"[{signal.pair}] Ordem {order_id} (sinal ID: {signal_id}) enviada.")
                active_trade = ActiveTrade(order_id=str(order_id), signal_id=signal_id, pair=signal.pair, entry_value=entry_value)
                await self.trade_queue.put(active_trade)
            else:
                await self.logger('ERROR', f"[{signal.pair}] Falha na execução da ordem na Exnova para '{full_asset_name}'.")
                await self.supabase.update_trade_result(signal_id, "ERROR")
        except Exception as e:
            await self.logger('ERROR', f"Exceção não tratada em _execute_trade para {signal.pair}: {e}")
            traceback.print_exc()

    async def _result_checker_loop(self):
        while self.is_running:
            try:
                trade = await asyncio.wait_for(self.trade_queue.get(), timeout=1.0)
                result = None
                for _ in range(15):
                    result = await self.exnova.check_trade_result(trade.order_id)
                    if result: break
                    await asyncio.sleep(5)
                
                if result:
                    await self.logger('SUCCESS' if result == 'WIN' else 'ERROR', f"[{trade.pair}] Resultado da ordem {trade.order_id}: {result}")
                    await self.supabase.update_trade_result(trade.signal_id, result)
                    self.current_cycle_trades.append({'result': result})
                    self._update_martingale_state(trade.pair, result, trade.entry_value)
                else:
                    await self.logger('WARNING', f"[{trade.pair}] Timeout ao obter resultado da ordem {trade.order_id}.")
                    await self.supabase.update_trade_result(trade.signal_id, "TIMEOUT")
                
                self.trade_queue.task_done()
            except asyncio.TimeoutError:
                continue # Nenhuma operação na fila, continua o loop
            except Exception as e:
                await self.logger('ERROR', f"Erro no loop de verificação de resultados: {e}")

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
