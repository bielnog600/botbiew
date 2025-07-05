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
        """
        Inicializa o TradingBot, configurando as conexões com os serviços Supabase e Exnova.
        """
        self.supabase = SupabaseService(settings.SUPABASE_URL, settings.SUPABASE_KEY)
        self.exnova = AsyncExnovaService(settings.EXNOVA_EMAIL, settings.EXNOVA_PASSWORD)
        self.is_running = True
        self.bot_config: Dict = {}
        self.martingale_state: Dict[str, Dict] = {}
        self.is_trade_active = False

    async def logger(self, level: str, message: str):
        """
        Regista uma mensagem tanto na consola como na base de dados Supabase.
        """
        ts = datetime.utcnow().isoformat()
        print(f"[{ts}] [{level.upper()}] {message}", flush=True)
        await self.supabase.insert_log(level, message)

    async def run(self):
        """
        O ponto de entrada principal para o bot. Conecta-se à Exnova e entra no ciclo principal de trading.
        """
        await self.logger('DEBUG', f"Configured MAX_ASSETS_TO_MONITOR = {settings.MAX_ASSETS_TO_MONITOR}")
        await self.logger('INFO', 'Bot a iniciar com LÓGICA DE ENTRADA NA VELA SEGUINTE...')
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
                    await self.trading_cycle()
                else:
                    if status != 'RUNNING':
                        await self.logger('INFO', f"Bot PAUSADO. Aguardando status 'RUNNING'.")
                    await asyncio.sleep(settings.BOT_CONFIG_POLL_INTERVAL)
            except Exception as e:
                await self.logger('ERROR', f"Loop principal falhou: {e}")
                traceback.print_exc()
                await asyncio.sleep(settings.BOT_CONFIG_POLL_INTERVAL)

    async def trading_cycle(self):
        """
        Verifica o tempo atual e decide se executa um ciclo de análise para M1 ou M5.
        """
        now = datetime.utcnow()
        
        # A análise de M5 tem prioridade.
        if now.minute % 5 == 0 and now.second < 5:
             await self.run_analysis_for_timeframe(timeframe_seconds=300, expiration_minutes=5)
        # Se não for hora de M5, faz a análise de M1.
        elif now.second < 5:
             await self.run_analysis_for_timeframe(timeframe_seconds=60, expiration_minutes=1)
        else:
            # Aguarda o próximo minuto para não sobrecarregar
            await asyncio.sleep(1)


    # MODIFICADO: Lógica de tempo para entrar na vela seguinte
    async def run_analysis_for_timeframe(self, timeframe_seconds: int, expiration_minutes: int):
        """
        Executa um ciclo de análise completo para um dado timeframe, entrando na VELA SEGUINTE.
        """
        if self.is_trade_active:
            await self.logger('INFO', f"Análise para M{expiration_minutes} pulada pois uma operação já está ativa.")
            return

        now_ts = datetime.utcnow().timestamp()
        
        # 1. Calcular o timestamp da abertura da PRÓXIMA vela
        # Arredonda o timestamp atual para o início do minuto atual
        current_minute_ts = now_ts - (now_ts % 60)
        # Calcula o timestamp de abertura da próxima vela do timeframe
        next_candle_ts = current_minute_ts - (current_minute_ts % (expiration_minutes * 60)) + (expiration_minutes * 60)

        # 2. Adicionar um buffer de 2 segundos para entrar após a abertura
        # Isto garante que os dados da vela anterior estão disponíveis na API
        entry_time_ts = next_candle_ts + 2

        # 3. Calcular o tempo de espera
        wait = max(entry_time_ts - now_ts, 0)
        
        if wait > (expiration_minutes * 60):
            await self.logger('DEBUG', f"Ponto de análise para M{expiration_minutes} já passou. Aguardando próximo ciclo.")
            return

        await self.logger('INFO', f"Aguardando {wait:.2f}s para analisar a vela recém-fechada e entrar na próxima vela de M{expiration_minutes}...")
        await asyncio.sleep(wait)

        # O resto da lógica continua igual
        await self.exnova.change_balance(self.bot_config.get('account_type', 'PRACTICE'))
        assets = await self.exnova.get_open_assets()
        assets = assets[: settings.MAX_ASSETS_TO_MONITOR]
        await self.logger('INFO', f"[M{expiration_minutes}] Ativos para análise: {assets}")

        for full in assets:
            if self.is_trade_active:
                break
            await self._analyze_asset(full, timeframe_seconds, expiration_minutes)

    async def _analyze_asset(self, full_name: str, timeframe_seconds: int, expiration_minutes: int):
        """
        Processa um ativo com uma lógica de REVERSÃO pura e corrigida.
        """
        try:
            base = full_name.split('-')[0]
            
            primary_candles_count = 500
            context_candles_count = 100

            if expiration_minutes == 1:
                analysis_candles, sr_candles = await asyncio.gather(
                    self.exnova.get_historical_candles(base, 60, primary_candles_count),
                    self.exnova.get_historical_candles(base, 900, context_candles_count), # M15 para S/R
                )
                if not analysis_candles or not sr_candles: return
                res, sup = get_m15_sr_zones(sr_candles)
            
            elif expiration_minutes == 5:
                analysis_candles, sr_candles = await asyncio.gather(
                    self.exnova.get_historical_candles(base, 300, primary_candles_count),
                    self.exnova.get_historical_candles(base, 3600, context_candles_count), # H1 para S/R
                )
                if not analysis_candles or not sr_candles: return
                res, sup = get_h1_sr_zones(sr_candles)
            else:
                return

            # --- FILTRO 1: VOLATILIDADE (ATR) ---
            atr_value = ti.calculate_atr(analysis_candles, period=14)
            min_atr, max_atr = 0.00005, 0.05 
            if atr_value is None or not (min_atr < atr_value < max_atr):
                await self.logger('DEBUG', f"[{base}-M{expiration_minutes}] Filtro de volatilidade: Fora dos limites (ATR={atr_value}). Ativo ignorado.")
                return

            # --- BUSCA POR CONFLUÊNCIAS DE REVERSÃO ---
            confluences = {'call': [], 'put': []}
            zones = {'resistance': res, 'support': sup}
            
            sr_signal = ti.check_price_near_sr(analysis_candles[-1], zones)
            if sr_signal: confluences[sr_signal].append("SR_Zone")

            candle_signal = ti.check_candlestick_pattern(analysis_candles)
            if candle_signal: confluences[candle_signal].append("Candle_Pattern")
            
            rsi_signal = ti.check_rsi_condition(analysis_candles)
            if rsi_signal: confluences[rsi_signal].append("RSI_Condition")
            
            # --- DECISÃO FINAL (LÓGICA DE REVERSÃO) ---
            final_direction = None
            confirmation_threshold = 2
            if 'SR_Zone' in confluences['call'] and len(confluences['call']) >= confirmation_threshold:
                final_direction = 'call'
            elif 'SR_Zone' in confluences['put'] and len(confluences['put']) >= confirmation_threshold:
                final_direction = 'put'
            
            if final_direction:
                strategy_name = f"M{expiration_minutes}_Reversal_" + ', '.join(confluences[final_direction])
                await self.logger('SUCCESS', f"[{base}-M{expiration_minutes}] SINAL VÁLIDO! Direção: {final_direction.upper()}. Confluências: {strategy_name}")
                
                last = analysis_candles[-1]
                signal = TradeSignal(pair=base, direction=final_direction, strategy=strategy_name,
                                     setup_candle_open=last.open, setup_candle_high=last.max,
                                     setup_candle_low=last.min, setup_candle_close=last.close)
                
                await self._execute_and_wait(signal, full_name, expiration_minutes)
                return

        except Exception as e:
            await self.logger('ERROR', f"Erro em _analyze_asset({full_name}, M{expiration_minutes}): {e}")
            traceback.print_exc()

    def _get_entry_value(self, asset: str) -> float:
        """
        Calcula o valor de entrada para uma operação, aplicando a lógica de martingale se ativada.
        """
        base = self.bot_config.get('entry_value', settings.ENTRY_VALUE)
        if not self.bot_config.get('use_martingale', False):
            return base
            
        state = self.martingale_state.get(asset, {'level': 0, 'last_value': base})
        if state['level'] == 0:
            return base
            
        return round(state['last_value'] * self.bot_config.get('martingale_factor', 2.3), 2)

    async def _execute_and_wait(self, signal: TradeSignal, full_name: str, expiration_minutes: int):
        """
        Executa uma operação e determina o resultado comparando o saldo antes e depois.
        """
        self.is_trade_active = True
        try:
            bal_before = await self.exnova.get_current_balance()

            entry_value = self._get_entry_value(signal.pair)
            sid = await self.supabase.insert_trade_signal(signal)
            if not sid:
                await self.logger('ERROR', f"[{signal.pair}] Falha ao inserir sinal, abortando.")
                self.is_trade_active = False
                return

            order_id = await self.exnova.execute_trade(entry_value, full_name, signal.direction.lower(), expiration_minutes)
            await self.logger('INFO', f"[{signal.pair}] Ordem {order_id} enviada. Valor: {entry_value}. Expiração: {expiration_minutes} min. Aguardando...")
            
            await asyncio.sleep(expiration_minutes * 60 + 5)

            bal_after = await self.exnova.get_current_balance()
            
            if bal_before is None or bal_after is None:
                result = 'UNKNOWN'
                await self.logger('WARNING', f"[{signal.pair}] Não foi possível ler o saldo antes/depois.")
            else:
                delta = bal_after - bal_before
                if delta > 0:
                    result = 'WIN'
                elif delta < 0:
                    result = 'LOSS'
                else:
                    result = 'DRAW'
                await self.logger('SUCCESS' if result == 'WIN' else 'ERROR', f"[{signal.pair}] Resultado: {result}. ΔSaldo = {delta:.2f}")

            mg_lv = self.martingale_state.get(signal.pair, {}).get('level', 0)
            await self.supabase.update_trade_result(sid, result, mg_lv)
            await self.supabase.update_current_balance(bal_after or 0.0)

            if self.bot_config.get('use_martingale', False):
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
