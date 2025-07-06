import asyncio
import time
import traceback
from datetime import datetime, timedelta
from typing import Dict

from config import settings
from services.exnova_service import AsyncExnovaService
from services.supabase_service import SupabaseService
from analysis.technical import get_m15_sr_zones, get_h1_sr_zones
from analysis import technical_indicators as ti
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
        ts = datetime.utcnow().isoformat()
        print(f"[{ts}] [{level.upper()}] {message}", flush=True)
        await self.supabase.insert_log(level, message)

    async def run(self):
        await self.logger('INFO', 'Bot a iniciar com LÓGICA DE EXECUÇÃO PROFISSIONAL...')
        await self.exnova.connect()
        
        while self.is_running:
            try:
                self.bot_config = await self.supabase.get_bot_config()
                status = self.bot_config.get('status', 'PAUSED')

                if status == 'RUNNING' and not self.is_trade_active:
                    await self.trading_cycle()
                else:
                    if status != 'RUNNING':
                        await self.logger('INFO', "Bot PAUSADO. Aguardando status 'RUNNING'.")
                    elif self.is_trade_active:
                         await self.logger('INFO', "Operação em andamento. Aguardando resultado...")
                
                await asyncio.sleep(1) # Verifica o status a cada segundo

            except Exception as e:
                await self.logger('ERROR', f"Loop principal falhou: {e}")
                traceback.print_exc()
                await asyncio.sleep(30)

    async def trading_cycle(self):
        now = datetime.utcnow()
        # A análise ocorre apenas nos primeiros 3 segundos de cada minuto.
        if now.second > 3:
            return

        # Análise de M5 tem prioridade no início de um bloco de 5 minutos
        if now.minute % 5 == 0:
            asyncio.create_task(self.run_analysis_for_timeframe(300, 5))
        # Análise de M1 ocorre em todos os outros minutos
        else:
            asyncio.create_task(self.run_analysis_for_timeframe(60, 1))

    async def run_analysis_for_timeframe(self, timeframe_seconds: int, expiration_minutes: int):
        await self.logger('INFO', f"Iniciando ciclo de análise para M{expiration_minutes}...")
        await self.exnova.change_balance(self.bot_config.get('account_type', 'PRACTICE'))
        assets = await self.exnova.get_open_assets()
        
        tasks = [self._analyze_asset(asset, timeframe_seconds, expiration_minutes) for asset in assets[:settings.MAX_ASSETS_TO_MONITOR]]
        await asyncio.gather(*tasks)

    async def _analyze_asset(self, full_name: str, timeframe_seconds: int, expiration_minutes: int):
        try:
            if self.is_trade_active: return
            base = full_name.split('-')[0]
            
            if expiration_minutes == 1:
                analysis_candles, sr_candles = await asyncio.gather(
                    self.exnova.get_historical_candles(base, 60, 200),
                    self.exnova.get_historical_candles(base, 900, 100),
                )
                if not analysis_candles or not sr_candles: return
                res, sup = get_m15_sr_zones(sr_candles)
            elif expiration_minutes == 5:
                analysis_candles, sr_candles = await asyncio.gather(
                    self.exnova.get_historical_candles(base, 300, 200),
                    self.exnova.get_historical_candles(base, 3600, 100),
                )
                if not analysis_candles or not sr_candles: return
                res, sup = get_h1_sr_zones(sr_candles)
            else:
                return

            signal_candle = analysis_candles[-2]
            
            confluences = {'call': [], 'put': []}
            zones = {'resistance': res, 'support': sup}
            
            if (sr_signal := ti.check_price_near_sr(signal_candle, zones)):
                confluences[sr_signal].append("SR_Zone")
            if (candle_signal := ti.check_candlestick_pattern(analysis_candles)):
                confluences[candle_signal].append("Candle_Pattern")
            if (rsi_signal := ti.check_rsi_condition(analysis_candles)):
                confluences[rsi_signal].append("RSI_Condition")
            
            final_direction = None
            if len(confluences['call']) >= 2: final_direction = 'call'
            elif len(confluences['put']) >= 2: final_direction = 'put'
            
            if final_direction:
                if not ti.validate_reversal_candle(signal_candle, final_direction):
                    await self.logger('DEBUG', f"Sinal em {base} rejeitado devido a pavio/corpo fraco.")
                    return

                if self.is_trade_active: return
                self.is_trade_active = True

                strategy_name = f"M{expiration_minutes}_" + ', '.join(confluences[final_direction])
                await self.logger('SUCCESS', f"SINAL VÁLIDO! Dir: {final_direction.upper()}. Conf: {strategy_name}")
                
                signal = TradeSignal(pair=base, direction=final_direction, strategy=strategy_name,
                                     setup_candle_open=signal_candle.open, setup_candle_high=signal_candle.max,
                                     setup_candle_low=signal_candle.min, setup_candle_close=signal_candle.close)
                
                trade_expiration = 4 if expiration_minutes == 5 else expiration_minutes
                await self._execute_and_wait(signal, full_name, trade_expiration)

        except Exception as e:
            await self.logger('ERROR', f"Erro em _analyze_asset({full_name}, M{expiration_minutes}): {e}")
            traceback.print_exc()

    def _get_entry_value(self, asset: str) -> float:
        base = self.bot_config.get('entry_value', settings.ENTRY_VALUE)
        if not self.bot_config.get('use_martingale', False): return base
        state = self.martingale_state.get(asset, {'level': 0, 'last_value': base})
        if state['level'] == 0: return base
        return round(state['last_value'] * self.bot_config.get('martingale_factor', 2.3), 2)

    async def _execute_and_wait(self, signal: TradeSignal, full_name: str, expiration_minutes: int):
        try:
            bal_before = await self.exnova.get_current_balance()
            entry_value = self._get_entry_value(signal.pair)
            sid = await self.supabase.insert_trade_signal(signal)
            if not sid:
                self.is_trade_active = False
                return

            order_id = await self.exnova.execute_trade(entry_value, full_name, signal.direction.lower(), expiration_minutes)
            await self.logger('INFO', f"Ordem {order_id} enviada. Valor: {entry_value}. Exp: {expiration_minutes} min. Aguardando...")
            
            await asyncio.sleep(expiration_minutes * 60 + 60)

            bal_after = await self.exnova.get_current_balance()
            
            if bal_before is None or bal_after is None: result = 'UNKNOWN'
            else:
                delta = bal_after - bal_before
                result = 'WIN' if delta > 0 else 'LOSS' if delta < 0 else 'DRAW'
            await self.logger('SUCCESS' if result == 'WIN' else 'ERROR', f"Resultado: {result}. ΔSaldo = {delta:.2f}")

            mg_lv = self.martingale_state.get(signal.pair, {}).get('level', 0)
            await self.supabase.update_trade_result(sid, result, mg_lv)
            await self.supabase.update_current_balance(bal_after or 0.0)

            if self.bot_config.get('use_martingale', False):
                if result == 'WIN': self.martingale_state[signal.pair] = {'level': 0, 'last_value': entry_value}
                elif result == 'LOSS':
                    lvl = mg_lv + 1
                    max_lv = self.bot_config.get('martingale_levels', 2)
                    if lvl <= max_lv: self.martingale_state[signal.pair] = {'level': lvl, 'last_value': entry_value}
                    else: self.martingale_state[signal.pair] = {'level': 0, 'last_value': self.bot_config.get('entry_value', entry_value)}
        finally:
            self.is_trade_active = False
            await self.logger('INFO', 'Ciclo de operação concluído. Pronto para nova análise.')
