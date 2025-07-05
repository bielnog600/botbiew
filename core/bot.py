import asyncio
import time
import traceback
from datetime import datetime, timedelta
from typing import Dict

from config import settings
from services.exnova_service import AsyncExnovaService
from services.supabase_service import SupabaseService
from analysis.technical import get_m15_sr_zones, get_h1_sr_zones # Supondo que você crie get_h1_sr_zones
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
        await self.logger('DEBUG', f"Configured MAX_ASSETS_TO_MONITOR = {settings.MAX_ASSETS_TO_MONITOR}")
        await self.logger('INFO', 'Bot a iniciar com LÓGICA MULTI-TIMEFRAME (M1 & M5)...')
        # ... (resto do método run permanece o mesmo)
        status = await self.exnova.connect()
        if status:
            await self.logger('SUCCESS', 'Conexão com a Exnova estabelecida.')
        else:
            await self.logger('ERROR', 'Falha na conexão com a Exnova.')
            return

        bal = await self.exnova.get_current_balance()
        if bal is not None:
            await self.supabase.update_current_balance(bal)
            await self.logger('INFO', f"Saldo inicial: {bal:.2f}")

        while self.is_running:
            try:
                bal = await self.exnova.get_current_balance()
                if bal is not None:
                    await self.supabase.update_current_balance(bal)
                    
                self.bot_config = await self.supabase.get_bot_config()
                status = self.bot_config.get('status', 'PAUSED')
                
                if status == 'RUNNING' and not self.is_trade_active:
                    await self.trading_cycle() # A lógica de tempo está agora dentro do trading_cycle
                else:
                    if status != 'RUNNING':
                        await self.logger('INFO', f"Bot PAUSADO. Aguardando status 'RUNNING'.")
                    await asyncio.sleep(settings.BOT_CONFIG_POLL_INTERVAL)
            except Exception as e:
                await self.logger('ERROR', f"Loop principal falhou: {e}")
                traceback.print_exc()
                await asyncio.sleep(settings.BOT_CONFIG_POLL_INTERVAL)

    # MODIFICADO: Lógica para decidir entre análise M1 e M5
    async def trading_cycle(self):
        """
        Verifica o tempo atual e decide se executa um ciclo de análise para M1, M5 ou ambos.
        """
        now = datetime.utcnow()
        
        # Lógica para M5: Executa a análise no minuto anterior ao fechamento da vela de 5min
        # Ex: nos minutos 4, 9, 14, 19, 24, etc.
        if now.minute % 5 == 4:
            await self.logger('INFO', f"Iniciando ciclo de análise para M5 (Expiração de 5 min)...")
            await self.run_analysis_for_timeframe(timeframe_seconds=300, expiration_minutes=5)

        # Lógica para M1: Executa a cada minuto
        await self.logger('INFO', f"Iniciando ciclo de análise para M1 (Expiração de 1 min)...")
        await self.run_analysis_for_timeframe(timeframe_seconds=60, expiration_minutes=1)

    # NOVO: Método para encapsular a lógica de análise de um timeframe específico
    async def run_analysis_for_timeframe(self, timeframe_seconds: int, expiration_minutes: int):
        """
        Executa um ciclo de análise completo para um dado timeframe.
        """
        if self.is_trade_active:
            await self.logger('INFO', f"Análise para M{expiration_minutes} pulada pois uma operação já está ativa.")
            return

        await self.exnova.change_balance(self.bot_config.get('account_type', 'PRACTICE'))
        assets = await self.exnova.get_open_assets()
        assets = assets[: settings.MAX_ASSETS_TO_MONITOR]
        await self.logger('INFO', f"[M{expiration_minutes}] Ativos para análise: {assets}")

        # Otimiza a entrada para 1.5s antes do fechamento da vela do timeframe
        now = datetime.utcnow()
        next_candle_minute = (now.minute // expiration_minutes + 1) * expiration_minutes
        target_dt = now.replace(second=0, microsecond=0) + timedelta(minutes=(next_candle_minute - now.minute))
        target_dt -= timedelta(seconds=1.5)
        
        wait = max(target_dt.timestamp() - time.time(), 0)
        await self.logger('DEBUG', f"[M{expiration_minutes}] Aguardando {wait:.2f}s até entrada otimizada...")
        await asyncio.sleep(wait)

        for full in assets:
            if self.is_trade_active:
                break
            await self._analyze_asset(full, timeframe_seconds, expiration_minutes)

    # MODIFICADO: O antigo _process_asset agora é parametrizado
    async def _analyze_asset(self, full_name: str, timeframe_seconds: int, expiration_minutes: int):
        """
        Processa um ativo com lógica de confluência para um timeframe específico.
        """
        try:
            base = full_name.split('-')[0]
            
            # MODIFICADO: Catalogação de 500 velas e timeframes de contexto dinâmicos
            primary_candles_count = 500
            context_candles_count = 100

            if expiration_minutes == 1: # Análise M1
                # Contexto de M5 e M15
                m1, m5, m15 = await asyncio.gather(
                    self.exnova.get_historical_candles(base, 60, primary_candles_count),
                    self.exnova.get_historical_candles(base, 300, context_candles_count),
                    self.exnova.get_historical_candles(base, 900, context_candles_count),
                )
                if not m1 or not m5 or not m15: return
                trend_candles = m5
                sr_candles = m15
                analysis_candles = m1
            
            elif expiration_minutes == 5: # Análise M5
                # Contexto de M15 e H1
                m5, m15, h1 = await asyncio.gather(
                    self.exnova.get_historical_candles(base, 300, primary_candles_count),
                    self.exnova.get_historical_candles(base, 900, context_candles_count),
                    self.exnova.get_historical_candles(base, 3600, context_candles_count),
                )
                if not m5 or not m15 or not h1: return
                trend_candles = m15
                sr_candles = h1
                analysis_candles = m5
            else:
                return # Timeframe não suportado

            # --- FILTROS E CONFLUÊNCIAS (a lógica interna permanece a mesma) ---
            # Filtro de Volatilidade (usando as velas de análise principal)
            atr_value = ti.calculate_atr(analysis_candles, period=5)
            # TODO: Você pode querer ajustar os limites de ATR para M1 e M5 separadamente
            min_atr, max_atr = 0.00001, 0.005
            if atr_value is None or not (min_atr < atr_value < max_atr):
                await self.logger('DEBUG', f"[{base}-M{expiration_minutes}] Filtro de volatilidade: Fora dos limites (ATR={atr_value}).")
                return

            # Filtro de Tendência (usando as velas de contexto de tendência)
            trend_ema = ti.calculate_ema(trend_candles, period=5)
            last_price = analysis_candles[-1].close
            trend = 'SIDEWAYS'
            if trend_ema and last_price > trend_ema: trend = 'UPTREND'
            if trend_ema and last_price < trend_ema: trend = 'DOWNTREND'
            
            # Busca por Confluências
            confluences = {'call': [], 'put': []}
            if expiration_minutes == 1:
                res, sup = get_m15_sr_zones(sr_candles)
            else: # M5
                res, sup = get_h1_sr_zones(sr_candles) # Supondo que você crie esta função
            
            zones = {'resistance': res, 'support': sup}
            sr_signal = ti.check_price_near_sr(analysis_candles[-1], zones)
            if sr_signal: confluences[sr_signal].append("SR_Zone")
            
            candle_signal = ti.check_candlestick_pattern(analysis_candles)
            if candle_signal: confluences[candle_signal].append("Candle_Pattern")
            
            rsi_signal = ti.check_rsi_condition(analysis_candles)
            if rsi_signal: confluences[rsi_signal].append("RSI_Condition")

            # Decisão Final
            final_direction = None
            confirmation_threshold = 2
            if len(confluences['call']) >= confirmation_threshold and trend in ['UPTREND', 'SIDEWAYS']:
                final_direction = 'call'
            elif len(confluences['put']) >= confirmation_threshold and trend in ['DOWNTREND', 'SIDEWAYS']:
                final_direction = 'put'
            
            if final_direction:
                strategy_name = f"M{expiration_minutes}_" + ', '.join(confluences[final_direction])
                await self.logger('SUCCESS', f"[{base}-M{expiration_minutes}] SINAL VÁLIDO! Dir: {final_direction.upper()}. Conf: {strategy_name}. Tend: {trend}")
                
                last = analysis_candles[-1]
                signal = TradeSignal(pair=base, direction=final_direction, strategy=strategy_name,
                                     setup_candle_open=last.open, setup_candle_high=last.max,
                                     setup_candle_low=last.min, setup_candle_close=last.close)
                
                # MODIFICADO: Passa o tempo de expiração para o executor
                await self._execute_and_wait(signal, full_name, expiration_minutes)
                return

        except Exception as e:
            await self.logger('ERROR', f"Erro em _analyze_asset({full_name}, M{expiration_minutes}): {e}")
            traceback.print_exc()

    def _get_entry_value(self, asset: str) -> float:
        # Nenhuma mudança necessária aqui
        base = self.bot_config.get('entry_value', settings.ENTRY_VALUE)
        if not self.bot_config.get('use_martingale', False):
            return base
        state = self.martingale_state.get(asset, {'level': 0, 'last_value': base})
        if state['level'] == 0:
            return base
        return round(state['last_value'] * self.bot_config.get('martingale_factor', 2.3), 2)

    # MODIFICADO: Aceita expiration_minutes para expiração e espera dinâmicas
    async def _execute_and_wait(self, signal: TradeSignal, full_name: str, expiration_minutes: int):
        self.is_trade_active = True
        try:
            bal_before = await self.exnova.get_current_balance()
            entry_value = self._get_entry_value(signal.pair)
            sid = await self.supabase.insert_trade_signal(signal)
            if not sid:
                await self.logger('ERROR', f"[{signal.pair}] Falha ao inserir sinal, abortando.")
                self.is_trade_active = False
                return

            # MODIFICADO: Usa o tempo de expiração dinâmico
            order_id = await self.exnova.execute_trade(entry_value, full_name, signal.direction.lower(), expiration_minutes)
            await self.logger('INFO', f"[{signal.pair}] Ordem {order_id} enviada. Valor: {entry_value}. Expiração: {expiration_minutes} min. Aguardando...")
            
            # MODIFICADO: Espera o tempo correto + 5s de buffer
            await asyncio.sleep(expiration_minutes * 60 + 5)

            bal_after = await self.exnova.get_current_balance()
            
            # O resto da lógica de apuração de resultado permanece a mesma
            if bal_before is None or bal_after is None:
                result = 'UNKNOWN'
            else:
                delta = bal_after - bal_before
                if delta > 0: result = 'WIN'
                elif delta < 0: result = 'LOSS'
                else: result = 'DRAW'
            await self.logger('SUCCESS' if result == 'WIN' else 'ERROR', f"[{signal.pair}] Resultado: {result}. ΔSaldo = {delta:.2f}")

            mg_lv = self.martingale_state.get(signal.pair, {}).get('level', 0)
            await self.supabase.update_trade_result(sid, result, mg_lv)
            await self.supabase.update_current_balance(bal_after or 0.0)

            if self.bot_config.get('use_martingale', False):
                # ... (lógica do martingale permanece a mesma)
                if result == 'WIN':
                    self.martingale_state[signal.pair] = {'level': 0, 'last_value': entry_value}
                elif result == 'LOSS':
                    lvl = mg_lv + 1
                    max_lv = self.bot_config.get('martingale_levels', 2)
                    if lvl <= max_lv:
                        self.martingale_state[signal.pair] = {'level': lvl, 'last_value': entry_value}
                    else: 
                        self.martingale_state[signal.pair] = {'level': 0, 'last_value': self.bot_config.get('entry_value', entry_value)}

        except Exception as e:
            await self.logger('ERROR', f"_execute_and_wait({signal.pair}) falhou: {e}")
            traceback.print_exc()
        finally:
            self.is_trade_active = False
            await self.logger('INFO', 'Pronto para próxima análise.')
