import asyncio
import time
import traceback
from datetime import datetime
from typing import List, Dict, Optional

from config import settings
from services.exnova_service import AsyncExnovaService
from services.supabase_service import SupabaseService
from analysis.strategy import STRATEGIES
from analysis.technical import get_m15_sr_zones
from core.data_models import TradeSignal, ActiveTrade, Candle

class TradingBot:
    def __init__(self):
        self.supabase = SupabaseService(settings.SUPABASE_URL, settings.SUPABASE_KEY)
        self.exnova = AsyncExnovaService(settings.EXNOVA_EMAIL, settings.EXNOVA_PASSWORD)
        self.is_running = True
        self.bot_config: Dict = {}
        self.trade_queue = asyncio.Queue()
        self.cooldown_assets = set()
        self.martingale_state: Dict[str, Dict] = {}
        self.current_cycle_trades: List[Dict] = []
        self.trade_semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_TRADES)
        self.active_assets: List[str] = []

    async def logger(self, level: str, message: str):
        print(f"[{level.upper()}] {message}", flush=True)
        await self.supabase.insert_log(level, message)

    async def _backtest_strategy(self, strategy, m1_candles: List[Candle], m15_candles: List[Candle]) -> Dict:
        wins, losses = 0, 0
        if len(m1_candles) < 21:
            return {'win_rate': 0, 'total_trades': 0}

        for i in range(20, len(m1_candles) - 1):
            historical_slice = m1_candles[:i+1]
            outcome_candle = m1_candles[i+1]

            resistance, support = get_m15_sr_zones(m15_candles)
            m15_zones = {'resistance': resistance, 'support': support}

            direction = strategy.analyze(historical_slice, m15_zones)
            if not direction:
                continue

            if direction == "call" and outcome_candle.close > historical_slice[-1].close:
                wins += 1
            elif direction == "call":
                losses += 1
            elif direction == "put" and outcome_candle.close < historical_slice[-1].close:
                wins += 1
            else:
                losses += 1

        total = wins + losses
        win_rate = (wins / total * 100) if total > 0 else 0
        return {'win_rate': win_rate, 'total_trades': total}

    async def _catalog_and_select_assets(self):
        await self.logger('INFO', "Iniciando fase de catalogação de ativos...")
        all_assets = await self.exnova.get_open_assets()

        best_assets = set()
        tasks = [self._analyze_asset_performance(asset) for asset in all_assets]
        results = await asyncio.gather(*tasks)

        for asset, strategy_name, performance in results:
            if performance and performance['win_rate'] >= 85:
                await self.logger(
                    'SUCCESS',
                    f"Ativo qualificado: {asset} com estratégia {strategy_name} ({performance['win_rate']:.2f}% de assertividade)."
                )
                best_assets.add(asset)

        self.active_assets = list(best_assets)
        if not self.active_assets:
            await self.logger('WARNING', "Nenhum ativo atingiu a meta de 85% de assertividade. O bot irá aguardar.")
        else:
            await self.logger('INFO', f"Catalogação concluída. Ativos selecionados para operar: {self.active_assets}")

    async def _analyze_asset_performance(self, asset: str):
        clean_asset_name = asset.split('-')[0]

        m1_candles_task = self.exnova.get_historical_candles(clean_asset_name, 60, 300)
        m15_candles_task = self.exnova.get_historical_candles(clean_asset_name, 900, 20)
        m1_candles, m15_candles = await asyncio.gather(m1_candles_task, m15_candles_task)

        if len(m1_candles) < 50 or not m15_candles:
            return asset, None, None

        for strategy in STRATEGIES:
            performance = await self._backtest_strategy(strategy, m1_candles, m15_candles)
            await self.supabase.update_asset_performance(
                asset=clean_asset_name,
                strategy=strategy.name,
                timeframe=1,
                win_rate=performance['win_rate'],
                total_trades=performance['total_trades']
            )
            return asset, strategy.name, performance
        return asset, None, None

    async def run(self):
        await self.logger('INFO', 'Bot a iniciar...')
        await self.exnova.connect()
        await self.logger('SUCCESS', "Conexão com a Exnova estabelecida.")

        asyncio.create_task(self._result_checker_loop())

        while self.is_running:
            try:
                self.bot_config = await self.supabase.get_bot_config()
                if self.bot_config.get('status') == 'RUNNING':
                    mode = self.bot_config.get('operation_mode', 'CONSERVADOR')
                    if mode == 'CONSERVADOR':
                        await self._run_conservative_cycle()
                    else:
                        await self.logger('INFO', "Bot em modo AGRESSIVO. A iniciar ciclo de negociação...")
                        await self.trading_loop(use_all_assets=True)
                else:
                    await self.logger('INFO', 'Bot em modo PAUSADO. A aguardar...')
                    await asyncio.sleep(15)
            except Exception as e:
                await self.logger('ERROR', f"Erro fatal no loop principal: {e}")
                traceback.print_exc()
                await asyncio.sleep(30)

    async def _run_conservative_cycle(self):
        await self._catalog_and_select_assets()

        if not self.active_assets:
            await asyncio.sleep(300)
            return

        await self.logger('INFO', "Iniciando ciclo de negociação de 5 minutos com os melhores ativos.")
        self.current_cycle_trades = []
        await self.trading_loop(use_all_assets=False, duration_minutes=5)

        wins = len([t for t in self.current_cycle_trades if t['result'] == 'WIN'])
        losses = len([t for t in self.current_cycle_trades if t['result'] == 'LOSS'])
        total = wins + losses
        win_rate = (wins / total * 100) if total > 0 else 0

        await self.logger(
            'INFO',
            f"Ciclo de 5 minutos concluído. Performance: {wins} WINS, {losses} LOSSES ({win_rate:.2f}%)."
        )

        if win_rate < 70:
            await self.logger('WARNING', "Performance do ciclo abaixo da meta. A recatalogar para encontrar melhores ativos.")
        else:
            await self.logger('SUCCESS', "Performance do ciclo acima da meta. A continuar com os mesmos ativos.")
            await asyncio.sleep(60)

    async def trading_loop(self, use_all_assets: bool, duration_minutes: Optional[int] = None):
        await self.exnova.change_balance(self.bot_config.get('account_type', 'PRACTICE'))

        assets = self.active_assets if not use_all_assets else await self.exnova.get_open_assets()
        assets = [a for a in assets if a not in self.cooldown_assets]
        assets = assets[:settings.MAX_ASSETS_TO_MONITOR]

        if not assets:
            await self.logger('INFO', "Nenhum ativo disponível para negociar neste ciclo.")
            await asyncio.sleep(60)
            return

        await self.logger('INFO', f"Ativos a serem monitorizados: {assets}")
        tasks = [asyncio.create_task(self._process_asset_task(a)) for a in assets]

        try:
            timeout = duration_minutes * 60 if duration_minutes else 55
            await asyncio.wait(tasks, timeout=timeout)
        finally:
            for t in tasks:
                if not t.done():
                    t.cancel()

    async def _wait_for_next_candle(self):
        now = datetime.now()
        wait_time = (60 - now.second) + 2 if now.second > 2 else 2 - now.second
        await asyncio.sleep(wait_time)

    async def _process_asset_task(self, full_asset_name: str):
        try:
            await self._wait_for_next_candle()
            clean = full_asset_name.split('-')[0]

            m1_task = self.exnova.get_historical_candles(clean, 60, 20)
            m15_task = self.exnova.get_historical_candles(clean, 900, 4)
            m1_c, m15_c = await asyncio.gather(m1_task, m15_task)

            if not m1_c or not m15_c:
                return

            resistance, support = get_m15_sr_zones(m15_c)
            zones = {'resistance': resistance, 'support': support}

            for strategy in STRATEGIES:
                dir = strategy.analyze(m1_c, zones)
                if dir:
                    await self.logger('SUCCESS', f"[{full_asset_name}] Sinal confirmado! Direção: {dir.upper()}, Estratégia: {strategy.name}")
                    self.cooldown_assets.add(full_asset_name)
                    asyncio.create_task(self._remove_from_cooldown(full_asset_name, 300))
                    last = m1_c[-1]
                    signal = TradeSignal(
                        pair=clean,
                        direction=dir,
                        strategy=strategy.name,
                        setup_candle_open=last.open,
                        setup_candle_high=last.max,
                        setup_candle_low=last.min,
                        setup_candle_close=last.close
                    )
                    asyncio.create_task(self._execute_trade(signal, full_asset_name))
                    break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            await self.logger('ERROR', f"Erro ao processar ativo {full_asset_name}: {e}")

    async def _remove_from_cooldown(self, asset: str, delay: int):
        await asyncio.sleep(delay)
        self.cooldown_assets.discard(asset)
        await self.logger('INFO', f"[{asset}] Cooldown terminado.")

    def _get_entry_value(self, asset: str) -> float:
        base = self.bot_config.get('entry_value', 1.0)
        if not self.bot_config.get('use_martingale', False):
            return base
        mg = self.martingale_state.get(asset, {'level': 0, 'last_value': base})
        if mg['level'] == 0:
            return base
        next_val = mg['last_value'] * self.bot_config.get('martingale_factor', 2.3)
        return round(next_val, 2)

    async def _execute_trade(self, signal: TradeSignal, full_asset_name: str):
        await self.logger('INFO', f"[{signal.pair}] Sinal na fila, a aguardar por uma vaga de execução...")
        async with self.trade_semaphore:
            await self.logger('SUCCESS', f"[{signal.pair}] Vaga de execução obtida.")
            try:
                entry = self._get_entry_value(signal.pair)
                sid = await self.supabase.insert_trade_signal(signal)
                if not sid:
                    await self.logger('ERROR', f"[{signal.pair}] Falha ao registrar sinal.")
                    return

                order_id = await self.exnova.execute_trade(entry, full_asset_name, signal.direction, 1)
                if order_id:
                    await self.logger('SUCCESS', f"[{signal.pair}] Ordem {order_id} enviada.")
                    at = ActiveTrade(order_id=str(order_id), signal_id=sid, pair=signal.pair, entry_value=entry)
                    await self.trade_queue.put(at)
                else:
                    await self.logger('ERROR', f"[{signal.pair}] Falha na execução da ordem.")
                    await self.supabase.update_trade_result(sid, "REJEITADO")
            except Exception as e:
                await self.logger('ERROR', f"Exceção em _execute_trade: {e}")

    async def _result_checker_loop(self):
        while self.is_running:
            try:
                trade = await self.trade_queue.get()
                asyncio.create_task(self._check_and_process_single_trade(trade))
                self.trade_queue.task_done()
            except Exception as e:
                await self.logger('ERROR', f"Erro no loop de verificação: {e}")

    async def _check_and_process_single_trade(self, trade: ActiveTrade):
        try:
            # aguarda fechamento da vela de expiração
            await asyncio.sleep((60 - datetime.now().second) + 2)

            # busca últimas 2 velas M1
            candles = await self.exnova.get_historical_candles(trade.pair, 60, 2)
            entry_close = candles[-2].close
            outcome_close = candles[-1].close

            # determina resultado
            if trade.direction.upper() == "CALL":
                result = "WIN" if outcome_close > entry_close else "LOSS"
            else:
                result = "WIN" if outcome_close < entry_close else "LOSS"

            # registra resultado
            self.current_cycle_trades.append({'result': result})
            mg_level = self.martingale_state.get(trade.pair, {}).get('level', 0)
            await self.supabase.update_trade_result(trade.signal_id, result, mg_level)
            await self.logger('SUCCESS', f"[{trade.pair}] Resultado determinado por candle: {result}.")

            # atualiza martingale
            self._update_martingale_state(trade.pair, result, trade.entry_value)
        except Exception as e:
            await self.logger('ERROR', f"Erro calculando resultado por candle: {e}")
        finally:
            self.trade_semaphore.release()
            await self.logger('INFO', f"[{trade.pair}] Vaga de execução libertada.")

    def _update_martingale_state(self, asset: str, result: str, last_value: float):
        if not self.bot_config.get('use_martingale', False):
            return
        max_levels = self.bot_config.get('martingale_levels', 2)
        curr = self.martingale_state.get(asset, {}).get('level', 0)
        if result == 'WIN':
            self.martingale_state[asset] = {'level': 0, 'last_value': self.bot_config.get('entry_value', 1.0)}
            asyncio.create_task(self.logger('INFO', f"[{asset}] Martingale resetado."))
        elif result == 'LOSS':
            if curr < max_levels:
                self.martingale_state[asset] = {'level': curr + 1, 'last_value': last_value}
                asyncio.create_task(self.logger('WARNING', f"[{asset}] LOSS. Martingale nível {curr + 1}."))
            else:
                self.martingale_state[asset] = {'level': 0, 'last_value': self.bot_config.get('entry_value', 1.0)}
                asyncio.create_task(self.logger('ERROR', f"[{asset}] Limite de Martingale atingido. Reset."))
