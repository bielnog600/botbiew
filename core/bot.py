import asyncio
import time
import traceback
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from config import settings
from services.exnova_service import AsyncExnovaService
from services.supabase_service import SupabaseService
# MODIFICADO: Removido STRATEGIES, pois a lógica agora é interna
from analysis.technical import get_m15_sr_zones
# NOVO: Importando as novas funções de indicadores
from analysis import technical_indicators as ti
from core.data_models import TradeSignal

class TradingBot:
    def __init__(self):
        """
        Initializes the TradingBot, setting up connections to Supabase and Exnova services.
        """
        self.supabase = SupabaseService(settings.SUPABASE_URL, settings.SUPABASE_KEY)
        self.exnova = AsyncExnovaService(settings.EXNOVA_EMAIL, settings.EXNOVA_PASSWORD)
        self.is_running = True
        self.bot_config: Dict = {}
        self.martingale_state: Dict[str, Dict] = {}
        self.is_trade_active = False

    async def logger(self, level: str, message: str):
        """
        Logs a message to both the console and the Supabase database.
        
        Args:
            level: The log level (e.g., 'INFO', 'ERROR').
            message: The message to log.
        """
        ts = datetime.utcnow().isoformat()
        print(f"[{ts}] [{level.upper()}] {message}", flush=True)
        await self.supabase.insert_log(level, message)

    async def run(self):
        """
        The main entry point for the bot. Connects to Exnova and enters the main trading loop.
        """
        await self.logger('DEBUG', f"Configured MAX_ASSETS_TO_MONITOR = {settings.MAX_ASSETS_TO_MONITOR}")
        await self.logger('INFO', 'Bot a iniciar com LÓGICA DE CONFLUÊNCIA PROFISSIONAL...')
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
                    await self.logger('INFO', 'Iniciando ciclo de análise...')
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
        Executes a single trading cycle: fetches assets, analyzes them, and places trades.
        """
        await self.exnova.change_balance(self.bot_config.get('account_type', 'PRACTICE'))

        assets = await self.exnova.get_open_assets()
        assets = assets[: settings.MAX_ASSETS_TO_MONITOR]
        await self.logger('INFO', f"Ativos para análise: {assets}")

        now = datetime.utcnow()
        target_dt = (now.replace(second=0, microsecond=0) + timedelta(minutes=1)) - timedelta(seconds=1.5)
        wait = max(target_dt.timestamp() - time.time(), 0)
        await self.logger('DEBUG', f"Aguardando {wait:.2f}s até entrada otimizada...")
        await asyncio.sleep(wait)

        for full in assets:
            if self.is_trade_active:
                break
            await self._process_asset(full)

    # MODIFICADO: Lógica de análise completamente reescrita
    async def _process_asset(self, full_name: str):
        """
        Processes a single asset with confluence logic:
        1. Volatility Filter (ATR)
        2. Trend Filter (EMA)
        3. Gathers confluences from multiple indicators.
        4. Executes trade only if enough confluences align with the trend.
        """
        try:
            base = full_name.split('-')[0]
            
            # 1. Obter mais dados para indicadores mais longos
            m1, m5, m15 = await asyncio.gather(
                self.exnova.get_historical_candles(base, 60, 100), # M1 para análise primária
                self.exnova.get_historical_candles(base, 300, 50), # M5 para tendência
                self.exnova.get_historical_candles(base, 900, 50), # M15 para S/R
            )
            if not m1 or not m15 or not m5:
                await self.logger('WARNING', f"[{base}] Não foi possível obter todos os candles necessários.")
                return

            # --- FILTRO 1: VOLATILIDADE (ATR) ---
            # TODO: Ajuste os valores min/max de acordo com seus testes
            atr_value = ti.calculate_atr(m1, period=14)
            min_atr, max_atr = 0.00015, 0.001 
            if atr_value is None or not (min_atr < atr_value < max_atr):
                await self.logger('DEBUG', f"[{base}] Filtro de volatilidade: Fora dos limites (ATR={atr_value}). Ativo ignorado.")
                return

            # --- FILTRO 2: TENDÊNCIA (MME Longa) ---
            trend_ema_period = 50
            trend_ema = ti.calculate_ema(m5, period=trend_ema_period)
            last_price = m5[-1].close
            trend = 'SIDEWAYS'
            if trend_ema:
                if last_price > trend_ema * 1.0005: # Adiciona um buffer
                    trend = 'UPTREND'
                elif last_price < trend_ema * 0.9995:
                    trend = 'DOWNTREND'
            await self.logger('DEBUG', f"[{base}] Filtro de Tendência (MME{trend_ema_period} em M5): {trend}")

            # --- 3. BUSCA POR CONFLUÊNCIAS ---
            confluences = {'call': [], 'put': []}

            # Confluência A: Suporte & Resistência de M15
            res, sup = get_m15_sr_zones(m15)
            zones = {'resistance': res, 'support': sup}
            sr_signal = ti.check_price_near_sr(m1[-1], zones)
            if sr_signal:
                confluences[sr_signal].append("SR_Zone")

            # Confluência B: Padrões de Candlestick
            candle_signal = ti.check_candlestick_pattern(m1)
            if candle_signal:
                confluences[candle_signal].append("Candle_Pattern")
            
            # Confluência C: Indicador RSI
            rsi_signal = ti.check_rsi_condition(m1)
            if rsi_signal:
                confluences[rsi_signal].append("RSI_Condition")

            # Você pode adicionar mais confluências aqui (MACD, Fibonacci, etc.)
            
            await self.logger('DEBUG', f"[{base}] Confluências encontradas: CALLS={confluences['call']}, PUTS={confluences['put']}")
            
            # --- 4. DECISÃO FINAL ---
            final_direction = None
            confirmation_threshold = 2 # Exigir pelo menos 2 confluências

            if len(confluences['call']) >= confirmation_threshold and trend in ['UPTREND', 'SIDEWAYS']:
                final_direction = 'call'
            elif len(confluences['put']) >= confirmation_threshold and trend in ['DOWNTREND', 'SIDEWAYS']:
                final_direction = 'put'
            
            if final_direction:
                strategy_name = ', '.join(confluences[final_direction])
                await self.logger('SUCCESS', f"[{base}] SINAL VÁLIDO ENCONTRADO! Direção: {final_direction.upper()}. Confluências: {strategy_name}. Tendência: {trend}")
                
                last = m1[-1]
                signal = TradeSignal(
                    pair=base,
                    direction=final_direction,
                    strategy=strategy_name,
                    setup_candle_open=last.open,
                    setup_candle_high=last.max,
                    setup_candle_low=last.min,
                    setup_candle_close=last.close,
                )
                await self._execute_and_wait(signal, full_name)
                return
            else:
                await self.logger('INFO', f"[{base}] Nenhuma oportunidade com confluência suficiente encontrada.")

        except Exception as e:
            await self.logger('ERROR', f"Erro em _process_asset({full_name}): {e}")
            traceback.print_exc()

    def _get_entry_value(self, asset: str) -> float:
        """
        Calculates the entry value for a trade, applying martingale logic if enabled.
        """
        base = self.bot_config.get('entry_value', settings.ENTRY_VALUE)
        if not self.bot_config.get('use_martingale', False):
            return base
            
        state = self.martingale_state.get(asset, {'level': 0, 'last_value': base})
        if state['level'] == 0:
            return base
            
        return round(state['last_value'] * self.bot_config.get('martingale_factor', 2.3), 2)

    async def _execute_and_wait(self, signal: TradeSignal, full_name: str):
        """
        Executes a trade and determines the result by comparing the balance before and after.
        """
        self.is_trade_active = True
        try:
            bal_before = await self.exnova.get_current_balance()

            entry_value = self._get_entry_value(signal.pair)
            sid = await self.supabase.insert_trade_signal(signal)
            if not sid:
                await self.logger('ERROR', f"[{signal.pair}] Failed to insert signal, aborting trade.")
                self.is_trade_active = False
                return

            order_id = await self.exnova.execute_trade(entry_value, full_name, signal.direction.lower(), 1)
            await self.logger('INFO', f"[{signal.pair}] Ordem {order_id} enviada. Valor: {entry_value}. Aguardando expiração…")
            
            await asyncio.sleep(65)

            bal_after = await self.exnova.get_current_balance()

            if bal_before is None or bal_after is None:
                result = 'UNKNOWN'
                await self.logger('WARNING', f"[{signal.pair}] Could not read balance before/after.")
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
