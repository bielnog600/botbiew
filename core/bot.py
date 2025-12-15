import asyncio
import traceback
import sys
import threading
import logging
import json
import time
from datetime import datetime
from typing import Dict, Optional, Set, List
from types import SimpleNamespace
import pandas as pd

try:
    import requests
except ImportError:
    requests = None

from config import settings
from services.exnova_service import AsyncExnovaService
from services.supabase_service import SupabaseService
from analysis.technical import get_m15_sr_zones, get_h1_sr_zones
from analysis import technical_indicators as ti
from core.data_models import TradeSignal

# ==============================================================================
#                       CONSTANTES GERAIS (PARES REAIS + OTC)
# ==============================================================================
ACTIVES_MAP = {
    "EURUSD": 1, "EURGBP": 2, "GBPJPY": 3, "EURJPY": 4, "GBPUSD": 5, "USDJPY": 6, "AUDCAD": 7, "NZDUSD": 8, 
    "USDCHF": 72, "AUDUSD": 99, "USDCAD": 100, "AUDJPY": 101, "GBPCAD": 102, "GBPCHF": 103, "EURCAD": 105,
    "EURUSD-OTC": 76, "EURGBP-OTC": 77, "USDCHF-OTC": 78, "EURJPY-OTC": 79, "NZDUSD-OTC": 80, "GBPUSD-OTC": 81,
    "GBPJPY-OTC": 84, "USDJPY-OTC": 85, "AUDCAD-OTC": 86, "AUDUSD-OTC": 2111, "USDCAD-OTC": 2112, 
    "USDMXN-OTC": 1548, "FWONA-OTC": 2169, "XNGUSD-OTC": 2170, "AUDJPY-OTC": 2113, "GBPCAD-OTC": 2114,
    "GBPCHF-OTC": 2115, "GBPAUD-OTC": 2116, "EURCAD-OTC": 2117
}

# ==============================================================================
#                       MONKEY PATCHES
# ==============================================================================

GLOBAL_TIME_OFFSET = 0

def _patch_library_constants_aggressive():
    try:
        import exnovaapi.constants as OP_code
        OP_code.ACTIVES.update(ACTIVES_MAP)
        REVERSE_MAP = {v: k for k, v in ACTIVES_MAP.items()}
        OP_code.ACTIVES.update(REVERSE_MAP)
    except: pass

_patch_library_constants_aggressive()

# --- 1. PATCH: INJEÇÃO INTELIGENTE DE GET_CANDLES ---
def _optimized_get_candles(self, active, duration, count, to):
    try:
        self.api.candles.candles_data = None
        active_id = active
        if isinstance(active, str):
            import exnovaapi.constants as OP_code
            active_id = OP_code.ACTIVES.get(active, None)
            if active_id is None:
                active_id = ACTIVES_MAP.get(active, None)
        
        if active_id is None:
            return []

        self.api.getcandles(active_id, duration, count, to)
        start = time.time()
        while self.api.candles.candles_data is None:
            if time.time() - start > 15: 
                # print(f"[TIMEOUT PATCH] {active} ID:{active_id}")
                return []
            time.sleep(0.05)
        return self.api.candles.candles_data
    except Exception:
        return []

# --- 2. PATCH: BALANCE ---
def _optimized_get_balances(self):
    self.api.balances_raw = None
    try:
        self.api.get_balances()
    except Exception:
        return {"msg": []}
    start = time.time()
    while self.api.balances_raw is None:
        if time.time() - start > 10: return {"msg": []} 
        time.sleep(0.1)
    return self.api.balances_raw

def _optimized_get_profile_ansyc(self):
    start = time.time()
    while self.api.profile.msg is None:
        if time.time() - start > 10: return None
        time.sleep(0.1)
    return self.api.profile.msg

try:
    import exnovaapi.stable_api
    TargetClass = None
    if hasattr(exnovaapi.stable_api, 'Exnova'):
        TargetClass = exnovaapi.stable_api.Exnova
    elif hasattr(exnovaapi.stable_api, 'ExnovaAPI'):
        TargetClass = exnovaapi.stable_api.ExnovaAPI

    if TargetClass:
        TargetClass.get_candles = _optimized_get_candles
        TargetClass.get_balances = _optimized_get_balances
        TargetClass.get_profile_ansyc = _optimized_get_profile_ansyc
        TargetClass.get_digital_underlying_list_data = lambda self: {"underlying": []}
        TargetClass.get_instruments = lambda self, *args: {"instruments": []}
        TargetClass._ExnovaAPI__get_other_open = lambda self, *args, **kwargs: None
        if hasattr(TargetClass, '_Exnova__get_other_open'):
             TargetClass._Exnova__get_other_open = lambda self, *args, **kwargs: None
except ImportError:
    pass

# --- 3. PATCH SERVICE GET_CANDLES ---
async def _get_historical_candles_patched(self, asset_name, duration, amount):
    if not hasattr(self, 'api') or not self.api: return []
    try:
        local_time = int(time.time())
        # TENTA RECUAR 30s PARA EVITAR ERROS DE FUTURO
        req_time = local_time - GLOBAL_TIME_OFFSET - 30

        candles = await asyncio.wait_for(
            asyncio.to_thread(self.api.get_candles, asset_name, duration, amount, req_time),
            timeout=20.0
        )
        
        # DEBUG DIAGNÓSTICO
        if not candles:
            # Se for None, é timeout/rede. Se for [], é a API a dizer "não tenho dados".
            is_none = candles is None
            is_empty = isinstance(candles, list) and len(candles) == 0
            if is_none:
                print(f"[DEBUG VELAS] {asset_name}: Timeout (Sem resposta)")
            elif is_empty:
                print(f"[DEBUG VELAS] {asset_name}: Lista Vazia (Bloqueio ou Tempo Errado)")
        
        return candles or []
    except Exception as e:
        print(f"[ERROR SERVICE] {asset_name}: {e}")
        return []

AsyncExnovaService.get_historical_candles = _get_historical_candles_patched

# --- 4. PATCH EXECUTE TRADE ---
async def _execute_trade_robust(self, amount, active_name, direction, duration):
    try:
        if hasattr(self, 'api') and self.api:
            status, id = await asyncio.to_thread(self.api.buy, amount, active_name, direction, duration)
            if status and id: return id
    except Exception: pass
    try:
        if hasattr(self, 'api') and self.api:
            status, id = await asyncio.to_thread(self.api.buy_digital_spot, active_name, amount, direction, duration)
            if status and id: return id
    except Exception: pass
    return None

AsyncExnovaService.execute_trade = _execute_trade_robust

# --- 5. PATCH ASSETS ---
async def _get_open_assets_fix(self):
    return [
        "EURUSD-OTC", "GBPUSD-OTC", "USDJPY-OTC", "EURJPY-OTC", 
        "USDCHF-OTC", "AUDCAD-OTC", "NZDUSD-OTC", "EURGBP-OTC", "AUDUSD-OTC",
        "USDMXN-OTC", "FWONA-OTC", "XNGUSD-OTC"
    ]
AsyncExnovaService.get_open_assets = _get_open_assets_fix

# --- 6. PATCH CONNECT ---
async def _connect_fresh_instance(self):
    try:
        if hasattr(self, 'api') and self.api is not None:
            try: self.api.websocket_client.close()
            except: pass
            self.api = None 
        from exnovaapi.stable_api import Exnova, ExnovaAPI
        try: self.api = Exnova("exnova.com", self.email, self.password)
        except NameError: self.api = ExnovaAPI("exnova.com", self.email, self.password)
        check = await asyncio.to_thread(self.api.connect)
        return check
    except Exception:
        return False
AsyncExnovaService.connect = _connect_fresh_instance

# --- 7. INDICADORES ---
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
        if direction.lower() == 'call' and not is_green: return False
        if direction.lower() == 'put' and not is_red: return False
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
        is_p_red, is_p_green = p_close < p_open, p_close > p_open
        is_l_green, is_l_red = l_close > l_open, l_close < l_open
        if is_p_red and is_l_green and l_close > p_open and l_open < p_close: return 'call'
        if is_p_green and is_l_red and l_close < p_open and l_open > p_close: return 'put'
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
        signal = None
        if last_rsi >= overbought: signal = 'put'
        elif last_rsi <= oversold: signal = 'call'
        return (signal, last_rsi) 
    except: return (None, 50.0)

ti._convert_candles_to_dataframe = _convert_candles_to_dataframe_fix
ti.validate_reversal_candle = _validate_reversal_candle_fix
ti.check_candlestick_pattern = _check_candlestick_pattern_fix
ti.check_rsi_condition = _check_rsi_condition_fix

def _safe_send_websocket_request(self, name, msg, request_id=""):
    try:
        if self.websocket and self.websocket.sock and self.websocket.sock.connected:
            data = json.dumps(dict(name=name, msg=msg, request_id=request_id))
            self.websocket.send(data)
            return True
    except Exception: pass
    return False

try:
    import exnovaapi.api
    exnovaapi.api.ExnovaAPI.send_websocket_request = _safe_send_websocket_request
except: pass

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

        # SUPRESSÃO DE LOGS
        for logger_name in ["websocket", "exnovaapi", "iqoptionapi", "urllib3", "iqoptionapi.websocket.client"]:
            logger = logging.getLogger(logger_name)
            logger.setLevel(logging.CRITICAL)
            logger.propagate = False

    def _get_asset_id(self, asset_name):
        return asset_name.replace(" (OTC)", "-OTC").strip()

    async def logger(self, level: str, message: str):
        ts = datetime.utcnow().isoformat()
        print(f"[{ts}] [{level.upper()}] {message}", flush=True)
        try: await asyncio.to_thread(self.supabase.insert_log, level, message)
        except: pass

    def _check_ip_reputation(self):
        if requests:
            try:
                ip = requests.get('https://api.ipify.org', timeout=5).text
                print(f"[NET DEBUG] IP Público do Bot: {ip}")
            except:
                print("[NET DEBUG] Não foi possível verificar o IP.")

    def _is_socket_connected(self):
        try:
            if not self.exnova.api:
                return False
            # check_connect() verifica global_value.check_websocket_if_connect
            return self.exnova.api.check_connect()
        except:
            return False

    async def _sync_time(self):
        global GLOBAL_TIME_OFFSET
        try:
            server_ts = 0
            if hasattr(self.exnova.api, 'get_server_timestamp'):
                server_ts = self.exnova.api.get_server_timestamp()
            
            if server_ts == 0 and hasattr(self.exnova.api.api, 'timesync'):
                 server_ts = self.exnova.api.api.timesync.server_timestamp

            if server_ts > 0:
                local_ts = time.time()
                if server_ts > 3000000000: 
                    server_ts /= 1000
                elif server_ts < 2000000000 and server_ts > 1000000:
                     if server_ts < local_ts / 100:
                         server_ts *= 1000

                offset = local_ts - server_ts
                if abs(offset) > 86400:
                    GLOBAL_TIME_OFFSET = 0
                else:
                    GLOBAL_TIME_OFFSET = int(offset)
            else:
                GLOBAL_TIME_OFFSET = 0

        except Exception:
            GLOBAL_TIME_OFFSET = 0

    async def _daily_reset_if_needed(self):
        current_date_utc = datetime.utcnow().date()
        if self.last_daily_reset_date != current_date_utc:
            await self.logger('INFO', f"NOVO DIA ({current_date_utc}). Reset metas.")
            self.daily_wins = 0
            self.daily_losses = 0
            self.last_daily_reset_date = current_date_utc
            try:
                bal = await self.exnova.get_current_balance()
                if bal and float(bal) > 0: 
                    await asyncio.to_thread(self.supabase.update_config, {'daily_initial_balance': bal, 'current_balance': bal})
            except: pass

    async def _hourly_cycle_reset(self):
        await self.logger('INFO', "CICLO HORÁRIO: Limpeza de stats.")
        self.asset_performance.clear()
        self.consecutive_losses.clear()
        self.blacklisted_assets.clear()
        self.last_reset_time = datetime.utcnow()

    async def run(self):
        await self.logger('INFO', 'Bot a iniciar no modo FORCE OTC ALWAYS...')
        
        self._check_ip_reputation()

        if not await self.exnova.connect(): await self.logger('ERROR', 'Falha na conexão inicial.')
        
        await self._daily_reset_if_needed()
        _patch_library_constants_aggressive()

        print("[SYSTEM] Aqueçendo API (Warmup 5s)...")
        await asyncio.sleep(5) 
        await self._sync_time()

        # BLOCO DE DIAGNÓSTICO DE INICIALIZAÇÃO
        # Tenta carregar perfil em loop. Se falhar, é Block.
        print("[SYSTEM] Verificando Perfil...")
        profile_ok = False
        for i in range(10):
            try:
                prof = await asyncio.to_thread(self.exnova.api.get_profile_ansyc)
                if prof:
                    print(f"[SYSTEM] Perfil OK! Currency: {prof.get('currency')} (Tentativa {i+1})")
                    profile_ok = True
                    break
            except: pass
            await asyncio.sleep(1)
        
        if not profile_ok:
            print("[ALERTA CRÍTICO] Falha ao carregar perfil. O IP pode estar bloqueado para dados.")

        print("[SYSTEM] Loop principal iniciado...")
        
        while self.is_running:
            try:
                if not self._is_socket_connected():
                    print("[AVISO] Conexão perdida. Tentando reconectar...")
                    reconnected = False
                    for i in range(3):
                        if await self.exnova.connect():
                            await self.logger('SUCCESS', 'Reconectado.')
                            await asyncio.sleep(3)
                            await self._sync_time()
                            reconnected = True
                            break
                        await asyncio.sleep(5)
                    
                    if not reconnected:
                        await asyncio.sleep(5)
                        continue

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
                    if len(self.active_trading_pairs) > 0: print(f"[PAUSA] Aguardando {len(self.active_trading_pairs)} trades.")
                    await asyncio.sleep(2)
                await asyncio.sleep(1)
            except Exception as e:
                print(f"[LOOP ERROR] {e}")
                await asyncio.sleep(5)

    async def trading_cycle(self):
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
            try:
                # DEBUG VISUAL ATIVO
                bal = await self.exnova.get_current_balance()
                print(f"[STATUS] Saldo: {bal} | {expiration_minutes}M Scan")
                await asyncio.wait_for(self.exnova.change_balance(self.bot_config.get('account_type', 'PRACTICE')), timeout=2.0)
            except: pass

            assets = await _get_open_assets_fix(None)
            available_assets = [a for a in assets if a not in self.blacklisted_assets]
            if not available_assets: available_assets = assets

            def get_asset_score(asset_name):
                stats = self.asset_performance.get(asset_name, {'wins': 0, 'losses': 0})
                total = stats['wins'] + stats['losses']
                return stats['wins'] / total if total > 0 else 0.5

            target_assets = sorted(available_assets, key=get_asset_score, reverse=True)[:15]
            max_sim = self.bot_config.get('max_simultaneous_trades', 1)
            if len(self.active_trading_pairs) >= max_sim: return

            for asset_name in target_assets:
                try:
                    if not self._is_socket_connected(): break
                except: break
                if asset_name in self.active_trading_pairs: continue
                try:
                    await self._analyze_asset(asset_name, timeframe_seconds, expiration_minutes)
                except Exception: pass
                await asyncio.sleep(4.0)

        except Exception as e:
            await self.logger('ERROR', f"Erro em run_analysis: {e}")

    async def _analyze_asset(self, full_name: str, timeframe_seconds: int, expiration_minutes: int):
        if full_name in self.active_trading_pairs: return

        try:
            if expiration_minutes == 1: t1, t2, res_func = 60, 900, get_m15_sr_zones
            elif expiration_minutes == 5: t1, t2, res_func = 300, 3600, get_h1_sr_zones
            else: return

            # DEBUG VISUAL ATIVO
            print(f"[DEBUG] Analisando: {full_name}")

            try:
                candles = await asyncio.gather(
                    self.exnova.get_historical_candles(full_name, t1, 200),
                    self.exnova.get_historical_candles(full_name, t2, 100)
                )
            except: return

            analysis_candles, sr_candles = candles
            if not analysis_candles:
                return

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

            close_price = float(signal_candle_obj.close)
            rsi_res = ti.check_rsi_condition(analysis_candles_objs) 
            rsi_sig, rsi_val = rsi_res if isinstance(rsi_res, tuple) else (None, 50.0)
            
            # DEBUG VISUAL ATIVO
            msg = f"ANALISE_DETALHADA::{full_name}::Preço:{close_price:.5f}::RSI:{rsi_val:.1f}"
            await self.logger('DEBUG', msg)

            if expiration_minutes == 1:
                sr_signal = ti.check_price_near_sr(signal_candle_obj, zones)
                pattern = ti.check_candlestick_pattern(analysis_candles_objs)
                
                if sr_signal:
                    print(f"[SINAL M1] {full_name}: SR {sr_signal}. RSI {rsi_val:.1f}")
                    confluences.append("SR_Zone")
                    if pattern == sr_signal: confluences.append("Candle_Pattern")
                    if rsi_sig == sr_signal: confluences.append("RSI_Condition")
                    if len(confluences) >= threshold: final_direction = sr_signal

            elif expiration_minutes == 5:
                m5_signal = ti.check_m5_price_action(analysis_candles_objs, zones)
                if m5_signal:
                    temp_conf = m5_signal['confluences']
                    if rsi_sig == m5_signal['direction']: temp_conf.append("RSI_Condition")
                    if len(temp_conf) >= threshold:
                        final_direction = m5_signal['direction']
                        confluences = temp_conf
            
            if final_direction:
                if not ti.validate_reversal_candle(signal_candle_obj, final_direction): 
                    return
                
                max_trades = self.bot_config.get('max_simultaneous_trades', 1)
                if len(self.active_trading_pairs) >= max_trades: return

                now = datetime.utcnow()
                wait_sec = (60 - now.second - 1) + (1 - now.microsecond / 1000000) + 0.2
                await self.logger('INFO', f"Sinal {full_name} CONFIRMADO. Aguardando {wait_sec:.1f}s.")
                await asyncio.sleep(wait_sec)
                
                if full_name in self.active_trading_pairs: return
                self.active_trading_pairs.add(full_name)

                strategy = f"M{expiration_minutes}_" + ', '.join(confluences)
                await self.logger('SUCCESS', f"ENTRADA: {full_name} | {final_direction.upper()} | {strategy}")
                
                signal = TradeSignal(
                    pair=full_name, direction=final_direction, strategy=strategy,
                    open=signal_candle_dict['open'], high=signal_candle_dict['high'],
                    low=signal_candle_dict['low'], close=signal_candle_dict['close']
                )
                
                trade_exp = 4 if expiration_minutes == 5 else expiration_minutes
                asyncio.create_task(self._execute_and_wait(signal, full_name, trade_exp))

        except Exception as e:
            pass

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
        signal = TradeSignal(pair=pair, direction=trade_info['direction'], strategy=strategy)
        await self.logger('SUCCESS', f"ENTRADA GALE {pair}!")
        trade_exp = 4 if trade_info['expiration_minutes'] == 5 else trade_info['expiration_minutes']
        await self._execute_and_wait(signal, pair, trade_exp)

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
            active_name = full_name 
            
            oid = None
            retries = 2
            
            for attempt in range(retries):
                oid = await self.exnova.execute_trade(val, active_name, signal.direction.lower(), expiration)
                if oid: break
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
        except: pass

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
