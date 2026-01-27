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

try:
    import requests
except ImportError:
    print("[SYSTEM] Instalando requests...")
    install_package("requests")
    import requests

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


BOT_VERSION = "SHOCK_ENGINE_V59_FIXED_CLASS_DEF_2026-01-27"
print(f"🚀 START::{BOT_VERSION}")

# ==============================================================================
# CONFIGURAÇÃO E AMBIENTE
# ==============================================================================
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

EXNOVA_EMAIL = os.environ.get("EXNOVA_EMAIL", "")
EXNOVA_PASSWORD = os.environ.get("EXNOVA_PASSWORD", "")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# Ajustes finos de Pipeline (Batch baixo para estabilidade)
SCAN_BATCH = int(os.environ.get("SCAN_BATCH", "1")) 
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
# ANÁLISE TÉCNICA
# ==============================================================================
class TechnicalAnalysis:
    @staticmethod
    def calculate_ema(candles, period):
        if len(candles) < period: return 0
        prices = [c["close"] for c in candles]
        ema = sum(prices[:period]) / period
        k = 2 / (period + 1)
        for price in prices[period:]:
            ema = (price * k) + (ema * (1 - k))
        return ema

    @staticmethod
    def analyze_candle(candle):
        o = candle["open"]; c = candle["close"]; h = candle["max"]; l = candle["min"]
        body = abs(c - o); rng = max(h - l, 1e-12)
        color = "green" if c > o else "red" if c < o else "doji"
        return {
            "open": o, "close": c, "max": h, "min": l,
            "body": body, "range": rng, "color": color,
            "upper_wick": h - max(o, c), "lower_wick": min(o, c) - l
        }

    @staticmethod
    def check_compression(candles):
        if len(candles) < 20: return False
        closed = candles[:-1]
        ema9 = TechnicalAnalysis.calculate_ema(closed, 9)
        ema21 = TechnicalAnalysis.calculate_ema(closed, 21)
        spread = abs(ema9 - ema21)
        bodies = [abs(c["close"] - c["open"]) for c in closed[-10:]]
        avg_body = sum(bodies) / len(bodies) if bodies else 0.00001
        return spread < (avg_body * 0.15)

    @staticmethod
    def get_signal_v2(candles):
        if len(candles) < 60: return None, "Dados insuficientes"
        closed = candles[:-1]
        ema9 = TechnicalAnalysis.calculate_ema(closed, 9)
        ema21 = TechnicalAnalysis.calculate_ema(closed, 21)
        ema21_prev = TechnicalAnalysis.calculate_ema(closed[:-1], 21)
        c_confirm = TechnicalAnalysis.analyze_candle(candles[-2])
        c_reject = TechnicalAnalysis.analyze_candle(candles[-3])
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

        live = TechnicalAnalysis.analyze_candle(candles[-1])
        closed = candles[:-1]
        ema9 = TechnicalAnalysis.calculate_ema(closed, 9)
        ema21 = TechnicalAnalysis.calculate_ema(closed, 21)
        trend_up = ema9 > ema21; trend_down = ema9 < ema21

        bodies = [abs(c["close"] - c["open"]) for c in closed[-20:]]
        ranges = [(c["max"] - c["min"]) for c in closed[-20:]]
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

class TendMaxStrategy:
    @staticmethod
    def get_signal(candles):
        if len(candles) < 50: return None, "Dados insuficientes"
        ema5 = TechnicalAnalysis.calculate_ema(candles[:-1], 5)
        ema10 = TechnicalAnalysis.calculate_ema(candles[:-1], 10)
        if ema5 > ema10: return "call", "TENDMAX_CALL"
        if ema5 < ema10: return "put", "TENDMAX_PUT"
        return None, "Sem cruzamento"

class TsunamiFlowStrategy:
    @staticmethod
    def get_signal(candles):
        if len(candles) < 6: return None, "Dados insuficientes"
        c1 = TechnicalAnalysis.analyze_candle(candles[-2])
        c2 = TechnicalAnalysis.analyze_candle(candles[-3])
        c3 = TechnicalAnalysis.analyze_candle(candles[-4])
        if c1["color"] == "green" and c2["color"] == "green" and c3["color"] == "green":
            if c1["body"] > c2["body"]: return "call", "TSUNAMI_UP"
        if c1["color"] == "red" and c2["color"] == "red" and c3["color"] == "red":
            if c1["body"] > c2["body"]: return "put", "TSUNAMI_DOWN"
        return None, "Sem fluxo"

class VolumeReactorStrategy:
    @staticmethod
    def get_signal(candles):
        if len(candles) < 30: return None, "Dados insuficientes"
        c1 = TechnicalAnalysis.analyze_candle(candles[-2])
        bodies = [abs(c["close"] - c["open"]) for c in candles[-22:-2]]
        avg_body = sum(bodies) / len(bodies) if bodies else 0.00001
        if c1["body"] > avg_body * 2.5:
            if c1["color"] == "green": return "put", "REACTOR_TOP"
            if c1["color"] == "red": return "call", "REACTOR_BOTTOM"
        return None, "Sem reactor"

# ==============================================================================
# IA COMMANDER
# ==============================================================================
class AICommander:
    def __init__(self, log_fn):
        self.log_fn = log_fn
        self.ai_active = False

    def log(self, msg, level="DEBUG"):
        try:
            self.log_fn(msg, level)
        except:
            pass

    def _call_openai_text(self, prompt):
        if not OPENAI_API_KEY:
            return None
        try:
            headers = {"Content-Type": "application/json", "Authorization": f"Bearer {OPENAI_API_KEY}"}
            payload = {
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.0
            }
            r = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=8)
            if r.status_code == 200:
                return (r.json()["choices"][0]["message"]["content"] or "").strip()
        except Exception as e:
            self.log(f"⚠️ OPENAI_TEXT_EX::{e}", "ERROR")
        return None

    def _call_gemini_text(self, prompt):
        if not GEMINI_API_KEY:
            return None
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
            payload = {"contents": [{"parts": [{"text": prompt}]}]}
            r = requests.post(url, json=payload, timeout=8)
            if r.status_code == 200:
                text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                return (text or "").strip()
        except Exception as e:
            self.log(f"⚠️ GEMINI_TEXT_EX::{e}", "ERROR")
        return None

    def check_connection(self):
        self.log("🤖 Testando conectividade da IA...", "SYSTEM")

        if not OPENAI_API_KEY and not GEMINI_API_KEY:
            self.log("⚠️ Nenhuma chave de IA configurada. Modo mecânico.", "WARNING")
            self.ai_active = False
            return False

        probe = "Responda apenas com a palavra OK."
        ok_text = self._call_openai_text(probe)
        if not ok_text:
            ok_text = self._call_gemini_text(probe)

        if ok_text:
            self.ai_active = True
            self.log(f"✅ IA ativa. Probe='{ok_text[:30]}'", "SUCCESS")
            return True

        self.ai_active = False
        self.log("⚠️ IA não respondeu. Vai de mecânico.", "WARNING")
        return False

    def _call_openai(self, prompt):
        if not OPENAI_API_KEY: return None
        try:
            headers = {"Content-Type": "application/json", "Authorization": f"Bearer {OPENAI_API_KEY}"}
            payload = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": prompt}], "temperature": 0.2}
            r = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=10)
            if r.status_code == 200:
                return safe_json_extract(r.json()["choices"][0]["message"]["content"])
        except Exception as e:
            self.log(f"⚠️ OPENAI_EX::{e}", "ERROR")
        return None

    def _call_gemini(self, prompt):
        if not GEMINI_API_KEY: return None
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
            payload = {"contents": [{"parts": [{"text": prompt}]}]}
            r = requests.post(url, json=payload, timeout=10)
            if r.status_code == 200:
                return safe_json_extract(r.json()["candidates"][0]["content"]["parts"][0]["text"])
        except Exception as e:
            self.log(f"⚠️ GEMINI_EX::{e}", "ERROR")
        return None

    def call(self, prompt):
        out = self._call_openai(prompt)
        if out:
            out["provider"] = "OPENAI"
            return out
        out = self._call_gemini(prompt)
        if out:
            out["provider"] = "GEMINI"
            return out
        return None

    def choose_strategy(self, asset_data):
        prompt = f"""
        Você é o Commander de um robô OTC M1.
        Escolha a MELHOR estratégia para este ativo.
        Se estiver ruim, responda NO_TRADE.
        Dados: {json.dumps(asset_data, ensure_ascii=False)}
        Estratégias: SHOCK_REVERSAL, V2_TREND, TENDMAX, TSUNAMI_FLOW, VOLUME_REACTOR, NO_TRADE
        JSON: {{"strategy":"NOME","confidence":0.0-1.0,"reason":"curto"}}
        """
        return self.call(prompt)

    def analyze_loss(self, context_data):
        prompt = f"""
        ANÁLISE DE LOSS. O bot perdeu. Analise as velas e diga o motivo.
        Contexto: {json.dumps(context_data, ensure_ascii=False)}
        JSON: {{ "reason": "LATERALIZACAO/RUIDO/REVERSAO", "explanation": "frase curta", "action": "INCREASE_CONFIDENCE" ou "CONTINUE" }}
        """
        return self.call(prompt)

    def global_tune(self, market_summary):
        prompt = f"""
        Ajuste global do bot.
        Resumo: {json.dumps(market_summary, ensure_ascii=False)}
        JSON: {{ "allow_trading": true, "prefer_strategy": "AUTO", "min_confidence": 0.80, "pause_win_streak": 2, "pause_win_seconds": 180, "pause_loss_streak": 2, "pause_loss_seconds": 900, "shock_enabled": true }}
        """
        return self.call(prompt)

# ==============================================================================
# STRATEGY BRAIN (NÚCLEO MECÂNICO)
# ==============================================================================
class StrategyBrain:
    def __init__(self, log_fn, min_samples=6, decay=0.92):
        self.log_fn = log_fn
        self.min_samples = int(min_samples)
        self.decay = float(decay)
        # stats[(asset, dow, hour)][strategy] = {"w": float, "t": float}
        self.stats = {}
        # mapa final já escolhido
        self.map = {} 

    def _key(self, asset, dt):
        dow = dt.weekday() # 0=segunda
        hour = dt.hour
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

        if best:
            return best["strategy"], float(best["wr"]), int(best["samples"]), "BUCKET_FALLBACK"

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
        self.candles_cache = {} 
        self.candles_lock = threading.RLock()
        self.minute_candidates = []
        self.scan_cursor = 0
        self.last_scan_second = -1

        # Brain e Memórias
        self.brain = StrategyBrain(self.log_to_db, min_samples=4, decay=0.92) 
        self.strategies_pool = ["V2_TREND", "TSUNAMI_FLOW", "VOLUME_REACTOR", "TENDMAX", "SHOCK_REVERSAL"]
        
        # Memória granular (Par, Estratégia)
        self.pair_strategy_memory = defaultdict(lambda: deque(maxlen=40))
        # Memória da sessão (Win/Loss recente) para stake dinâmica
        self.session_memory = deque(maxlen=20)

        self.active_trades = set()
        self.next_trade_plan = None
        self.asset_cooldown = {}
        self.last_global_trade_ts = 0
        self.last_recalibrate_ts = 0

        self.current_date = datetime.now(BR_TIMEZONE).date()
        self.daily_wins = 0
        self.daily_losses = 0
        self.daily_total = 0
        self.win_streak = 0
        self.loss_streak = 0
        self.pause_until_ts = 0
        
        # Variáveis de controle de tempo (Garantia no __init__)
        self.last_heartbeat_ts = 0
        self.last_config_ts = 0
        self.last_activity_ts = time.time()

        self.best_assets = [
            "EURUSD-OTC", "EURGBP-OTC", "USDCHF-OTC", "EURJPY-OTC", "NZDUSD-OTC", "GBPUSD-OTC", "GBPJPY-OTC", "USDJPY-OTC",
            "AUDCAD-OTC", "AUDUSD-OTC", "USDCAD-OTC", "AUDJPY-OTC", "GBPCAD-OTC", "GBPCHF-OTC", "GBPAUD-OTC", "EURCAD-OTC", 
            "CHFJPY-OTC", "CADCHF-OTC", "EURAUD-OTC", "USDNOK-OTC", "EURNZD-OTC", "USDSEK-OTC", "USDTRY-OTC", "USDPLN-OTC", 
            "AUDCHF-OTC", "AUDNZD-OTC", "EURCHF-OTC", "GBPNZD-OTC", "CADJPY-OTC", "NZDCAD-OTC", "NZDJPY-OTC", "CHFNOK-OTC", 
            "NOKJPY-OTC", "NZDCHF-OTC", "EURTHB-OTC", "USDTHB-OTC", "JPYTHB-OTC", "EURGBP_GS",
            "GOOGLE-OTC", "AMAZON-OTC", "TESLA-OTC", "FB-OTC", "APPLE-OTC", "Reddit", "AMZN/ALIBABA-OTC", "AMZN/EBAY-OTC", 
            "NVDA/AMD-OTC", "GOOGLE/MSFT-OTC", "TESLA/FORD-OTC", "MSFT/AAPL-OTC", "INTEL/IBM-OTC", "NFLX/AMZN-OTC", 
            "META/GOOGLE-OTC", "BIDU-OTC", "INTEL-OTC", "MSFT-OTC", "CITI-OTC", "COKE-OTC", "JPM-OTC", "MCDON-OTC", 
            "MORSTAN-OTC", "NIKE-OTC", "ALIBABA-OTC", "AIG-OTC", "GS-OTC", "SNAP-OTC",
            "ETHUSD-OTC", "SOLUSD-OTC", "TON/USD-OTC", "NOTCOIN-OTC", "XRPUSD-OTC", "LTCUSD-OTC", "EOSUSD-OTC", "ICPUSD-OTC", 
            "IMXUSD-OTC", "JUPUSD-OTC", "BONKUSD-OTC", "LINKUSD-OTC", "WIFUSD-OTC", "PEPEUSD-OTC", "FLOKIUSD-OTC", "GALAUSD-OTC", 
            "BCHUSD-OTC", "DOTUSD-OTC", "ATOMUSD-OTC", "INJUSD-OTC", "SEIUSD-OTC", "IOTAUSD-OTC", "BEAMUSD-OTC", "DASHUSD-OTC", 
            "ARBUSD-OTC", "WLDUSD-OTC", "ORDIUSD-OTC", "SATSUSD-OTC", "PYTHUSD-OTC", "RONINUSD-OTC", "TIAUSD-OTC", "MANAUSD-OTC", 
            "SANDUSD-OTC", "GRTUSD-OTC", "STXUSD-OTC", "MATICUSD-OTC", "NEARUSD-OTC", "HMSTR-OTC", "BTCUSD-OTC-op", "ONDOUSD-OTC", 
            "DYDXUSD-OTC", "ONYXCOINUSD-OTC", "FARTCOINUSD-OTC", "PENGUUSD-OTC", "RAYDIUMUSD-OTC", "SUIUSD-OTC", "HBARUSD-OTC", 
            "FETUSD-OTC", "RENDERUSD-OTC", "TAOUSD-OTC", "TRUMPUSD-OTC", "MELANIAUSD-OTC",
            "SP500-OTC", "USNDAQ100-OTC", "US30-OTC", "SP35-OTC", "FR40-OTC", "GER30-OTC", "UK100-OTC", "AUS200-OTC", "HK33-OTC", 
            "EU50-OTC", "JP225-OTC", "US30/JP225-OTC", "US100/JP225-OTC", "US500/JP225-OTC", "XAU/XAG-OTC", "GER30/UK100-OTC", 
            "US2000-OTC", "TRUMPvsHARRIS-OTC"
        ]

        # RESTAURADO!
        self.asset_strategy_map = {}
        self.last_calibration_time = 0
        self.calibration_running = False

        self.dynamic = {
            "allow_trading": True, "prefer_strategy": "AUTO", "min_confidence": 0.68, 
            "pause_win_streak": 2, "pause_win_seconds": 180,
            "pause_loss_streak": 2, "pause_loss_seconds": 900,
            "shock_enabled": True, "shock_body_mult": 1.5, "shock_range_mult": 1.4,
            "shock_close_pos_min": 0.85, "shock_pullback_ratio_max": 0.25,
            "trend_filter_enabled": True,
        }

        self.config = {
            "status": "PAUSED", "account_type": "PRACTICE", "entry_value": 1.0,
            "max_trades_per_day": 0, "max_wins_per_day": 0, "max_losses_per_day": 0,
            "mode": "LIVE", "strategy_mode": "AUTO"
        }

        self.init_supabase()
        self.commander = AICommander(self.log_to_db)

    def touch_watchdog(self):
        global LAST_LOG_TIME
        LAST_LOG_TIME = time.time()

    def init_supabase(self):
        try:
            if not SUPABASE_URL or not SUPABASE_KEY:
                self.supabase = None; return
            self.supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
            print("✅ Supabase conectado.")
        except Exception as e:
            print(f"❌ Erro Supabase: {e}"); self.supabase = None

    def log_to_db(self, message, level="INFO"):
        self.touch_watchdog()
        print(f"[{level}] {message}")
        if level == "DEBUG" or not self.supabase: return
        try:
            with self.db_lock:
                self.supabase.table("logs").insert({"message": message, "level": level, "created_at": datetime.now(timezone.utc).isoformat()}).execute()
        except: pass

    def log_json(self, tag, payload, level="DEBUG"):
        try: s = json.dumps(payload, ensure_ascii=False)
        except: s = str(payload)
        self.log_to_db(f"{tag}::{s}", level)

    def insert_signal(self, asset, direction, strategy, amount, status="PENDING", result="PENDING", profit=0.0):
        if not self.supabase: return None
        payload = {
            "pair": asset, "direction": direction, "strategy": strategy, "status": status, "result": result, "profit": profit,
            "amount": float(amount), "created_at": datetime.now(timezone.utc).isoformat()
        }
        try:
            with self.db_lock:
                res = self.supabase.table("trade_signals").insert(payload).execute()
            if res.data: return res.data[0].get("id")
        except: pass
        return None

    def update_signal(self, signal_id, status, result, profit):
        if not self.supabase or not signal_id: return
        try:
            with self.db_lock:
                self.supabase.table("trade_signals").update({"status": status, "result": result, "profit": profit}).eq("id", signal_id).execute()
        except: pass

    def push_balance_to_front(self):
        if not self.supabase or not self.api: return
        try:
            with self.api_lock: bal = self.api.get_balance()
            with self.db_lock:
                self.supabase.table("bot_config").update({
                    "current_balance": float(bal),
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }).eq("id", 1).execute()
        except: pass

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
                })
        except: pass

    def reset_daily_if_needed(self):
        today = datetime.now(BR_TIMEZONE).date()
        if today != self.current_date:
            self.current_date = today; self.daily_wins = 0; self.daily_losses = 0; self.daily_total = 0
            self.win_streak = 0; self.loss_streak = 0; self.pause_until_ts = 0; self.next_trade_plan = None
            self.asset_cooldown = {}; self.log_to_db("🚀 Nova sessão diária", "SYSTEM")

    def check_daily_limits(self):
        if self.config["max_trades_per_day"] > 0 and self.daily_total >= self.config["max_trades_per_day"]:
            self.log_to_db("🛑 Limite de trades do dia atingido", "WARNING"); return False
        if self.config["max_wins_per_day"] > 0 and self.daily_wins >= self.config["max_wins_per_day"]:
            self.log_to_db("🏆 Meta de wins atingida", "SUCCESS"); return False
        if self.config["max_losses_per_day"] > 0 and self.daily_losses >= self.config["max_losses_per_day"]:
            self.log_to_db("❌ Limite de losses atingido", "ERROR"); return False
        return True

    def get_wr(self, strategy):
        mem = self.strategy_memory.get(strategy)
        if not mem: return 0.55
        return sum(mem) / len(mem)

    def get_wr_pair(self, asset, strategy):
        mem = self.pair_strategy_memory.get((asset, strategy))
        if not mem or len(mem) < 6: return 0.55
        return sum(mem) / len(mem)

    def get_dynamic_amount(self, base_amount, plan_confidence):
        if len(self.session_memory) < 5: wr = 0.50
        else: wr = sum(self.session_memory) / len(self.session_memory)
        mult = 0.50 + 0.50 * clamp((wr - 0.50) / 0.15, 0.0, 1.0)
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
        if strategy_name == "TENDMAX": return TendMaxStrategy.get_signal(candles)
        if strategy_name == "TSUNAMI_FLOW": return TsunamiFlowStrategy.get_signal(candles)
        if strategy_name == "VOLUME_REACTOR": return VolumeReactorStrategy.get_signal(candles)
        return None, "Estratégia inválida"

    # --- NOVO MÉTODO: HELPERS PARA VELAS ---
    def _candle_ts(self, c):
        try: return int(c.get("from", 0))
        except: return 0

    def get_last_closed_candle(self, candles, now_ts=None):
        if not candles: return None
        if now_ts is None: now_ts = int(time.time())
        try:
            last = candles[-1]; last_ts = self._candle_ts(last)
            if last_ts > 0:
                if last_ts >= (now_ts - 55): return candles[-2] if len(candles) >= 2 else last
                return last
            return candles[-2] if len(candles) >= 2 else candles[-1]
        except: return candles[-2] if len(candles) >= 2 else candles[-1]

    # --- PIPELINE METHODS ---
    def fetch_candles_cached(self, asset, need=60, ttl=3.0):
        now = time.time()
        with self.candles_lock:
            item = self.candles_cache.get(asset)
            if item and (now - item["ts"] <= ttl) and len(item["candles"]) >= need:
                return item["candles"]
        try:
            with self.api_lock: candles = self.api.get_candles(asset, 60, max(need, 60), int(time.time()))
            if candles:
                with self.candles_lock: self.candles_cache[asset] = {"ts": now, "candles": candles}
            return candles
        except: return None

    # --- RECALIBRAÇÃO MECÂNICA (SEM IA) ---
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
                with self.api_lock: 
                    candles = self.api.get_candles(asset, 60, 120, int(time.time()))
                
                if not candles or len(candles) < 90: continue

                for s in self.strategies_pool:
                    wins = 0; total = 0
                    for i in range(len(candles) - backtest_steps - 2, len(candles) - 2):
                        window = candles[i-60:i+1]; result = candles[i+1]
                        sig, _ = self.check_strategy_signal(s, window, asset)
                        if not sig: continue
                        total += 1
                        win = (sig == "call" and result["close"] > result["open"]) or (sig == "put" and result["close"] < result["open"])
                        if win: wins += 1

                    if total >= 3:
                        k = (asset, now_dt.weekday(), now_dt.hour)
                        if k not in self.brain.stats: self.brain.stats[k] = {}
                        if s not in self.brain.stats[k]: self.brain.stats[k][s] = {"w": 0.0, "t": 0.0}
                        self.brain.stats[k][s]["w"] += float(wins)
                        self.brain.stats[k][s]["t"] += float(total)
                        self.brain.rebuild_key(asset, now_dt)

            except Exception as e:
                self.log_to_db(f"⚠️ Brain Recalib Erro {asset}: {e}", "DEBUG")

        self.last_recalibrate_ts = time.time()
        self.log_to_db("🧠 Brain: Recalibração concluída.", "SUCCESS")

    def pre_scan_window(self):
        sec = datetime.now(BR_TIMEZONE).second
        if sec < 30 or sec > 55: return
        if self.last_scan_second == sec: return
        self.last_scan_second = sec

        with self.dynamic_lock:
            allow_trading = bool(self.dynamic.get("allow_trading", True))
            min_conf = float(self.dynamic.get("min_confidence", 0.68))

        if not allow_trading or (time.time() - self.last_global_trade_ts < GLOBAL_COOLDOWN_SECONDS): return

        now_dt = datetime.now(BR_TIMEZONE)
        batch_size = SCAN_BATCH
        local_candidates = []
        active_pool = self.best_assets[:]
        
        for _ in range(batch_size):
            asset = active_pool[self.scan_cursor % len(active_pool)]
            self.scan_cursor += 1
            if time.time() < self.asset_cooldown.get(asset, 0): continue

            chosen, wr_hint, samples, src = self.brain.choose_strategy(asset, now_dt, self.strategies_pool)
            target_list = self.strategies_pool[:]

            candles = self.fetch_candles_cached(asset, need=60, ttl=SCAN_TTL)
            if not candles: continue

            best_local = None
            for strat in target_list:
                sig, lbl = self.check_strategy_signal(strat, candles, asset)
                if not sig: continue
                
                wr_pair = self.get_wr_pair(asset, strat)
                wr_window = wr_hint if strat == chosen and samples > 0 else 0.55
                mapped = self.asset_strategy_map.get(asset, {})
                mapped_conf = float(mapped.get("confidence", 0.0))

                base = 0.70
                conf = clamp((wr_pair * 0.70) + (mapped_conf * 0.30), 0.0, 0.95)
                score = (wr_pair * 0.75) + (conf * 0.25)
                
                cand = {
                    "asset": asset, "direction": sig, "strategy": strat, "label": lbl, 
                    "wr": wr_pair, "confidence": conf, "score": score,
                    "brain_src": src, "wr_window": wr_window
                }
                if (best_local is None) or (cand["score"] > best_local["score"]): best_local = cand

            if best_local and best_local["confidence"] >= min_conf:
                local_candidates.append(best_local)

        if local_candidates:
            with self.trade_lock: self.minute_candidates.extend(local_candidates)

    def reserve_best_candidate(self):
        sec = datetime.now(BR_TIMEZONE).second
        if sec < 56 or sec > 59: return
        if self.next_trade_plan or not self.check_daily_limits(): return

        with self.trade_lock:
            cands = list(self.minute_candidates)
            self.minute_candidates = [] 

        if not cands: return
        cands.sort(key=lambda x: x["score"], reverse=True)
        best = cands[0]
        
        self.next_trade_plan = best
        self.next_trade_key = datetime.now(BR_TIMEZONE).strftime("%Y%m%d%H%M")
        
        self.log_to_db(
            f"🧠 RESERVADO_FINAL: {best['asset']} {best['direction'].upper()} {best['strategy']} "
            f"conf={best['confidence']:.2f} score={best['score']:.3f}",
            "SYSTEM"
        )

    def execute_reserved(self):
        if not self.next_trade_plan or time.time() < self.pause_until_ts or not self.check_daily_limits(): self.next_trade_plan = None; return
        plan = self.next_trade_plan; self.next_trade_plan = None
        self.log_to_db(f"🚀 EXEC: {plan['asset']} {plan['direction'].upper()} {plan['strategy']}", "SYSTEM")
        self.launch_trade(asset=plan["asset"], direction=plan["direction"], strategy_key=plan["strategy"], strategy_label=plan["label"], plan=plan)

    def launch_trade(self, **kwargs):
        t = threading.Thread(target=self._trade_thread, kwargs=kwargs, daemon=True); t.start()

    def _trade_thread(self, asset, direction, strategy_key, strategy_label, plan):
        if time.time() - self.last_global_trade_ts < GLOBAL_COOLDOWN_SECONDS: return
        with self.trade_lock:
            if asset in self.active_trades: return
            self.active_trades.add(asset)

        signal_id = None
        try:
            base_amount = float(self.config["entry_value"])
            amount = self.get_dynamic_amount(base_amount, plan.get("confidence", 0.70))
            self.log_to_db(f"💰 Stake: base={base_amount} usado={amount}", "SYSTEM")

            signal_id = self.insert_signal(asset, direction, f"{strategy_key}::{strategy_label}", amount)
            balance_before = 0.0
            if self.config["mode"] == "LIVE":
                try: 
                    with self.api_lock: balance_before = self.api.get_balance()
                except: pass

            self.log_to_db(f"🟡 BUY: {asset} {direction.upper()} ${amount}", "INFO")
            if self.config["mode"] == "OBSERVE": status, trade_id = True, "VIRTUAL"
            else:
                with self.api_lock: status, trade_id = self.api.buy(amount, asset, direction, 1)

            if not status or not trade_id:
                self.log_to_db(f"❌ RECUSADA: {asset}", "ERROR"); self.update_signal(signal_id, "FAILED", "FAILED", 0.0); return

            self.last_global_trade_ts = time.time(); self.last_activity_ts = time.time()
            self.log_to_db(f"✅ ABERTA: {trade_id}", "INFO")
            
            self.push_balance_to_front()
            
            time.sleep(64)

            res_str = "UNKNOWN"; profit = 0.0; candles_after = []
            try:
                for _ in range(2):
                    with self.api_lock: candles_after = self.api.get_candles(asset, 60, 3, int(time.time()))
                    if candles_after: break
                    time.sleep(1)
            except: pass

            if self.config["mode"] == "OBSERVE":
                last = self.get_last_closed_candle(candles_after, now_ts=int(time.time()))
                if last:
                    win = (direction == "call" and last["close"] > last["open"]) or (direction == "put" and last["close"] < last["open"])
                    res_str = "WIN" if win else "LOSS"; profit = (amount * 0.87) if win else -amount
                else: res_str = "UNKNOWN"; profit = 0.0
            else:
                bal_after = balance_before; delta = 0.0
                for _ in range(7):
                    try:
                        with self.api_lock: bal_after = self.api.get_balance()
                        delta = bal_after - balance_before
                        if abs(delta) > 0.01: break
                    except: pass
                    time.sleep(1)
                
                if delta > 0.01: res_str = "WIN"; profit = delta
                elif delta < -0.01: res_str = "LOSS"; profit = delta
                else: res_str = "DOJI"

            if res_str in ["WIN", "LOSS"]:
                self.pair_strategy_memory[(asset, strategy_key)].append(1 if res_str == "WIN" else 0)
                self.session_memory.append(1 if res_str == "WIN" else 0)
                self.brain.update_result(asset, datetime.now(BR_TIMEZONE), strategy_key, res_str == "WIN")

            if res_str != "DOJI":
                self.daily_total += 1
                if res_str == "WIN":
                    self.daily_wins += 1; self.win_streak += 1; self.loss_streak = 0
                elif res_str == "LOSS":
                    self.daily_losses += 1; self.loss_streak += 1; self.win_streak = 0
                    self.asset_cooldown[asset] = time.time() + ASSET_LOSS_COOLDOWN_SECONDS
                    self.log_to_db(f"🚫 Cooldown: {asset}", "INFO")
                    with self.dynamic_lock: self.dynamic["min_confidence"] = min(0.90, self.dynamic["min_confidence"] + 0.04)
                    self.log_to_db(f"🛡️ Defesa (+): Conf={self.dynamic['min_confidence']:.2f}", "WARNING")

            with self.dynamic_lock:
                pause_win = int(self.dynamic.get("pause_win_streak", 2)); pause_win_s = int(self.dynamic.get("pause_win_seconds", 180))
                pause_loss = int(self.dynamic.get("pause_loss_streak", 2)); pause_loss_s = int(self.dynamic.get("pause_loss_seconds", 900))

            if self.win_streak >= pause_win:
                self.pause_until_ts = time.time() + pause_win_s; self.log_to_db(f"😴 PAUSA WIN: {pause_win} wins", "SYSTEM"); self.win_streak = 0
            if self.loss_streak >= pause_loss:
                self.pause_until_ts = time.time() + pause_loss_s; self.log_to_db(f"🛑 PAUSA LOSS: {pause_loss} losses", "WARNING")

            self.update_signal(signal_id, res_str, res_str, float(profit))
            self.push_balance_to_front()
            
            lvl = "SUCCESS" if res_str == "WIN" else "ERROR"
            self.log_to_db(f"{'🏆' if res_str=='WIN' else '🔻'} {res_str}: {profit:.2f} | {self.daily_wins}W/{self.daily_losses}L", lvl)
        finally:
            with self.trade_lock: self.active_trades.discard(asset)

    def start(self):
        threading.Thread(target=watchdog, daemon=True).start()
        self.log_to_db("🧠 Inicializando Bot (Mechanical Brain)...", "SYSTEM")
        
        if not hasattr(self, "last_heartbeat_ts"): self.last_heartbeat_ts = 0
        if not hasattr(self, "last_config_ts"): self.last_config_ts = 0
        if not hasattr(self, "last_activity_ts"): self.last_activity_ts = time.time()

        # Teste de IA
        self.commander.check_connection()

        if not self.api or not self.connect(): time.sleep(3)
        
        self.recalibrate_current_hour()

        with self.trade_lock: self.minute_candidates = []

        while True:
            try:
                if time.time() - self.last_heartbeat_ts >= 30: self.last_heartbeat_ts = time.time(); self.touch_watchdog()
                
                if int(time.time()) % 10 == 0: self.push_balance_to_front()

                self.reset_daily_if_needed()
                if time.time() - self.last_config_ts >= 5: self.fetch_config(); self.last_config_ts = time.time()
                if not self.api or not self.api.check_connect():
                    if not self.connect(): time.sleep(5); continue
                if self.config["status"] == "PAUSED" or time.time() < self.pause_until_ts: time.sleep(1); continue
                
                if (time.time() - self.last_recalibrate_ts) > 1800: self.recalibrate_current_hour()
                
                sec = datetime.now(BR_TIMEZONE).second
                if 30 <= sec <= 55: self.pre_scan_window()
                elif 56 <= sec <= 59: self.reserve_best_candidate()
                elif sec in NEXT_CANDLE_EXEC_SECONDS: self.execute_reserved()
                
                if sec == 2:
                    with self.trade_lock:
                        if self.minute_candidates: self.minute_candidates = []

                time.sleep(0.1)
            except Exception as e: self.log_to_db(f"❌ Loop: {e}", "ERROR"); time.sleep(3)

if __name__ == "__main__":
    SimpleBot().start()
