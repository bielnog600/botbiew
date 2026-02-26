import sys
import time
import logging
import json
import threading
import os
import random
import math
import subprocess
from datetime import datetime, timedelta, timezone
from collections import deque, defaultdict

# --- AUTO-INSTALAÇÃO DE DEPENDÊNCIAS ---
def install_package(package):
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])
    except Exception as e:
        print(f"[SYSTEM] Erro ao instalar {package}: {e}")

try:
    from supabase import create_client
except ImportError:
    print("[SYSTEM] Instalando supabase...")
    install_package("supabase")
    from supabase import create_client

# Tenta importar Exnova API, se falhar instala
try:
    from exnovaapi.stable_api import Exnova
except ImportError:
    print("[SYSTEM] Biblioteca 'exnovaapi' não encontrada. Instalando...")
    install_package("exnovaapi")
    try:
        from exnovaapi.stable_api import Exnova
    except ImportError:
        print("[ERRO CRÍTICO] Falha ao carregar 'exnovaapi'. Verifique a instalação.")
        sys.exit(1)


BOT_VERSION = "SHOCK_ENGINE_V73.1_RECALIBRATE_FIX_2026-02-11"
print(f"🚀 START::{BOT_VERSION}")

# ==============================================================================
# CONFIGURAÇÃO E AMBIENTE
# ==============================================================================
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

EXNOVA_EMAIL = os.environ.get("EXNOVA_EMAIL", "")
EXNOVA_PASSWORD = os.environ.get("EXNOVA_PASSWORD", "")

# Ajustes finos de Pipeline (Batch 3 = Equilíbrio)
SCAN_BATCH = int(os.environ.get("SCAN_BATCH", "3")) 
SCAN_TTL = float(os.environ.get("SCAN_TTL", "3.0")) 

BR_TIMEZONE = timezone(timedelta(hours=-3))

# Janelas de Tempo
NEXT_CANDLE_EXEC_SECONDS = [0, 1]
RESERVE_SECONDS = [58, 59]

# Cooldowns
GLOBAL_COOLDOWN_SECONDS = 50
ASSET_LOSS_COOLDOWN_SECONDS = 180

if not EXNOVA_EMAIL or not EXNOVA_PASSWORD:
    print("⚠️ AVISO: EXNOVA_EMAIL ou EXNOVA_PASSWORD não configurados.")

# ==============================================================================
# LOGGING
# ==============================================================================
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
for logger_name in ["websocket", "exnovaapi", "iqoptionapi", "urllib3", "iqoptionapi.websocket.client"]:
    logging.getLogger(logger_name).setLevel(logging.CRITICAL)

LAST_LOG_TIME = time.time()

def watchdog():
    global LAST_LOG_TIME
    print("[WATCHDOG] Monitoramento iniciado.")
    while True:
        time.sleep(60)
        if time.time() - LAST_LOG_TIME > 300:
            print("[WATCHDOG] ⚠️ Silêncio > 5min, forçando reinício...")
            os._exit(1)

# ==============================================================================
# UTILITÁRIOS
# ==============================================================================
def safe_json_extract(text: str):
    if not text:
        return None
    try:
        if isinstance(text, dict): return text
        s = text.find("{")
        e = text.rfind("}") + 1
        if s != -1 and e > s:
            return json.loads(text[s:e])
    except:
        pass
    return None

def clamp(v, a, b):
    return max(a, min(b, v))

# ==============================================================================
# ANÁLISE TÉCNICA (CORE)
# ==============================================================================
class TechnicalAnalysis:
    @staticmethod
    def calculate_atr(candles, period=14):
        if not candles or len(candles) < period + 1: return 0.0
        trs = []
        for i in range(-period, 0):
            c = candles[i]; p = candles[i - 1]
            high = float(c["max"]); low = float(c["min"]); prev_close = float(p["close"])
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            trs.append(tr)
        return sum(trs) / len(trs) if trs else 0.0

    @staticmethod
    def calculate_rsi(closes, period=14):
        if not closes or len(closes) < period + 1: return 50.0
        gains = 0.0; losses = 0.0
        for i in range(-period, 0):
            diff = closes[i] - closes[i-1]
            if diff > 0: gains += diff
            else: losses += abs(diff)
        if losses == 0: return 100.0
        rs = gains / max(losses, 1e-12)
        return 100.0 - (100.0 / (1.0 + rs))

    @staticmethod
    def calculate_ema(candles, period):
        if len(candles) < period: return 0
        prices = [float(c["close"]) for c in candles]
        ema = sum(prices[:period]) / period
        k = 2 / (period + 1)
        for price in prices[period:]:
            ema = (price * k) + (ema * (1 - k))
        return ema
    
    @staticmethod
    def calculate_wma(data, period):
        if len(data) < period: return 0
        weighted_sum = 0; weight_sum = 0
        for i in range(period):
            weight = i + 1
            weighted_sum += data[-(period-i)] * weight
            weight_sum += weight
        return weighted_sum / weight_sum

    @staticmethod
    def analyze_candle(candle):
        o = float(candle["open"]); c = float(candle["close"]); h = float(candle["max"]); l = float(candle["min"])
        body = abs(c - o); rng = max(h - l, 1e-12)
        color = "green" if c > o else "red" if c < o else "doji"
        return {"open": o, "close": c, "max": h, "min": l, "body": body, "range": rng, "color": color, "upper_wick": h - max(o, c), "lower_wick": min(o, c) - l}

    @staticmethod
    def check_compression(candles):
        if len(candles) < 20: return False
        ema9 = TechnicalAnalysis.calculate_ema(candles, 9)
        ema21 = TechnicalAnalysis.calculate_ema(candles, 21)
        spread = abs(ema9 - ema21)
        bodies = [abs(float(c["close"]) - float(c["open"])) for c in candles[-10:]]
        avg_body = sum(bodies) / len(bodies) if bodies else 0.00001
        return spread < (avg_body * 0.15)

    @staticmethod
    def get_signal_v2(candles):
        if len(candles) < 60: return None, "Dados insuficientes"
        ema9 = TechnicalAnalysis.calculate_ema(candles, 9)
        ema21 = TechnicalAnalysis.calculate_ema(candles, 21)
        ema21_prev = TechnicalAnalysis.calculate_ema(candles[:-1], 21)
        c_confirm = TechnicalAnalysis.analyze_candle(candles[-1]) 
        c_reject = TechnicalAnalysis.analyze_candle(candles[-2])  
        slope = ema21 - ema21_prev
        
        if ema9 > ema21 and slope > 0:
            if c_reject["color"] == "red" and c_confirm["color"] == "green": return "call", "V2_CALL"
        if ema9 < ema21 and slope < 0:
            if c_reject["color"] == "green" and c_confirm["color"] == "red": return "put", "V2_PUT"
        return None, "Sem V2"

class ShockLiveDetector:
    @staticmethod
    def detect(candles, asset_name, dynamic_config=None):
        if len(candles) < 30: return None, "Dados insuficientes", {}
        dyn = dynamic_config or {}
        if not bool(dyn.get("shock_enabled", True)): return None, "Shock OFF", {}

        body_mult = float(dyn.get("shock_body_mult", 1.5))
        range_mult = float(dyn.get("shock_range_mult", 1.4))
        close_pos_min = float(dyn.get("shock_close_pos_min", 0.85))
        pullback_ratio_max = float(dyn.get("shock_pullback_ratio_max", 0.25))
        trend_filter = bool(dyn.get("trend_filter_enabled", True))

        # OBS: Agora recebe candles normalizados (fechados), então -1 é a última vela fechada.
        live = TechnicalAnalysis.analyze_candle(candles[-1])
        closed = candles[:-1]
        ema9 = TechnicalAnalysis.calculate_ema(closed, 9)
        ema21 = TechnicalAnalysis.calculate_ema(closed, 21)
        trend_up = ema9 > ema21; trend_down = ema9 < ema21

        bodies = [abs(float(c["close"]) - float(c["open"])) for c in closed[-20:]]
        ranges = [(float(c["max"]) - float(c["min"])) for c in closed[-20:]]
        avg_body = (sum(bodies) / len(bodies)) if bodies else 0.00001
        avg_range = (sum(ranges) / len(ranges)) if ranges else 0.00001

        explosive = (live["body"] >= avg_body * body_mult) and (live["range"] >= avg_range * range_mult)
        if not explosive: return None, "Sem explosão", {"body_mult": body_mult}

        super_mult = max(2.2, body_mult + 0.8)
        super_explosive = (live["body"] >= avg_body * super_mult) and (live["range"] >= avg_range * super_mult)
        close_pos = (live["close"] - live["min"]) / live["range"]
        
        pullback = 0
        if live["color"] == "green": pullback = live["max"] - live["close"]
        elif live["color"] == "red": pullback = live["close"] - live["min"]
        pullback_ratio = pullback / live["range"]

        if live["color"] == "green":
            if trend_filter and trend_up and not super_explosive: return None, "Contra trend alta", {}
            if close_pos >= close_pos_min and pullback_ratio <= pullback_ratio_max: return "put", "SHOCK_UP", {}
        if live["color"] == "red":
            if trend_filter and trend_down and not super_explosive: return None, "Contra trend baixa", {}
            if close_pos <= (1.0 - close_pos_min) and pullback_ratio <= pullback_ratio_max: return "call", "SHOCK_DOWN", {}
        return None, "Sem padrão", {}

class GapTraderStrategy:
    @staticmethod
    def get_signal(candles):
        if len(candles) < 45: return None, "Dados insuficientes"
        closes = [float(c["close"]) for c in candles]
        def get_sma34(arr, idx):
            end = len(arr) + idx + 1 if idx < 0 else idx + 1
            start = end - 34
            if start < 0: return 0
            return sum(arr[start:end]) / 34
        buffer1_series = []
        for i in range(7):
            idx = -7 + i 
            sma = get_sma34(closes, idx)
            val = closes[idx] - sma
            buffer1_series.append(val)
        wma_curr = TechnicalAnalysis.calculate_wma(buffer1_series[2:], 5)
        line_curr = buffer1_series[-1]
        wma_prev = TechnicalAnalysis.calculate_wma(buffer1_series[1:-1], 5)
        line_prev = buffer1_series[-2]
        if line_curr > wma_curr and line_prev < wma_prev: return "put", "GAP_PUT"
        if line_curr < wma_curr and line_prev > wma_prev: return "call", "GAP_CALL"
        return None, "Sem sinal"

class TsunamiFlowStrategy:
    @staticmethod
    def get_signal(candles):
        if len(candles) < 4: return None, "Dados insuficientes"
        c1 = TechnicalAnalysis.analyze_candle(candles[-1]) 
        c2 = TechnicalAnalysis.analyze_candle(candles[-2])
        c3 = TechnicalAnalysis.analyze_candle(candles[-3])
        if c1["color"] == "green" and c2["color"] == "green" and c3["color"] == "green":
            if c1["body"] > c2["body"]: return "call", "TSUNAMI_UP"
        if c1["color"] == "red" and c2["color"] == "red" and c3["color"] == "red":
            if c1["body"] > c2["body"]: return "put", "TSUNAMI_DOWN"
        return None, "Sem fluxo"

class VolumeReactorStrategy:
    @staticmethod
    def get_signal(candles):
        if len(candles) < 30: return None, "Dados insuficientes"
        c1 = TechnicalAnalysis.analyze_candle(candles[-1]) 
        bodies = [abs(float(c["close"]) - float(c["open"])) for c in candles[-21:-1]]
        avg_body = sum(bodies) / len(bodies) if bodies else 0.00001
        if c1["body"] > avg_body * 2.5:
            if c1["color"] == "green": return "put", "REACTOR_TOP"
            if c1["color"] == "red": return "call", "REACTOR_BOTTOM"
        return None, "Sem reactor"

class EmaPullbackStrategy:
    @staticmethod
    def get_signal(candles, ema_fast=9, ema_slow=21, touch_k=0.25):
        if not candles or len(candles) < 60: return None, "Dados insuficientes"
        ema9 = TechnicalAnalysis.calculate_ema(candles, ema_fast)
        ema21 = TechnicalAnalysis.calculate_ema(candles, ema_slow)
        ema21_prev = TechnicalAnalysis.calculate_ema(candles[:-1], ema_slow)
        slope = ema21 - ema21_prev
        c0 = TechnicalAnalysis.analyze_candle(candles[-1]) 
        c1 = TechnicalAnalysis.analyze_candle(candles[-2]) 
        trend_up = (ema9 > ema21) and (slope > 0)
        trend_down = (ema9 < ema21) and (slope < 0)
        ranges = [(float(c["max"]) - float(c["min"])) for c in candles[-20:]]
        avg_range = (sum(ranges) / len(ranges)) if ranges else c1["range"]
        tol = avg_range * touch_k
        near_ema9_low = abs(c1["min"] - ema9) <= tol
        near_ema9_high = abs(c1["max"] - ema9) <= tol
        if trend_up and c1["color"] == "red" and near_ema9_low and c0["color"] == "green":
            close_pos = (c0["close"] - c0["min"]) / max(c0["range"], 1e-12)
            if close_pos >= 0.60: return "call", "EMA_PULLBACK_CALL"
        if trend_down and c1["color"] == "green" and near_ema9_high and c0["color"] == "red":
            close_pos = (c0["max"] - c0["close"]) / max(c0["range"], 1e-12)
            if close_pos >= 0.60: return "put", "EMA_PULLBACK_PUT"
        return None, "Sem pullback"

class BollingerReentryStrategy:
    @staticmethod
    def get_signal(candles, period=20, std_mult=2.0):
        if not candles or len(candles) < period + 5: return None, "Dados insuficientes"
        if not TechnicalAnalysis.check_compression(candles[-30:]): return None, "Sem range"
        closes = [float(c["close"]) for c in candles]
        def band_at(idx):
            window = closes[idx - period + 1: idx + 1]
            if len(window) < period: return 0, 0, 0
            sma = sum(window) / period
            var = sum((x - sma) ** 2 for x in window) / period
            std = var ** 0.5
            return sma, sma + std_mult * std, sma - std_mult * std
        prev_idx = len(candles) - 2; curr_idx = len(candles) - 1
        _, up_prev, lo_prev = band_at(prev_idx)
        _, up_curr, lo_curr = band_at(curr_idx)
        prev_close = closes[-2]; curr_close = closes[-1]
        rsi = TechnicalAnalysis.calculate_rsi(closes, 14)
        if prev_close < lo_prev and curr_close > lo_curr and rsi <= 35: return "call", "BB_REENTRY_CALL"
        if prev_close > up_prev and curr_close < up_curr and rsi >= 65: return "put", "BB_REENTRY_PUT"
        return None, "Sem BB"

# ==============================================================================
# ANÁLISE DE COMPORTAMENTO (MODULE)
# ==============================================================================
class BehaviorAnalysis:
    """ Módulo interno para análise de comportamento, SR e estrutura """
    
    @staticmethod
    def calculate_adx(candles, period=14):
        if len(candles) < period * 2: return {}
        
        highs = [float(c['max']) for c in candles]
        lows = [float(c['min']) for c in candles]
        closes = [float(c['close']) for c in candles]
        
        plus_dm = []
        minus_dm = []
        tr = []
        
        for i in range(1, len(candles)):
            h_diff = highs[i] - highs[i-1]
            l_diff = lows[i-1] - lows[i]
            
            plus_dm.append(h_diff if h_diff > l_diff and h_diff > 0 else 0)
            minus_dm.append(l_diff if l_diff > h_diff and l_diff > 0 else 0)
            
            tr.append(max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1])))

        def smooth(data, p):
            res = [sum(data[:p])]
            for x in data[p:]:
                res.append(res[-1] - (res[-1]/p) + x)
            return res

        tr_smooth = smooth(tr, period)
        plus_dm_smooth = smooth(plus_dm, period)
        minus_dm_smooth = smooth(minus_dm, period)
        
        if len(tr_smooth) == 0: return {}

        di_plus = [(p / t) * 100 if t else 0 for p, t in zip(plus_dm_smooth, tr_smooth)]
        di_minus = [(m / t) * 100 if t else 0 for m, t in zip(minus_dm_smooth, tr_smooth)]
        
        dx = []
        for i in range(len(di_plus)):
            denom = di_plus[i] + di_minus[i]
            num = abs(di_plus[i] - di_minus[i])
            dx.append((num / denom) * 100 if denom else 0)
            
        adx_val = sum(dx[-period:]) / period if len(dx) >= period else 0
        
        return {
            "adx": adx_val,
            "di_plus": di_plus[-1] if di_plus else 0,
            "di_minus": di_minus[-1] if di_minus else 0
        }

    @staticmethod
    def calculate_choppiness(candles, period=14):
        if len(candles) < period + 1: return 50.0
        
        highs = [float(c['max']) for c in candles]
        lows = [float(c['min']) for c in candles]
        closes = [float(c['close']) for c in candles]
        
        tr_sum = 0
        for i in range(1, period + 1):
            idx = -i
            tr = max(highs[idx] - lows[idx], abs(highs[idx] - closes[idx-1]), abs(lows[idx] - closes[idx-1]))
            tr_sum += tr
            
        range_max = max(highs[-period:])
        range_min = min(lows[-period:])
        denom = range_max - range_min
        
        if denom == 0: return 50.0
        
        chop = 100 * math.log10(tr_sum / denom) / math.log10(period)
        return chop

    @staticmethod
    def classify_regime(adx, chop):
        if adx > 25 and chop < 50: return "TREND"
        if adx < 20 or chop > 61.8: return "RANGE"
        return "MIXED"

    @staticmethod
    def detect_structure(candles, pivot_window=3, lookback=60):
        if len(candles) < lookback: return {"state": "UNKNOWN"}
        
        highs = [float(c['max']) for c in candles]
        lows = [float(c['min']) for c in candles]
        
        pivot_highs = []
        pivot_lows = []
        
        for i in range(pivot_window, len(candles) - pivot_window):
            window_highs = highs[i-pivot_window:i+pivot_window+1]
            window_lows = lows[i-pivot_window:i+pivot_window+1]
            
            if highs[i] == max(window_highs): pivot_highs.append(highs[i])
            if lows[i] == min(window_lows): pivot_lows.append(lows[i])
            
        if len(pivot_highs) < 2 or len(pivot_lows) < 2: return {"state": "UNKNOWN"}
        
        last_hh = pivot_highs[-1] > pivot_highs[-2]
        last_hl = pivot_lows[-1] > pivot_lows[-2]
        last_lh = pivot_highs[-1] < pivot_highs[-2]
        last_ll = pivot_lows[-1] < pivot_lows[-2]
        
        if last_hh and last_hl: return {"state": "UP_HH_HL"}
        if last_lh and last_ll: return {"state": "DOWN_LH_LL"}
        return {"state": "MIXED"}

    @staticmethod
    def get_sr_zones(candles, window_size=5, tolerance_pct=0.0015, top_n=5, lookback=400):
        if not candles:
            return {"support": [], "resistance": []}

        cs = candles[-lookback:] if len(candles) > lookback else candles
        highs = [float(c["max"]) for c in cs]
        lows = [float(c["min"]) for c in cs]

        piv_hi = []
        piv_lo = []

        # Detecção de pivôs locais
        for i in range(window_size, len(cs) - window_size):
            h = highs[i]
            l = lows[i]
            if h == max(highs[i-window_size:i+window_size+1]):
                piv_hi.append(h)
            if l == min(lows[i-window_size:i+window_size+1]):
                piv_lo.append(l)

        # Clusterização (Agrupa níveis próximos)
        def cluster(levels):
            if not levels: return []
            levels = sorted(levels)
            clusters = [[levels[0]]]
            for lvl in levels[1:]:
                base = sum(clusters[-1]) / len(clusters[-1])
                if abs(lvl - base) / max(base, 1e-12) <= tolerance_pct:
                    clusters[-1].append(lvl)
                else:
                    clusters.append([lvl])
            return [sum(c) / len(c) for c in clusters]

        res = cluster(piv_hi)
        sup = cluster(piv_lo)
        res = sorted(res, reverse=True)[:top_n] 
        sup = sorted(sup)[:top_n]              
        
        return {"support": sup, "resistance": res}

    @staticmethod
    def distance_to_nearest_level(price, levels):
        if not levels: return 999.0
        nearest = min([abs(price - l) for l in levels])
        return nearest / price

# ==============================================================================
# STRATEGY BRAIN
# ==============================================================================
class StrategyBrain:
    def __init__(self, log_fn, min_samples=6, decay=0.92):
        self.log_fn = log_fn
        self.min_samples = int(min_samples)
        self.decay = float(decay)
        self.stats = {} 
        self.map = {} 

    def _key(self, asset, dt):
        dow = dt.weekday(); hour = dt.hour
        return (asset, dow, hour)

    def log(self, msg, level="INFO"):
        try: self.log_fn(msg, level)
        except: pass

    def decay_bucket(self, asset, dt):
        k = self._key(asset, dt)
        b = self.stats.get(k)
        if not b: return
        for s, v in b.items():
            v["w"] *= self.decay
            v["t"] *= self.decay

    def update_result(self, asset, dt, strategy, is_win):
        k = self._key(asset, dt)
        if k not in self.stats: self.stats[k] = {}
        if strategy not in self.stats[k]: self.stats[k][strategy] = {"w": 0.0, "t": 0.0}
        self.decay_bucket(asset, dt)
        self.stats[k][strategy]["t"] += 1.0
        if is_win: self.stats[k][strategy]["w"] += 1.0
        self.rebuild_key(asset, dt)

    def get_bucket(self, asset, dt):
        k = self._key(asset, dt)
        return self.stats.get(k, {})

    def rebuild_key(self, asset, dt):
        k = self._key(asset, dt)
        bucket = self.stats.get(k, {})
        if not bucket: return
        best = None
        for strat, v in bucket.items():
            t = v["t"]
            if t <= 0: continue
            wr = v["w"] / t
            score = (wr * 0.8) + (min(t, 30.0) / 30.0 * 0.2)
            cand = {"strategy": strat, "wr": wr, "samples": int(t), "score": score}
            if (best is None) or (cand["score"] > best["score"]): best = cand
        if best and best["samples"] >= self.min_samples:
            self.map[k] = {"strategy": best["strategy"], "wr": float(best["wr"]), "samples": int(best["samples"])}
        else:
            if k in self.map: del self.map[k]

    def choose_strategy(self, asset, dt, allowed_strategies):
        k = self._key(asset, dt)
        m = self.map.get(k)
        if m and m["strategy"] in allowed_strategies:
            return m["strategy"], float(m["wr"]), int(m["samples"]), "HOUR_MAP"
        bucket = self.get_bucket(asset, dt)
        best = None
        for s in allowed_strategies:
            v = bucket.get(s)
            if not v or v["t"] <= 0: continue
            wr = v["w"] / v["t"]
            cand = {"strategy": s, "wr": wr, "samples": int(v["t"])}
            if (best is None) or (cand["wr"] > best["wr"]): best = cand
        if best: return best["strategy"], float(best["wr"]), int(best["samples"]), "BUCKET_FALLBACK"
        return "NO_TRADE", 0.0, 0, "NO_DATA"

# ==============================================================================
# BOT PRINCIPAL
# ==============================================================================
class SimpleBot:
    def __init__(self):
        self.api = None
        self.supabase = None
        self.trade_lock = threading.RLock()
        self.api_lock = threading.RLock()
        self.db_lock = threading.RLock()
        self.dynamic_lock = threading.RLock()
        
        # Pipeline Vars
        self.candles_cache = {} # M1 cache
        self.candles_cache_m15 = {} # M15 cache
        self.candles_lock = threading.RLock()
        self.minute_candidates = []
        self.scan_cursor = 0
        self.last_scan_second = -1

        self.brain = StrategyBrain(self.log_to_db, min_samples=4, decay=0.92) 
        self.strategies_pool = ["V2_TREND", "TSUNAMI_FLOW", "VOLUME_REACTOR", "GAP_TRADER", "SHOCK_REVERSAL", "EMA_PULLBACK", "BB_REENTRY"]
        
        self.pair_strategy_memory = defaultdict(lambda: deque(maxlen=40))
        self.strategy_memory = defaultdict(lambda: deque(maxlen=40))
        self.session_memory = deque(maxlen=20)
        self.strategy_cooldowns = {} 

        self.vol_lock = threading.RLock()
        self.vol_memory = defaultdict(lambda: deque(maxlen=240))
        self.vol_last_log = {} 
        self.behavior_last_log = {} 

        self.base_min_conf = 0.55
        self.asset_risk = defaultdict(lambda: {
            "min_conf": 0.55,
            "loss_streak": 0,
            "win_streak": 0,
            "cooldown_until": 0.0
        })

        self.active_trades = set()
        self.next_trade_plan = None
        self.asset_cooldown = {} 
        self.last_global_trade_ts = 0
        self.last_recalibrate_ts = 0
        self.last_balance_push_ts = 0
        self.last_alive_log_ts = 0

        self.current_date = datetime.now(BR_TIMEZONE).date()
        self.daily_wins = 0
        self.daily_losses = 0
        self.daily_total = 0
        self.win_streak = 0
        self.loss_streak = 0
        self.pause_until_ts = 0
        
        self.initial_balance_day = 0.0 # Guard para Stop Loss de Banca
        
        self.last_heartbeat_ts = 0
        self.last_config_ts = 0
        self.last_activity_ts = time.time()

        self.best_assets = [
            "EURUSD-OTC", "EURGBP-OTC", "USDCHF-OTC", "EURJPY-OTC", "NZDUSD-OTC", "GBPUSD-OTC", "GBPJPY-OTC", "USDJPY-OTC",
            "AUDCAD-OTC", "AUDUSD-OTC", "USDCAD-OTC", "AUDJPY-OTC", "GBPCAD-OTC", "GBPCHF-OTC", "GBPAUD-OTC", "EURCAD-OTC", 
            "CHFJPY-OTC", "CADCHF-OTC", "EURAUD-OTC", "USDNOK-OTC", "EURNZD-OTC", "USDSEK-OTC", "USDTRY-OTC", "USDPLN-OTC", 
            "AUDCHF-OTC", "AUDNZD-OTC", "EURCHF-OTC", "GBPNZD-OTC", "CADJPY-OTC", "NZDCAD-OTC", "NZDJPY-OTC", "CHFNOK-OTC", 
            "NOKJPY-OTC", "NZDCHF-OTC", "EURTHB-OTC", "USDTHB-OTC", "JPYTHB-OTC", "EURGBP_GS"
        ]

        self.asset_strategy_map = {}
        self.last_calibration_time = 0
        self.calibration_running = False

        self.dynamic = {
            "allow_trading": True, "prefer_strategy": "AUTO", "min_confidence": 0.55,
            "pause_win_streak": 2, "pause_win_seconds": 180,
            "pause_loss_streak": 2, "pause_loss_seconds": 900,
            "shock_enabled": True, "shock_body_mult": 1.5, "shock_range_mult": 1.4,
            "shock_close_pos_min": 0.85, "shock_pullback_ratio_max": 0.25,
            "trend_filter_enabled": True,
            "vol_enabled": True, "atr_period": 14, "vol_low_mult": 0.60, "vol_high_mult": 1.80,
        }

        self.config = {
            "status": "PAUSED", "account_type": "PRACTICE", "entry_value": 1.0,
            "max_trades_per_day": 0, "max_wins_per_day": 0, "max_losses_per_day": 0,
            "mode": "LIVE", "strategy_mode": "AUTO",
            "timer_enabled": False, "timer_start": "00:00", "timer_end": "23:59"
        }

        self.init_supabase()

    # --- INFRA ---
    def touch_watchdog(self):
        global LAST_LOG_TIME
        LAST_LOG_TIME = time.time()

    def init_supabase(self):
        try:
            if not SUPABASE_URL or not SUPABASE_KEY: self.supabase = None; return
            self.supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
            print("✅ Supabase conectado.")
        except Exception as e: print(f"❌ Erro Supabase: {e}"); self.supabase = None

    def log_to_db(self, message, level="INFO"):
        self.touch_watchdog()
        print(f"[{level}] {message}")
        if level == "DEBUG" or not self.supabase: return
        try:
            with self.db_lock: self.supabase.table("logs").insert({"message": message, "level": level, "created_at": datetime.now(timezone.utc).isoformat()}).execute()
        except: pass

    def push_balance_to_front(self):
        if not self.supabase or not self.api: return
        try:
            with self.api_lock: bal = self.api.get_balance()
            if self.initial_balance_day == 0: self.initial_balance_day = float(bal)
            with self.db_lock:
                self.supabase.table("bot_config").update({"current_balance": float(bal), "updated_at": datetime.now(timezone.utc).isoformat()}).eq("id", 1).execute()
        except Exception as e:
            self.log_to_db(f"⚠️ Erro Sync Saldo: {e}", "ERROR")

    # --- CONNECTION ---
    def connect(self):
        self.log_to_db("🔌 Conectando Exnova...", "SYSTEM")
        try:
            with self.api_lock:
                if self.api: 
                    try: self.api.api.close()
                    except: pass
                self.api = Exnova(EXNOVA_EMAIL, EXNOVA_PASSWORD)
                ok, reason = self.api.connect()
                if ok:
                    self.log_to_db("✅ Conectado!", "SUCCESS")
                    self.api.change_balance(self.config["account_type"])
                    return True
                else: self.log_to_db(f"❌ Falha conexão: {reason}", "ERROR")
        except Exception as e: self.log_to_db(f"❌ Erro conexão: {e}", "ERROR")
        return False

    # --- DATA FETCHING ---
    def fetch_config(self):
        if not self.supabase: return
        try:
            with self.db_lock: res = self.supabase.table("bot_config").select("*").eq("id", 1).execute()
            if res.data:
                d = res.data[0]
                self.config.update({
                    "status": str(d.get("status", "PAUSED")).strip().upper(),
                    "mode": str(d.get("mode", "LIVE")).strip().upper(),
                    "entry_value": float(d.get("entry_value", 1.0) or 1.0),
                    "account_type": str(d.get("account_type", "PRACTICE")).strip().upper(),
                    "max_trades_per_day": int(d.get("max_trades_per_day", 0) or 0),
                    "max_wins_per_day": int(d.get("max_wins_per_day", 0) or 0),
                    "max_losses_per_day": int(d.get("max_losses_per_day", 0) or 0),
                    "strategy_mode": str(d.get("strategy_mode", "AUTO")).strip().upper(),
                    "timer_enabled": bool(d.get("timer_enabled", False)),
                    "timer_start": str(d.get("timer_start", "00:00")),
                    "timer_end": str(d.get("timer_end", "23:59")),
                })
                
                # Troca o saldo (Demo/Real) on-the-fly sem precisar reiniciar
                if self.api and self.api.check_connect():
                    try: self.api.change_balance(self.config["account_type"])
                    except: pass

                dyn_json = d.get("dynamic_json")
                if dyn_json:
                    parsed = safe_json_extract(dyn_json)
                    if parsed:
                        with self.dynamic_lock: self.dynamic.update(parsed)
        except: pass

    def reset_daily_if_needed(self):
        today = datetime.now(BR_TIMEZONE).date()
        if today != self.current_date:
            self.current_date = today; self.daily_wins = 0; self.daily_losses = 0; self.daily_total = 0
            self.win_streak = 0; self.loss_streak = 0; self.pause_until_ts = 0; self.next_trade_plan = None
            self.asset_cooldown = {}
            self.initial_balance_day = 0 # Reset balance guard
            self.asset_risk = defaultdict(lambda: {"min_conf": self.base_min_conf, "loss_streak": 0, "win_streak": 0, "cooldown_until": 0.0})
            self.strategy_cooldowns = {}
            self.vol_last_log = {}
            self.log_to_db("🚀 Nova sessão diária (Risk & Strategy Reset)", "SYSTEM")

    def check_daily_limits(self):
        if self.config["max_trades_per_day"] > 0 and self.daily_total >= self.config["max_trades_per_day"]:
            self.log_to_db("🛑 Limite de trades do dia atingido", "WARNING"); return False
        if self.config["max_wins_per_day"] > 0 and self.daily_wins >= self.config["max_wins_per_day"]:
            self.log_to_db("🏆 Meta de wins atingida", "SUCCESS"); return False
        if self.config["max_losses_per_day"] > 0 and self.daily_losses >= self.config["max_losses_per_day"]:
            self.log_to_db("❌ Limite de losses atingido", "ERROR"); return False
        
        # --- STOP LOSS BANCA (20% do dia) ---
        if self.initial_balance_day > 0:
             try:
                 curr = float(self.api.get_balance())
                 if curr < (self.initial_balance_day * 0.80):
                     self.log_to_db(f"💀 STOP LOSS BANCA ATINGIDO! Inicial: {self.initial_balance_day} Atual: {curr}", "CRITICAL")
                     self.config["status"] = "PAUSED"
                     return False
             except: pass

        return True

    def check_timer_limits(self):
        """ Verifica se o bot está dentro da janela de operação agendada no painel """
        if not self.config.get("timer_enabled"):
            return True
        try:
            start_str = self.config.get("timer_start", "00:00")
            end_str = self.config.get("timer_end", "23:59")
            now = datetime.now(BR_TIMEZONE)
            
            start_time = datetime.strptime(start_str, "%H:%M").time()
            end_time = datetime.strptime(end_str, "%H:%M").time()
            current_time = now.time()

            if start_time <= end_time:
                return start_time <= current_time <= end_time
            else: # Caso passe da meia noite (ex: 22:00 as 02:00)
                return current_time >= start_time or current_time <= end_time
        except Exception:
            return True # Em caso de falha de formatação do front, permite rodar

    def get_wr(self, strategy):
        mem = self.strategy_memory.get(strategy)
        if not mem: return 0.55
        return sum(mem) / len(mem)

    def get_wr_pair(self, asset, strategy):
        mem = self.pair_strategy_memory.get((asset, strategy))
        if not mem or len(mem) < 6: return 0.55
        return sum(mem) / len(mem)

    def get_wr_hour(self, asset, dt, strategy):
        bucket = self.brain.get_bucket(asset, dt) or {}
        v = bucket.get(strategy)
        if not v or v.get("t", 0) <= 0: return 0.55, 0
        t = float(v["t"])
        w = float(v["w"])
        return (w / t), int(t)

    def get_dynamic_amount(self, asset, strategy_key, base_amount, plan_confidence):
        if len(self.session_memory) < 5: wr_session = 0.50
        else: wr_session = sum(self.session_memory) / len(self.session_memory)
        wr_pair = self.get_wr_pair(asset, strategy_key)
        wr_mix = (wr_session * 0.5) + (wr_pair * 0.5)
        mult = 0.50 + 0.50 * clamp((wr_mix - 0.50) / 0.15, 0.0, 1.0)
        mult = mult * clamp(plan_confidence / 0.80, 0.80, 1.05)
        return round(base_amount * clamp(mult, 0.50, 1.0), 2)

    def check_strategy_signal(self, strategy_name, candles, asset_name=""):
        if strategy_name == "SHOCK_REVERSAL":
            with self.dynamic_lock: dyn = self.dynamic.copy()
            sig, lbl, _ = ShockLiveDetector.detect(candles, asset_name, dyn)
            return sig, lbl
        if strategy_name == "V2_TREND":
            if TechnicalAnalysis.check_compression(candles): return None, "Compressão"
            return TechnicalAnalysis.get_signal_v2(candles)
        if strategy_name == "BB_REENTRY": return BollingerReentryStrategy.get_signal(candles)
        if strategy_name == "EMA_PULLBACK": return EmaPullbackStrategy.get_signal(candles)
        if strategy_name == "TSUNAMI_FLOW": return TsunamiFlowStrategy.get_signal(candles)
        if strategy_name == "VOLUME_REACTOR": return VolumeReactorStrategy.get_signal(candles)
        if strategy_name == "GAP_TRADER": return GapTraderStrategy.get_signal(candles)
        return None, "Estratégia inválida"

    # --- HELPER: Velas ---
    def _candle_ts(self, c):
        try: return int(c.get("from", 0))
        except: return 0

    def normalize_candles(self, candles):
        return sorted(candles, key=lambda c: int(c.get("from", 0)))

    def normalize_closed_candles(self, candles, tf_sec=60):
        if not candles or len(candles) < 3: return candles
        candles = self.normalize_candles(candles)
        now_ts = int(time.time())
        last_ts = self._candle_ts(candles[-1])
        if last_ts > 0 and now_ts < (last_ts + tf_sec):
            return candles[:-1]
        return candles

    def fetch_candles_cached_tf(self, asset, tf_sec, need, ttl):
        now = time.time()
        cache_dict = self.candles_cache if tf_sec == 60 else self.candles_cache_m15
        
        with self.candles_lock:
            item = cache_dict.get(asset)
            if item and (now - item["ts"] <= ttl):
                closed = self.normalize_closed_candles(item["candles"], tf_sec)
                if closed and len(closed) >= need: return closed
        
        try:
            with self.api_lock: candles = self.api.get_candles(asset, tf_sec, max(need + 5, 60), int(time.time()))
            if candles:
                candles = self.normalize_candles(candles)
                with self.candles_lock: cache_dict[asset] = {"ts": now, "candles": candles}
                return self.normalize_closed_candles(candles, tf_sec)
        except: pass
        return None

    def analyze_behavior(self, m1_candles, m15_candles):
        adx_pack = BehaviorAnalysis.calculate_adx(m1_candles, period=14) or {}
        chop = BehaviorAnalysis.calculate_choppiness(m1_candles, period=14)
        adx = float(adx_pack.get("adx", 0.0))
        di_p = float(adx_pack.get("di_plus", 0.0))
        di_m = float(adx_pack.get("di_minus", 0.0))
        regime = BehaviorAnalysis.classify_regime(adx, chop)
        struct = BehaviorAnalysis.detect_structure(m1_candles, pivot_window=3, lookback=60)
        zones = {}
        if m15_candles: zones = BehaviorAnalysis.get_sr_zones(m15_candles, lookback=120)
        last_close = float(m1_candles[-1]["close"])
        d_sup = BehaviorAnalysis.distance_to_nearest_level(last_close, zones.get("support", [])) if zones else 999.0
        d_res = BehaviorAnalysis.distance_to_nearest_level(last_close, zones.get("resistance", [])) if zones else 999.0
        return {
            "regime": regime, "adx": adx, "di_plus": di_p, "di_minus": di_m, "chop": chop,
            "structure": struct, "sr": zones, "dist_support": d_sup, "dist_resistance": d_res
        }

    def insert_signal(self, asset, direction, strategy, amount, status="PENDING", result="PENDING", profit=0.0):
        if not self.supabase: return None
        try:
            payload = {
                "pair": asset, "direction": direction, "strategy": strategy, "status": status,
                "result": result, "profit": float(profit), "amount": float(amount),
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            with self.db_lock: res = self.supabase.table("trade_signals").insert(payload).execute()
            if getattr(res, "data", None) and len(res.data) > 0: return res.data[0].get("id")
        except Exception as e: self.log_to_db(f"⚠️ insert_signal: {e}", "ERROR")
        return None

    def update_signal(self, signal_id, status, result, profit):
        if not self.supabase or not signal_id: return
        try:
            with self.db_lock:
                self.supabase.table("trade_signals").update({
                    "status": status, "result": result, "profit": float(profit),
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }).eq("id", signal_id).execute()
        except Exception as e: self.log_to_db(f"⚠️ update_signal: {e}", "ERROR")

    # --- VOLATILITY CALC ---
    def calculate_vol_metrics(self, asset, candles):
        with self.dynamic_lock:
            atr_period = int(self.dynamic.get("atr_period", 14))
            low_mult = float(self.dynamic.get("vol_low_mult", 0.60))
            high_mult = float(self.dynamic.get("vol_high_mult", 1.80))

        atr = TechnicalAnalysis.calculate_atr(candles, period=atr_period)
        price = float(candles[-1]["close"])
        atr_pct = atr / max(price, 1e-12)

        with self.vol_lock:
            mem = self.vol_memory[asset]
            mem.append(atr_pct)
            if len(mem) < 40:
                # WARMUP BLOCK: Se ATR for absurdo (> 0.4%), bloqueia.
                if atr_pct > 0.004:
                     return {"state": "WARMUP_BLOCK", "current": atr_pct, "low": 0, "high": 0, "high_shock": 0, "med": 0}
                return {"state": "WARMUP", "current": atr_pct, "low": 0, "high": 999, "high_shock": 999, "med": 0}
            arr = sorted(mem)
            med = arr[len(arr) // 2]
            low = med * low_mult
            high = med * high_mult
            high_shock = med * 2.4

        return {"state": "READY", "current": atr_pct, "med": med, "low": low, "high": high, "high_shock": high_shock}

    # --- STRATEGY SIGNAL ---
    def vol_ok_for_strategy(self, strat, curr, med):
        if strat == "BB_REENTRY": return curr <= med * 1.15
        if strat in ["V2_TREND", "EMA_PULLBACK", "TSUNAMI_FLOW"]: return (curr >= med * 0.70) and (curr <= med * 1.90)
        if strat == "VOLUME_REACTOR": return (curr >= med * 0.95) and (curr <= med * 2.20)
        if strat == "SHOCK_REVERSAL": return (curr >= med * 1.60) and (curr <= med * 3.00)
        return True

    # --- SCANNING ---
    def pre_scan_window(self):
        sec = datetime.now(BR_TIMEZONE).second
        if sec < 30 or sec > 57: return
        if self.last_scan_second == sec: return
        self.last_scan_second = sec

        with self.dynamic_lock:
            allow_trading = bool(self.dynamic.get("allow_trading", True))
            min_conf = float(self.dynamic.get("min_confidence", 0.55))

        if not allow_trading or (time.time() - self.last_global_trade_ts < GLOBAL_COOLDOWN_SECONDS): return
        
        # Bloqueios Críticos do Painel (Stops diários e Timer)
        if not self.check_daily_limits(): return
        if not self.check_timer_limits(): return
        
        with self.trade_lock:
            if self.active_trades: return 

        now_dt = datetime.now(BR_TIMEZONE)
        batch_size = SCAN_BATCH
        local_candidates = []
        active_pool = self.best_assets[:]
        
        for _ in range(batch_size):
            asset = active_pool[self.scan_cursor % len(active_pool)]
            self.scan_cursor += 1
            risk = self.asset_risk[asset]
            if time.time() < risk["cooldown_until"]: continue
            
            # --- BEHAVIOR ANALYSIS ---
            m1 = self.fetch_candles_cached_tf(asset, 60, need=80, ttl=SCAN_TTL)
            if not m1: continue
            m15 = self.fetch_candles_cached_tf(asset, 900, need=130, ttl=60.0) # Cache longo pra M15

            behavior = self.analyze_behavior(m1, m15)
            
            # Logging Throttled
            log_key = (asset, datetime.now(BR_TIMEZONE).strftime("%Y%m%d%H%M"))
            if not self.behavior_last_log.get(log_key):
                self.behavior_last_log[log_key] = True
                self.log_to_db(f"🧭 BEHAVIOR {asset} reg={behavior['regime']} adx={behavior['adx']:.1f} struct={behavior['structure']['state']} dS={behavior['dist_support']:.4f} dR={behavior['dist_resistance']:.4f}", "DEBUG")

            # SELEÇÃO DE ESTRATÉGIAS POR REGIME E PAINEL
            reg = behavior["regime"]
            struct = behavior["structure"]["state"]
            strat_mode = self.config.get("strategy_mode", "AUTO")
            
            target_list = []
            
            if strat_mode == "AUTO":
                if reg == "TREND" and struct in ["UP_HH_HL", "DOWN_LH_LL"]:
                    target_list = ["V2_TREND", "EMA_PULLBACK", "TSUNAMI_FLOW"]
                elif reg == "RANGE":
                    target_list = ["BB_REENTRY", "SHOCK_REVERSAL", "VOLUME_REACTOR"]
                else: # MIXED/UNKNOWN
                    target_list = ["EMA_PULLBACK", "BB_REENTRY", "SHOCK_REVERSAL", "V2_TREND"]

                # Brain override (dica histórica) apenas no automático
                chosen, wr_hint, samples, src = self.brain.choose_strategy(asset, now_dt, self.strategies_pool)
                if chosen != "NO_TRADE" and chosen not in target_list:
                    target_list.append(chosen)
            else:
                # Oculta/Força apenas a estratégia definida no painel
                if strat_mode == "TENDMAX": 
                    target_list = ["V2_TREND"] # Mapeando TENDMAX do Front para o Engine do bot
                else:
                    target_list = [strat_mode]

            # Volatility check setup
            vol_metrics = None
            vol_enabled = self.dynamic.get("vol_enabled", True)
            if vol_enabled:
                 vol_metrics = self.calculate_vol_metrics(asset, m1) # Reuse m1
                 if vol_metrics["state"] == "WARMUP_BLOCK": continue

            best_local = None
            for strat in target_list:
                blocked_until = self.strategy_cooldowns.get((asset, strat), 0)
                if time.time() < blocked_until: continue 
                
                # GATE CHECK (POR ESTRATÉGIA)
                if vol_enabled and vol_metrics and vol_metrics["state"] == "READY":
                    med_val = vol_metrics.get("med", 0)
                    if not self.vol_ok_for_strategy(strat, vol_metrics["current"], med_val):
                         continue

                sig, lbl = self.check_strategy_signal(strat, m1, asset)
                if not sig: continue
                
                # --- SR PENALTY (CONFIDENCE) ---
                score_penalty = 1.0
                if behavior['dist_resistance'] <= 0.0012 and sig == 'call': score_penalty = 0.85
                if behavior['dist_support'] <= 0.0012 and sig == 'put': score_penalty = 0.85
                
                # Confiança
                wr_pair = self.get_wr_pair(asset, strat)
                wr_hour, hour_samples = self.get_wr_hour(asset, now_dt, strat)
                sample_factor = clamp(hour_samples / 12.0, 0.0, 1.0)
                
                conf = clamp((wr_pair * 0.55) + (wr_hour * 0.35) + (sample_factor * 0.10), 0.0, 0.95)
                
                # Aplica penalidade SR na confiança tambem
                if score_penalty < 1.0:
                    conf = conf * 0.92

                score = ((wr_pair * 0.55) + (wr_hour * 0.35) + (sample_factor * 0.10)) * score_penalty
                
                cand = {
                    "asset": asset, "direction": sig, "strategy": strat, "label": lbl, 
                    "confidence": conf, "score": score, "brain_src": src,
                    "regime": reg, "hour_samples": hour_samples
                }
                if (best_local is None) or (cand["score"] > best_local["score"]): best_local = cand

            min_conf_asset = float(risk["min_conf"])
            threshold_base = max(min_conf, min_conf_asset)
            has_history = (best_local and best_local.get("hour_samples", 0) >= 6)
            threshold = threshold_base if has_history else min_conf

            if best_local and best_local["confidence"] >= threshold:
                local_candidates.append(best_local)

        if local_candidates:
            with self.trade_lock: self.minute_candidates.extend(local_candidates)

    def reserve_best_candidate(self):
        sec = datetime.now(BR_TIMEZONE).second
        if sec < 58 or sec > 59: return 
        if self.next_trade_plan: return 

        with self.trade_lock:
            if self.active_trades: return
            cands = list(self.minute_candidates)
            self.minute_candidates = [] 

        if not cands: return
        cands.sort(key=lambda x: x["score"], reverse=True)
        best = cands[0]
        
        self.next_trade_plan = best
        self.next_trade_key = datetime.now(BR_TIMEZONE).strftime("%Y%m%d%H%M")
        
        risk = self.asset_risk[best["asset"]]
        self.log_to_db(
            f"🧠 RESERVADO: {best['asset']} {best['direction'].upper()} {best['strategy']} "
            f"conf={best['confidence']:.2f} score={best['score']:.3f} reg={best['regime']}",
            "SYSTEM"
        )

    def execute_reserved(self):
        if not self.next_trade_plan: return
        plan = self.next_trade_plan; self.next_trade_plan = None
        self.log_to_db(f"🚀 EXEC: {plan['asset']} {plan['direction'].upper()} {plan['strategy']}", "SYSTEM")
        t = threading.Thread(target=self._trade_thread, kwargs={"asset":plan["asset"], "direction":plan["direction"], "strategy_key":plan["strategy"], "strategy_label":plan["label"], "plan":plan}, daemon=True); t.start()

    def _trade_thread(self, asset, direction, strategy_key, strategy_label, plan):
        with self.trade_lock:
            if asset in self.active_trades: return
            self.active_trades.add(asset)
        
        self.last_global_trade_ts = time.time()
        
        try:
            amt = float(self.config["entry_value"])
            # Inserir sinal
            sid = self.insert_signal(asset, direction, f"{strategy_key}", amt)
            
            self.log_to_db(f"🟡 BUY: {asset} {direction} ${amt}", "INFO")
            
            if self.config["mode"] == "OBSERVE":
                st, tid = True, "VIRTUAL"
            else:
                with self.api_lock: st, tid = self.api.buy(amt, asset, direction, 1)
                if not st: 
                    # Tenta digital
                    with self.api_lock:
                        try:
                            self.api.subscribe_strike_list(asset, 1)
                            tid = self.api.buy_digital_spot(asset, amt, direction, 1)
                            if tid: st = True
                        except: pass
            
            if not st:
                self.log_to_db(f"❌ Falha Ordem {asset}", "ERROR")
                self.update_signal(sid, "FAILED", "FAILED", 0.0)
                return
            
            # --- REAL BALANCE GUARD ---
            # Espera até 10s para ver se o saldo muda, confirmando que a corretora processou
            initial_bal = 0.0
            with self.api_lock: initial_bal = float(self.api.get_balance())
            
            # Push inicial
            self.push_balance_to_front()
            
            time.sleep(64) # Aguarda vela
            
            # Checagem de Resultado V2 (Mudança de Saldo)
            res_str = "UNKNOWN"; profit = 0.0
            
            final_bal = initial_bal
            # Tenta ler saldo novo por 10s
            for _ in range(10):
                with self.api_lock: final_bal = float(self.api.get_balance())
                if abs(final_bal - initial_bal) > 0.01:
                    break
                time.sleep(1)

            delta = final_bal - initial_bal
            
            if delta > 0.01:
                res_str = "WIN"; profit = delta
            elif delta < -0.01:
                res_str = "LOSS"; profit = delta
            else:
                # Se saldo não mudou, assume LOSS ou DOJI (em Digital, empate é loss)
                # Vamos tentar ver pela vela pra ter certeza
                try:
                    with self.api_lock: c_res = self.api.get_candles(asset, 60, 3, int(time.time()))
                    if c_res:
                        c_res = self.normalize_candles(c_res)
                        last = self.normalize_closed_candles(c_res, tf_sec=60)[-1]
                        
                        # Logica simples de win/loss visual
                        op = last['open']; cl = last['close']
                        if direction == "call":
                            win = cl > op
                        else:
                            win = cl < op
                        
                        if win: res_str = "WIN"; profit = amt * 0.87
                        elif op == cl: res_str = "DOJI"; profit = 0.0
                        else: res_str = "LOSS"; profit = -amt
                except: 
                    res_str = "DOJI/ERROR"; profit = 0.0

            # Atualiza stats
            risk = self.asset_risk[asset]
            if "WIN" in res_str:
                self.daily_wins += 1; self.win_streak += 1; self.loss_streak = 0
                self.pair_strategy_memory[(asset, strategy_key)].append(1)
                self.session_memory.append(1)
                self.brain.update_result(asset, datetime.now(BR_TIMEZONE), strategy_key, True)
                risk["win_streak"] += 1; risk["loss_streak"] = 0
                risk["min_conf"] = max(self.base_min_conf, float(risk["min_conf"]) - 0.02)
                
            elif "LOSS" in res_str:
                self.daily_losses += 1; self.loss_streak += 1; self.win_streak = 0
                self.pair_strategy_memory[(asset, strategy_key)].append(0)
                self.session_memory.append(0)
                self.brain.update_result(asset, datetime.now(BR_TIMEZONE), strategy_key, False)
                risk["loss_streak"] += 1; risk["win_streak"] = 0
                risk["min_conf"] = min(0.90, float(risk["min_conf"]) + 0.03)
                risk["cooldown_until"] = time.time() + ASSET_LOSS_COOLDOWN_SECONDS
                
                # Freeze strategy
                self.strategy_cooldowns[(asset, strategy_key)] = time.time() + 1800
            
            self.update_signal(sid, res_str, res_str, profit)
            self.push_balance_to_front()
            
            self.log_to_db(f"{'🏆' if 'WIN' in res_str else '🔻'} {res_str} {asset}: {profit:.2f}", "SUCCESS" if "WIN" in res_str else "ERROR")

        except Exception as e:
            self.log_to_db(f"❌ Trade Err: {e}", "ERROR")
        finally:
            with self.trade_lock: self.active_trades.discard(asset)

    # --- RECALIBRAÇÃO ---
    def recalibrate_current_hour(self, assets_limit=25, backtest_steps=40):
        if not self.api or not self.api.check_connect(): return
        self.log_to_db("⚙️ Brain: Recalibrando hora atual...", "SYSTEM")
        now_dt = datetime.now(BR_TIMEZONE)
        sample_assets = self.best_assets[:]
        random.shuffle(sample_assets)
        sample_assets = sample_assets[:assets_limit]
        
        for asset in sample_assets:
            try:
                time.sleep(0.1)
                with self.api_lock: candles = self.api.get_candles(asset, 60, 120, int(time.time()))
                if not candles: continue
                candles = self.normalize_candles(candles)
                candles = self.normalize_closed_candles(candles)
                
                # Backtest simples para popular memória
                for s in self.strategies_pool:
                    wins = 0; total = 0
                    for i in range(len(candles) - backtest_steps - 2, len(candles) - 2):
                         window = candles[i-60:i+1]; result = candles[i+1]
                         sig, _ = self.check_strategy_signal(s, window, asset)
                         if sig:
                             total += 1
                             win = (sig == "call" and result["close"] > result["open"]) or (sig == "put" and result["close"] < result["open"])
                             if win: wins += 1
                    
                    if total >= 3:
                         k = self.brain._key(asset, now_dt)
                         if k not in self.brain.stats: self.brain.stats[k] = {}
                         if s not in self.brain.stats[k]: self.brain.stats[k][s] = {"w":0.0, "t":0.0}
                         self.brain.stats[k][s]["w"] += float(wins)
                         self.brain.stats[k][s]["t"] += float(total)
                         self.brain.rebuild_key(asset, now_dt)

            except: pass
        self.last_recalibrate_ts = time.time()
        self.log_to_db("🧠 Brain: Recalibração concluída.", "SUCCESS")

    # --- MAIN LOOP ---
    def start(self):
        threading.Thread(target=watchdog, daemon=True).start()
        self.log_to_db("🧠 Inicializando Bot (Real Balance Guard V73.1)...", "SYSTEM")
        
        # Init vars safe
        if not hasattr(self, "last_heartbeat_ts"): self.last_heartbeat_ts = 0
        if not hasattr(self, "last_config_ts"): self.last_config_ts = 0
        if not hasattr(self, "last_activity_ts"): self.last_activity_ts = time.time()
        if not hasattr(self, "last_balance_push_ts"): self.last_balance_push_ts = 0
        if not hasattr(self, "last_alive_log_ts"): self.last_alive_log_ts = 0

        if not self.api or not self.connect(): time.sleep(3)
        self.recalibrate_current_hour()

        while True:
            try:
                now = time.time()
                if now - self.last_heartbeat_ts >= 30: self.last_heartbeat_ts = now; self.touch_watchdog()
                if now - self.last_alive_log_ts >= 30:
                    self.last_alive_log_ts = now
                    self.log_to_db("❤️ ALIVE", "SYSTEM")
                
                if int(now) % 30 == 0: self.push_balance_to_front()
                self.reset_daily_if_needed()
                
                if now - self.last_config_ts >= 5: self.fetch_config(); self.last_config_ts = now
                if not self.api or not self.api.check_connect():
                    if not self.connect(): time.sleep(5); continue
                if self.config["status"] == "PAUSED" or now < self.pause_until_ts: time.sleep(1); continue

                if (now - self.last_recalibrate_ts) > 1800: self.recalibrate_current_hour()

                sec = datetime.now(BR_TIMEZONE).second
                if 30 <= sec <= 57: self.pre_scan_window()
                elif 58 <= sec <= 59: self.reserve_best_candidate()
                elif sec in NEXT_CANDLE_EXEC_SECONDS: self.execute_reserved()
                
                if sec == 2:
                     with self.trade_lock: self.minute_candidates = []

                time.sleep(0.1)
            except Exception as e:
                self.log_to_db(f"❌ Main Loop Error: {e}", "ERROR")
                time.sleep(3)

if __name__ == "__main__":
    SimpleBot().start()
