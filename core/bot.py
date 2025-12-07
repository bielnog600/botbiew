import asyncio
import traceback
from datetime import datetime
from typing import Dict, Optional, Set, List
from types import SimpleNamespace
import pandas as pd 

from config import settings
from services.exnova_service import AsyncExnovaService
from services.supabase_service import SupabaseService
from analysis.technical import get_m15_sr_zones, get_h1_sr_zones
from analysis import technical_indicators as ti
from core.data_models import TradeSignal

# ==============================================================================
#                      CONSTANTES OTC (FORNECIDAS)
# ==============================================================================
ACTIVES_MAP = {
    "EURUSD": 1, "EURGBP": 2, "GBPJPY": 3, "EURJPY": 4, "GBPUSD": 5, "USDJPY": 6, "AUDCAD": 7, "NZDUSD": 8, "USDCHF": 72,
    "EURUSD-OTC": 76, "EURGBP-OTC": 77, "USDCHF-OTC": 78, "EURJPY-OTC": 79, "NZDUSD-OTC": 80, "GBPUSD-OTC": 81,
    "GBPJPY-OTC": 84, "USDJPY-OTC": 85, "AUDCAD-OTC": 86, "AUDUSD": 99, "USDCAD": 100, "AUDJPY": 101, "GBPCAD": 102,
    "GBPCHF": 103, "GBPAUD": 104, "EURCAD": 105, "CHFJPY": 106, "CADCHF": 107, "EURAUD": 108, "USDNOK": 168,
    "EURNZD": 212, "USDSEK": 219, "USDTRY": 220, "AUDCHF": 943, "AUDNZD": 944, "CADJPY": 945, "EURCHF": 946,
    "GBPNZD": 947, "NZDCAD": 948, "NZDJPY": 949, "EURSEK": 950, "EURNOK": 951, "CHFSGD": 952, "EURSGD": 955,
    "USDMXN": 957, "USDDKK": 1045, "NZDCHF": 1048, "CADSGD": 1054, "EURCZK": 1056, "USDTHB": 1062, "USDBRL-OTC": 1546,
    "USDMXN-OTC-L": 1548, "XAUUSD-OTC": 1857, "EURUSD-op": 1861, "EURGBP-op": 1862, "EURJPY-op": 1864, "USDJPY-op": 1865,
    "GBPJPY-op": 1866, "GBPUSD-op": 1867, "AUDCAD-op": 1868, "AUDJPY-op": 1869, "AUDUSD-op": 1870, "CADCHF-op": 1871,
    "EURAUD-op": 1874, "EURCAD-op": 1875, "EURCHF-op": 1876, "GBPAUD-op": 1877, "USDCAD-op": 1878, "GBPNZD-op": 1880,
    "NZDCAD-op": 1881, "NZDJPY-op": 1882, "AUDCHF-op": 1884, "NZDUSD-op": 1896, "GBPCAD-op": 1897, "GBPCHF-op": 1898,
    "AUDNZD-op": 1900, "EURNZD-op": 1901, "US30/JP225-OTC": 2079, "US100/JP225-OTC": 2080, "US500/JP225-OTC": 2081,
    "AUDUSD-OTC": 2111, "USDCAD-OTC": 2112, "AUDJPY-OTC": 2113, "GBPCAD-OTC": 2114, "GBPCHF-OTC": 2115, "GBPAUD-OTC": 2116,
    "EURCAD-OTC": 2117, "CHFJPY-OTC": 2118, "CADCHF-OTC": 2119, "EURAUD-OTC": 2120, "USDNOK-OTC": 2121, "EURNZD-OTC": 2122,
    "USDSEK-OTC": 2123, "USDTRY-OTC": 2124, "USDPLN-OTC": 2128, "AUDCHF-OTC": 2129, "AUDNZD-OTC": 2130, "EURCHF-OTC": 2131,
    "GBPNZD-OTC": 2132, "CADJPY-OTC": 2136, "NZDCAD-OTC": 2137, "NZDJPY-OTC": 2138, "NZDCHF-OTC": 2202
}

# ==============================================================================
#                      MONKEY PATCHES (CORREÇÕES INJETADAS)
# ==============================================================================

# --- 1. CORREÇÃO INDICADORES (Pandas & Padrões) ---
def _convert_candles_to_dataframe_fix(candles):
    if not candles: return pd.DataFrame()
    normalized = []
    for c in candles:
        if isinstance(c, dict): normalized.append(c)
        else:
            try: normalized.append(vars(c))
            except TypeError:
                try: normalized.append({'open': c.open, 'close': c.close, 'high': c.high, 'low': c.low, 'volume': getattr(c, 'volume', 0)})
                except AttributeError: pass
    df = pd.DataFrame(normalized)
    for col in ['open', 'close', 'high', 'low', 'volume']:
        if col in df.columns: df[col] = pd.to_numeric(df[col], errors='coerce')
    return df

def _validate_reversal_candle_fix(candle, direction):
    try:
        c_open, c_close = float(candle.open), float(candle.close)
        is_green = c_close >= c_open
        is_red = c_close <= c_open
        if direction.lower() == 'call' and not is_green:
            print(f"   [FILTRO] Call rejeitado. Vela Vermelha (O:{c_open} -> C:{c_close})")
            return False
        if direction.lower() == 'put' and not is_red:
            print(f"   [FILTRO] Put rejeitado. Vela Verde (O:{c_open} -> C:{c_close})")
            return False
        return True
    except: return False

def _check_candlestick_pattern_fix(candles):
    if len(candles) < 2: return None
    try:
        last, prev = candles[-1], candles[-2]
        get_val = lambda c, a: float(c[a]) if isinstance(c, dict) else float(getattr(c, a))
        
        l_open, l_close = get_val(last, 'open'), get_val(last, 'close')
        l_high, l_low = get_val(last, 'high'), get_val(last, 'low')
        p_open, p_close = get_val(prev, 'open'), get_val(prev, 'close')
        
        l_body = abs(l_close - l_open) or 0.00001
        l_upper = l_high - max(l_close, l_open)
        l_lower = min(l_close, l_open) - l_low
        
        is_p_red = p_close < p_open
        is_p_green = p_close > p_open
        is_l_green = l_close > l_open
        is_l_red = l_close < l_open
        
        # Engolfo
        if is_p_red and is_l_green and l_close > p_open and l_open < p_close: return 'call'
        if is_p_green and is_l_red and l_close < p_open and l_open > p_close: return 'put'
        
        # Pinbar (Ratio 1.5x)
        RATIO = 1.5
        if l_lower >= (RATIO * l_body) and l_upper <= l_body: return 'call'
        if l_upper >= (RATIO * l_body) and l_lower <= l_body: return 'put'
    except: return None
    return None

def _check_rsi_condition_fix(candles, period=14, overbought=65, oversold=35):
    try:
        df = _convert_candles_to_dataframe_fix(candles)
        if df.empty or len(df) < period + 1: return None
        
        delta = df['close'].diff()
        up, down = delta.clip(lower=0), -1 * delta.clip(upper=0)
        ma_up = up.ewm(com=period - 1, adjust=True, min_periods=period).mean()
        ma_down = down.ewm(com=period - 1, adjust=True, min_periods=period).mean()
        rsi = 100 - (100 / (1 + (ma_up / ma_down)))
        
        last_rsi = rsi.iloc[-1]
        # Log menos intrusivo para poupar espaço, reative se necessário
        # print(f"   [RSI DEBUG] Valor: {last_rsi:.2f}")
        
        if last_rsi >= overbought: return 'put'
        if last_rsi <= oversold: return 'call'
        return None
    except: return None

# Aplica patches dos indicadores
ti._convert_candles_to_dataframe = _convert_candles_to_dataframe_fix
ti.validate_reversal_candle = _validate_reversal_candle_fix
ti.check_candlestick_pattern = _check_candlestick_pattern_fix
ti.check_rsi_condition = _check_rsi_condition_fix

# --- 2. CORREÇÃO SERVIÇO DE EXECUÇÃO (ID + Híbrido) ---
async def _execute_trade_robust(self, amount, active, direction, duration):
    try:
        if hasattr(self, 'api') and self.api:
            print(f"[EXEC] Tentando BINARY para {active}...")
            status, id = await asyncio.to_thread(self.api.buy, amount, active, direction, duration)
            if status and id:
                print(f"[EXEC] Sucesso via BINARY. ID: {id}")
                return id
            elif not status and isinstance(id, str):
                print(f"[EXEC] Falha Binary: {id}")
    except Exception as e:
        print(f"[EXEC] Erro ao tentar Binary: {e}")

    try:
        if hasattr(self, 'api') and self.api:
            print(f"[EXEC] Binary falhou. Tentando DIGITAL para {active}...")
            status, id = await asyncio.to_thread(self.api.buy_digital_spot, active, amount, direction, duration)
            if status and id:
                print(f"[EXEC] Sucesso via DIGITAL. ID: {id}")
                return id
    except Exception as e:
        print(f"[EXEC] Erro ao tentar Digital: {e}")
    return None

AsyncExnovaService.execute_trade = _execute_trade_robust

# ==============================================================================

class TradingBot:
    def __init__(self):
        self.supabase = SupabaseService(settings.SUPABASE_URL, settings.SUPABASE_KEY)
        self.exnova = AsyncExnovaService(settings.EXNOVA_EMAIL, settings.EXNOVA_PASSWORD)
        self.is_running = True
        self.bot_config: Dict = {}
        self.martingale_state: Dict[str, Dict] = {} 
        self.pending_martingale_trades: Dict[str, Dict] = {} 
        self.active_trading_pairs: Set[str] = set() 
        self.asset_performance: Dict[str, Dict[str, int]] = {}
        self.consecutive_losses: Dict[str, int] = {}
        self.blacklisted_assets: set = set()
        self.last_reset_time: datetime = datetime.utcnow()
        self.last_analysis_minute = -1
        self.last_daily_reset_date = None
        self.daily_wins = 0
        self.daily_losses = 0

    def _get_asset_id(self, asset_name):
        """Converte Nome e Normaliza (EURUSD (OTC) -> EURUSD-OTC -> ID)."""
        # Normalização de nomes
        name = asset_name.replace(" (OTC)", "-OTC")
        
        if name in ACTIVES_MAP:
            return ACTIVES_MAP[name]
        
        # Fallback: Se não encontrou, retorna o próprio nome (pode falhar na API)
        return name

    async def logger(self, level: str, message: str):
        ts = datetime.utcnow().isoformat()
        print(f"[{ts}] [{level.upper()}] {message}", flush=True)
        try:
            await asyncio.to_thread(self.supabase.insert_log, level, message)
        except Exception:
            pass

    async def _hourly_cycle_reset(self):
        await self.logger('INFO', "CICLO HORÁRIO: Limpeza de stats.")
        self.asset_performance.clear()
        self.consecutive_losses.clear()
        self.blacklisted_assets.clear()
        self.last_reset_time = datetime.utcnow()
        
    async def _daily_reset_if_needed(self):
        current_date_utc = datetime.utcnow().date()
        if self.last_daily_reset_date != current_date_utc:
            await self.logger('INFO', f"NOVO DIA ({current_date_utc}). Reset metas.")
            self.daily_wins = 0
            self.daily_losses = 0
            self.last_daily_reset_date = current_date_utc
            try:
                bal = await self.exnova.get_current_balance()
                if bal > 0:
                    await asyncio.to_thread(self.supabase.update_config, {'daily_initial_balance': bal, 'current_balance': bal})
            except Exception as e:
                await self.logger('ERROR', f"Erro ao atualizar saldo diário: {e}")

    async def run(self):
        await self.logger('INFO', 'Bot a iniciar no modo DEBUG (Scan Verbose)...')
        
        if not await self.exnova.connect():
            await self.logger('ERROR', 'Falha na conexão inicial.')

        await self._daily_reset_if_needed()

        while self.is_running:
            try:
                # --- AUTO-RECONEXÃO ---
                connected = False
                try:
                    if hasattr(self.exnova, 'is_connected'):
                        connected = await self.exnova.is_connected()
                    else: connected = True
                except: pass

                if not connected:
                    print("[AVISO] Conexão perdida. Reconectando...")
                    if await self.exnova.connect():
                        await self.logger('SUCCESS', 'Reconectado.')
                    else:
                        await asyncio.sleep(5)
                        continue
                # -----------------------

                await self._daily_reset_if_needed()
                
                if (datetime.utcnow() - self.last_reset_time).total_seconds() >= 3600:
                    await self._hourly_cycle_reset()

                self.bot_config = await asyncio.to_thread(self.supabase.get_bot_config)
                status = self.bot_config.get('status', 'PAUSED')

                if status == 'RUNNING':
                    pending = list(self.pending_martingale_trades.keys())
                    for pair in pending:
                        if pair not in self.active_trading_pairs:
                            asyncio.create_task(self._execute_martingale_trade(pair))
                    await self.trading_cycle()
                
                elif status != 'RUNNING':
                    if len(self.active_trading_pairs) > 0:
                        print(f"[PAUSA] Aguardando {len(self.active_trading_pairs)} trades.")
                    await asyncio.sleep(2)
                await asyncio.sleep(1)

            except Exception as e:
                print(f"[LOOP ERROR] {e}")
                await asyncio.sleep(5)

    async def trading_cycle(self):
        try:
            if hasattr(self.exnova, 'is_connected') and not await self.exnova.is_connected(): return
        except: pass

        now = datetime.utcnow()
        if now.second >= 50:
            if now.minute != self.last_analysis_minute:
                self.last_analysis_minute = now.minute
                is_m5 = (now.minute + 1) % 5 == 0
                if is_m5:
                    await self.logger('INFO', f"Varredura M5...")
                    asyncio.create_task(self.run_analysis_for_timeframe(300, 5))
                else:
                    await self.logger('INFO', f"Varredura M1...")
                    asyncio.create_task(self.run_analysis_for_timeframe(60, 1))

    async def run_analysis_for_timeframe(self, timeframe_seconds: int, expiration_minutes: int):
        try:
            await self.exnova.change_balance(self.bot_config.get('account_type', 'PRACTICE'))
            assets = await self.exnova.get_open_assets()
            
            # --- LÓGICA DE FIM DE SEMANA / OTC ---
            is_weekend = datetime.utcnow().weekday() >= 5
            
            available_assets = []
            for asset in assets:
                # Verificação mais flexível para 'OTC'
                if is_weekend and 'OTC' not in asset: continue
                if not is_weekend and 'OTC' in asset: continue
                    
                if asset.split('-')[0] not in self.blacklisted_assets:
                    available_assets.append(asset)
            # -------------------------------------

            def get_asset_score(asset_name):
                pair = asset_name.split('-')[0]
                stats = self.asset_performance.get(pair, {'wins': 0, 'losses': 0})
                total = stats['wins'] + stats['losses']
                return stats['wins'] / total if total > 0 else 0.5

            target_assets = sorted(available_assets, key=get_asset_score, reverse=True)[:settings.MAX_ASSETS_TO_MONITOR]
            
            # [DEBUG IMPORTANTE] Ver o que o bot encontrou
            if timeframe_seconds == 60: # Só imprime no M1 para não spammar
                print(f"[DEBUG SCAN] Ativos encontrados: {len(target_assets)} (Exemplos: {target_assets[:3]})")

            max_sim = self.bot_config.get('max_simultaneous_trades', 1)
            
            if len(self.active_trading_pairs) >= max_sim: return

            tasks = []
            for asset in target_assets:
                base = asset.split('-')[0]
                if base in self.active_trading_pairs: continue
                tasks.append(self._analyze_asset(asset, timeframe_seconds, expiration_minutes))

            if tasks: await asyncio.gather(*tasks)
        except Exception as e:
            await self.logger('ERROR', f"Erro em run_analysis: {e}")

    async def _analyze_asset(self, full_name: str, timeframe_seconds: int, expiration_minutes: int):
        base = full_name.split('-')[0]
        if base in self.active_trading_pairs: return

        try:
            if expiration_minutes == 1: t1, t2, res_func = 60, 900, get_m15_sr_zones
            elif expiration_minutes == 5: t1, t2, res_func = 300, 3600, get_h1_sr_zones
            else: return

            # --- ID RESOLUTION DEBUG ---
            asset_id = self._get_asset_id(full_name)
            # ---------------------------

            candles = await asyncio.gather(
                self.exnova.get_historical_candles(asset_id, t1, 200),
                self.exnova.get_historical_candles(asset_id, t2, 100)
            )
            analysis_candles, sr_candles = candles
            
            # [DEBUG CRÍTICO] Se as velas vierem vazias, avisar!
            if not analysis_candles:
                # Comenta isto depois se spammar muito, mas precisamos agora
                if timeframe_seconds == 60:
                    print(f"[WARN] Sem velas para {full_name} (ID usado: {asset_id}). Verifique o ID.")
                return

            # Prepara dados
            analysis_candles_objs = []
            for c in analysis_candles:
                clean_c = c.copy()
                for field in ['open', 'close', 'high', 'low', 'volume']:
                    if field in clean_c:
                        try: clean_c[field] = float(clean_c[field])
                        except: pass
                analysis_candles_objs.append(SimpleNamespace(**clean_c))
            
            signal_candle_obj = analysis_candles_objs[-1]
            signal_candle_dict = analysis_candles[-1]
            
            res, sup = res_func(sr_candles)
            zones = {'resistance': res, 'support': sup}
            threshold = self.bot_config.get('confirmation_threshold', 2)
            final_direction, confluences = None, []

            if expiration_minutes == 1:
                sr_signal = ti.check_price_near_sr(signal_candle_obj, zones)
                if sr_signal:
                    print(f"[SINAL M1] {full_name}: SR {sr_signal} detetado. Analisando...")
                    confluences.append("SR_Zone")
                    
                    pattern = ti.check_candlestick_pattern(analysis_candles_objs)
                    if pattern == sr_signal: confluences.append("Candle_Pattern")

                    rsi_sig = ti.check_rsi_condition(analysis_candles_objs)
                    if rsi_sig == sr_signal: confluences.append("RSI_Condition")
                    
                    print(f"   >>> {full_name} Decisão: Padrão={pattern}, RSI_Sinal={rsi_sig} | Confluências={len(confluences)}/{threshold}")
                    if len(confluences) >= threshold: final_direction = sr_signal

            elif expiration_minutes == 5:
                m5_signal = ti.check_m5_price_action(analysis_candles_objs, zones)
                if m5_signal:
                    temp_conf = m5_signal['confluences']
                    rsi_sig = ti.check_rsi_condition(analysis_candles_objs)
                    if rsi_sig == m5_signal['direction']: temp_conf.append("RSI_Condition")
                    
                    print(f"[DEBUG M5] {full_name}: Sinal {m5_signal['direction']}. Conf: {temp_conf}")
                    if len(temp_conf) >= threshold:
                        final_direction = m5_signal['direction']
                        confluences = temp_conf
            
            if final_direction:
                if not ti.validate_reversal_candle(signal_candle_obj, final_direction): 
                    print(f"[{full_name}] Vela inválida (Filtro de cor).")
                    return
                
                max_trades = self.bot_config.get('max_simultaneous_trades', 1)
                if len(self.active_trading_pairs) >= max_trades: return

                now = datetime.utcnow()
                wait_sec = (60 - now.second - 1) + (1 - now.microsecond / 1000000) + 0.2
                await self.logger('INFO', f"Sinal {full_name} CONFIRMADO. Aguardando {wait_sec:.1f}s.")
                await asyncio.sleep(wait_sec)
                
                if base in self.active_trading_pairs: return
                self.active_trading_pairs.add(base)

                strategy = f"M{expiration_minutes}_" + ', '.join(confluences)
                await self.logger('SUCCESS', f"ENTRADA: {full_name} | {final_direction.upper()} | {strategy}")
                
                signal = TradeSignal(
                    pair=base, direction=final_direction, strategy=strategy,
                    open=signal_candle_dict['open'], high=signal_candle_dict['high'],
                    low=signal_candle_dict['low'], close=signal_candle_dict['close']
                )
                
                trade_exp = 4 if expiration_minutes == 5 else expiration_minutes
                asyncio.create_task(self._execute_and_wait(signal, full_name, trade_exp))

        except Exception as e:
            if base in self.active_trading_pairs: self.active_trading_pairs.remove(base)
            print(f"[ERRO] {base}: {e}")
            traceback.print_exc()

    async def _execute_martingale_trade(self, pair: str):
        trade_info = self.pending_martingale_trades.pop(pair, None)
        if not trade_info: return
        
        self.active_trading_pairs.add(pair)
        now = datetime.utcnow()
        next_min = (now.timestamp() // 60 + 1) * 60
        wait_sec = next_min - now.timestamp() + 0.2
        
        lvl = self.martingale_state.get(pair, {}).get('level', 1)
        await self.logger('WARNING', f"GALE {lvl} para {pair}. Aguardando {wait_sec:.2f}s.")
        await asyncio.sleep(wait_sec)

        strategy = f"M{trade_info['expiration_minutes']}_Gale_{lvl}"
        signal = TradeSignal(pair=trade_info['pair'], direction=trade_info['direction'], strategy=strategy)
        
        await self.logger('SUCCESS', f"ENTRADA GALE {pair}!")
        trade_exp = 4 if trade_info['expiration_minutes'] == 5 else trade_info['expiration_minutes']
        await self._execute_and_wait(signal, trade_info['full_name'], trade_exp)

    def _get_entry_value(self, asset: str, is_martingale: bool = False) -> float:
        base_val = self.bot_config.get('entry_value', 1.0)
        if not self.bot_config.get('use_martingale', False): return base_val
        mg_level = self.martingale_state.get(asset, {}).get('level', 0)
        level_calc = mg_level if is_martingale else 0
        if level_calc == 0: return base_val
        factor = self.bot_config.get('martingale_factor', 2.3)
        return round(base_val * (factor ** level_calc), 2)

    async def _execute_and_wait(self, signal: TradeSignal, full_name: str, expiration: int):
        try:
            is_gale = "Gale" in signal.strategy or "Martingale" in signal.strategy
            val = self._get_entry_value(signal.pair, is_martingale=is_gale)
            
            # --- CORREÇÃO: USAR ID PARA EXECUTAR ---
            active_id = self._get_asset_id(full_name)
            # ---------------------------------------
            
            oid = None
            retries = 2
            
            for attempt in range(retries):
                oid = await self.exnova.execute_trade(val, active_id, signal.direction.lower(), expiration)
                if oid: break
                
                print(f"[DEBUG] Tentativa {attempt+1}/{retries} falhou para {full_name} (ID: {active_id}). Retrying...")
                await asyncio.sleep(1)
            
            if not oid:
                await self.logger('ERROR', f"FALHA FATAL na ordem {full_name} (${val}).")
                if is_gale: self.martingale_state[signal.pair] = {'level': 0}
                self.active_trading_pairs.discard(signal.pair)
                return

            await self.logger('INFO', f"Ordem {oid} aceita. ${val}. Monitorando...")
            sid = await asyncio.to_thread(self.supabase.insert_trade_signal, signal)
            
            await asyncio.sleep(expiration * 60 + 15)
            result = await self.exnova.check_win(oid)
            
            await self.process_trade_result(signal.pair, full_name, result, sid, is_gale, expiration, signal.direction)

        except Exception as e:
            await self.logger('ERROR', f"Erro execução {full_name}: {e}")
        finally:
            self.active_trading_pairs.discard(signal.pair)

    async def process_trade_result(self, pair, full_name, result, sid, is_martingale, expiration, direction):
        await self.logger('SUCCESS' if result == 'win' else 'ERROR', f"Resultado {pair}: {result.upper()}")

        mg_lv = self.martingale_state.get(pair, {}).get('level', 0)
        if sid: await asyncio.to_thread(self.supabase.update_trade_result, sid, result.upper(), mg_lv)
        
        try:
            bal = await self.exnova.get_current_balance()
            if bal: await asyncio.to_thread(self.supabase.update_current_balance, bal)
        except Exception: pass

        self.asset_performance.setdefault(pair, {'wins': 0, 'losses': 0})
        self.consecutive_losses.setdefault(pair, 0)

        if result == 'win':
            self.daily_wins += 1
            self.asset_performance[pair]['wins'] += 1
            self.consecutive_losses[pair] = 0
            self.martingale_state[pair] = {'level': 0}
            if pair in self.blacklisted_assets: self.blacklisted_assets.remove(pair)
        elif result == 'loss':
            self.daily_losses += 1
            self.asset_performance[pair]['losses'] += 1
            self.consecutive_losses[pair] += 1
            if self.consecutive_losses[pair] >= 2: self.blacklisted_assets.add(pair)

            if self.bot_config.get('use_martingale', False):
                cur_lv = self.martingale_state.get(pair, {}).get('level', 0)
                max_lv = self.bot_config.get('martingale_levels', 2)
                if cur_lv < max_lv:
                    self.martingale_state[pair] = {'level': cur_lv + 1}
                    self.pending_martingale_trades[pair] = {
                        "full_name": full_name, "direction": direction,
                        "expiration_minutes": expiration, "pair": pair
                    }
                    await self.logger('WARNING', f"Agendado Gale {cur_lv + 1} em {pair}")
                else:
                    self.martingale_state[pair] = {'level': 0}
                    await self.logger('ERROR', f"Stop Gale em {pair}.")
