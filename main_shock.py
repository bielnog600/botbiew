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
from collections import deque

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


BOT_VERSION = "SHOCK_ENGINE_V56_OPTIMIZED_2026-01-26"
print(f"🚀 START::{BOT_VERSION}")

# ==============================================================================
# CONFIGURAÇÃO E AMBIENTE
# ==============================================================================
# Tenta pegar do ambiente, se não tiver, usa valores placeholder (mas avisa)
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

EXNOVA_EMAIL = os.environ.get("EXNOVA_EMAIL", "")
EXNOVA_PASSWORD = os.environ.get("EXNOVA_PASSWORD", "")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# Fuso Horário (Ajuste conforme necessário)
BR_TIMEZONE = timezone(timedelta(hours=-3))

# Entrada na próxima vela: reserva 58-59s e executa 00-01s
NEXT_CANDLE_EXEC_SECONDS = [0, 1]
RESERVE_SECONDS = [58, 59]

# Cooldowns
GLOBAL_COOLDOWN_SECONDS = 50
ASSET_LOSS_COOLDOWN_SECONDS = 180

# Validação básica de credenciais
if not EXNOVA_EMAIL or not EXNOVA_PASSWORD:
    print("⚠️ AVISO: EXNOVA_EMAIL ou EXNOVA_PASSWORD não configurados nas variáveis de ambiente.")

# ==============================================================================
# LOGGING
# ==============================================================================
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
# Silenciar logs ruidosos da API e bibliotecas
for logger_name in ["websocket", "exnovaapi", "iqoptionapi", "urllib3", "iqoptionapi.websocket.client"]:
    logging.getLogger(logger_name).setLevel(logging.CRITICAL)

LAST_LOG_TIME = time.time()

def watchdog():
    """Monitora se o bot travou e reinicia se necessário"""
    global LAST_LOG_TIME
    print("[WATCHDOG] Monitoramento iniciado.")
    while True:
        time.sleep(60)
        # Se passar 5 minutos (300s) sem log, considera travado
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
        if len(candles) < period:
            return 0
        prices = [c["close"] for c in candles]
        ema = sum(prices[:period]) / period
        k = 2 / (period + 1)
        for price in prices[period:]:
            ema = (price * k) + (ema * (1 - k))
        return ema

    @staticmethod
    def analyze_candle(candle):
        o = candle["open"]
        c = candle["close"]
        h = candle["max"]
        l = candle["min"]

        body = abs(c - o)
        rng = max(h - l, 1e-12)

        color = "green" if c > o else "red" if c < o else "doji"
        upper = h - max(o, c)
        lower = min(o, c) - l

        return {
            "open": o, "close": c, "max": h, "min": l,
            "body": body, "range": rng,
            "upper_wick": upper, "lower_wick": lower,
            "color": color, "volume": candle.get("volume", 0)
        }

    @staticmethod
    def check_compression(candles):
        if len(candles) < 20:
            return False
        closed = candles[:-1]
        ema9 = TechnicalAnalysis.calculate_ema(closed, 9)
        ema21 = TechnicalAnalysis.calculate_ema(closed, 21)
        
        bodies = [abs(c["close"] - c["open"]) for c in closed[-10:]]
        avg_body = sum(bodies) / len(bodies) if bodies else 0.00001
        
        spread = abs(ema9 - ema21)
        return spread < (avg_body * 0.15)

    @staticmethod
    def get_signal_v2(candles):
        if len(candles) < 60:
            return None, "Dados insuficientes"

        closed = candles[:-1]
        ema9 = TechnicalAnalysis.calculate_ema(closed, 9)
        ema21 = TechnicalAnalysis.calculate_ema(closed, 21)
        ema21_prev = TechnicalAnalysis.calculate_ema(closed[:-1], 21)

        c_confirm = TechnicalAnalysis.analyze_candle(candles[-2])
        c_reject = TechnicalAnalysis.analyze_candle(candles[-3])

        slope = ema21 - ema21_prev

        # Alta
        if ema9 > ema21 and slope > 0:
            if c_reject["color"] == "red" and c_confirm["color"] == "green":
                return "call", "V2_CALL"
        # Baixa
        if ema9 < ema21 and slope < 0:
            if c_reject["color"] == "green" and c_confirm["color"] == "red":
                return "put", "V2_PUT"
        
        return None, "Sem V2"

class ShockLiveDetector:
    @staticmethod
    def detect(candles, asset_name, dynamic_config=None):
        if len(candles) < 30:
            return None, "Dados insuficientes", {}

        dyn = dynamic_config or {}
        if not bool(dyn.get("shock_enabled", True)):
            return None, "Shock OFF", {}

        body_mult = float(dyn.get("shock_body_mult", 1.5))
        range_mult = float(dyn.get("shock_range_mult", 1.4))
        close_pos_min = float(dyn.get("shock_close_pos_min", 0.85))
        pullback_ratio_max = float(dyn.get("shock_pullback_ratio_max", 0.25))
        trend_filter = bool(dyn.get("trend_filter_enabled", True))

        live = TechnicalAnalysis.analyze_candle(candles[-1])
        closed = candles[:-1]

        ema9 = TechnicalAnalysis.calculate_ema(closed, 9)
        ema21 = TechnicalAnalysis.calculate_ema(closed, 21)
        trend_up = ema9 > ema21
        trend_down = ema9 < ema21

        bodies = [abs(c["close"] - c["open"]) for c in closed[-20:]]
        ranges = [(c["max"] - c["min"]) for c in closed[-20:]]
        avg_body = (sum(bodies) / len(bodies)) if bodies else 0.00001
        avg_range = (sum(ranges) / len(ranges)) if ranges else 0.00001

        body_live = live["body"]
        range_live = live["range"]

        explosive = (body_live >= avg_body * body_mult) and (range_live >= avg_range * range_mult)
        if not explosive:
            return None, "Sem explosão", {"body_mult": body_mult}

        super_mult = max(2.2, body_mult + 0.8)
        super_explosive = (body_live >= avg_body * super_mult) and (range_live >= avg_range * super_mult)

        close_pos = (live["close"] - live["min"]) / range_live
        
        # Pullback check
        pullback = 0
        if live["color"] == "green":
            pullback = live["max"] - live["close"]
        elif live["color"] == "red":
            pullback = live["close"] - live["min"]
        
        pullback_ratio = pullback / range_live

        # Lógica de Reversão (Shock)
        if live["color"] == "green":
            if trend_filter and trend_up and not super_explosive:
                return None, "Contra trend alta", {}
            if close_pos >= close_pos_min and pullback_ratio <= pullback_ratio_max:
                return "put", "SHOCK_UP", {}
        
        if live["color"] == "red":
            if trend_filter and trend_down and not super_explosive:
                return None, "Contra trend baixa", {}
            if close_pos <= (1.0 - close_pos_min) and pullback_ratio <= pullback_ratio_max:
                return "call", "SHOCK_DOWN", {}

        return None, "Sem padrão", {}

class TendMaxStrategy:
    @staticmethod
    def get_signal(candles):
        if len(candles) < 50:
            return None, "Dados insuficientes"
        ema5 = TechnicalAnalysis.calculate_ema(candles[:-1], 5)
        ema10 = TechnicalAnalysis.calculate_ema(candles[:-1], 10)
        if ema5 > ema10:
            return "call", "TENDMAX_CALL"
        if ema5 < ema10:
            return "put", "TENDMAX_PUT"
        return None, "Sem cruzamento"

class TsunamiFlowStrategy:
    @staticmethod
    def get_signal(candles):
        if len(candles) < 6:
            return None, "Dados insuficientes"
        c1 = TechnicalAnalysis.analyze_candle(candles[-2])
        c2 = TechnicalAnalysis.analyze_candle(candles[-3])
        c3 = TechnicalAnalysis.analyze_candle(candles[-4])

        if c1["color"] == "green" and c2["color"] == "green" and c3["color"] == "green":
            if c1["body"] > c2["body"]:
                return "call", "TSUNAMI_UP"
        if c1["color"] == "red" and c2["color"] == "red" and c3["color"] == "red":
            if c1["body"] > c2["body"]:
                return "put", "TSUNAMI_DOWN"
        return None, "Sem fluxo"

class VolumeReactorStrategy:
    @staticmethod
    def get_signal(candles):
        if len(candles) < 30:
            return None, "Dados insuficientes"
        c1 = TechnicalAnalysis.analyze_candle(candles[-2])
        bodies = [abs(c["close"] - c["open"]) for c in candles[-22:-2]]
        avg_body = sum(bodies) / len(bodies) if bodies else 0.00001
        
        if c1["body"] > avg_body * 2.5:
            if c1["color"] == "green":
                return "put", "REACTOR_TOP"
            if c1["color"] == "red":
                return "call", "REACTOR_BOTTOM"
        return None, "Sem reactor"

# ==============================================================================
# IA COMMANDER
# ==============================================================================
class AICommander:
    def __init__(self, log_fn):
        self.log_fn = log_fn

    def log(self, msg, level="DEBUG"):
        try:
            self.log_fn(msg, level)
        except:
            pass

    def _call_openai(self, prompt):
        if not OPENAI_API_KEY:
            return None
        try:
            headers = {"Content-Type": "application/json", "Authorization": f"Bearer {OPENAI_API_KEY}"}
            payload = {
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2
            }
            r = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=20)
            if r.status_code == 200:
                content = r.json()["choices"][0]["message"]["content"]
                return safe_json_extract(content)
        except Exception as e:
            self.log(f"⚠️ OPENAI_EX::{e}", "ERROR")
        return None

    def _call_gemini(self, prompt):
        if not GEMINI_API_KEY:
            return None
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
            payload = {"contents": [{"parts": [{"text": prompt}]}]}
            r = requests.post(url, json=payload, timeout=20)
            if r.status_code == 200:
                text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                return safe_json_extract(text)
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
        Se estiver ruim ou confuso, responda NO_TRADE.
        Dados: {json.dumps(asset_data, ensure_ascii=False)}
        Estratégias: SHOCK_REVERSAL, V2_TREND, TENDMAX, TSUNAMI_FLOW, VOLUME_REACTOR, NO_TRADE
        JSON: {{"strategy":"NOME","confidence":0.0-1.0,"reason":"curto"}}
        """
        return self.call(prompt)

    def global_tune(self, market_summary):
        prompt = f"""
        Você é o Commander Global. Ajuste o comportamento.
        Resumo: {json.dumps(market_summary, ensure_ascii=False)}
        JSON: {{ "allow_trading": true, "prefer_strategy": "AUTO", "min_confidence": 0.75, "pause_win_streak": 2, "pause_win_seconds": 180, "pause_loss_streak": 2, "pause_loss_seconds": 900, "shock_enabled": true, "reason": "curto" }}
        """
        return self.call(prompt)

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

        self.active_trades = set()
        self.next_trade_plan = None
        self.next_trade_key = None
        self.asset_cooldown = {}
        self.last_global_trade_ts = 0

        self.current_date = datetime.now(BR_TIMEZONE).date()
        self.daily_wins = 0
        self.daily_losses = 0
        self.daily_total = 0
        self.win_streak = 0
        self.loss_streak = 0
        self.pause_until_ts = 0

        self.best_assets = [
            "EURUSD-OTC", "EURGBP-OTC", "USDCHF-OTC", "EURJPY-OTC",
            "NZDUSD-OTC", "GBPUSD-OTC", "GBPJPY-OTC", "USDJPY-OTC",
            "AUDCAD-OTC", "AUDUSD-OTC", "USDCAD-OTC", "AUDJPY-OTC"
        ]

        self.strategy_memory = {
            "SHOCK_REVERSAL": deque(maxlen=30),
            "V2_TREND": deque(maxlen=30),
            "TENDMAX": deque(maxlen=30),
            "TSUNAMI_FLOW": deque(maxlen=30),
            "VOLUME_REACTOR": deque(maxlen=30),
        }

        self.dynamic = {
            "allow_trading": True, "prefer_strategy": "AUTO", "min_confidence": 0.75,
            "pause_win_streak": 2, "pause_win_seconds": 180,
            "pause_loss_streak": 2, "pause_loss_seconds": 900,
            "shock_enabled": True, "shock_body_mult": 1.5, "shock_range_mult": 1.4,
            "shock_close_pos_min": 0.85, "shock_pullback_ratio_max": 0.25,
            "trend_filter_enabled": True,
        }

        self.asset_strategy_map = {}
        self.last_calibration_time = 0
        self.calibration_running = False

        self.last_config_ts = 0
        self.last_heartbeat_ts = 0
        self.last_activity_ts = time.time()

        self.config = {
            "status": "PAUSED",
            "account_type": "PRACTICE",
            "entry_value": 1.0,
            "max_trades_per_day": 0, "max_wins_per_day": 0, "max_losses_per_day": 0,
            "mode": "LIVE", "strategy_mode": "AUTO"
        }

        self.init_supabase()
        self.commander = AICommander(self.log_to_db)

    # -------------------- INFRAESTRUTURA --------------------
    def touch_watchdog(self):
        global LAST_LOG_TIME
        LAST_LOG_TIME = time.time()

    def init_supabase(self):
        try:
            if not SUPABASE_URL or not SUPABASE_KEY:
                print("⚠️ Supabase: Credenciais incompletas. Logs remotos desativados.")
                self.supabase = None
                return

            self.supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
            print("✅ Supabase conectado.")
        except Exception as e:
            print(f"❌ Erro Supabase: {e}")
            self.supabase = None

    def log_to_db(self, message, level="INFO"):
        self.touch_watchdog()
        print(f"[{level}] {message}")

        if level == "DEBUG" or not self.supabase:
            return

        try:
            with self.db_lock:
                self.supabase.table("logs").insert(
                    {"message": message, "level": level, "created_at": datetime.now(timezone.utc).isoformat()}
                ).execute()
        except:
            pass

    def log_json(self, tag, payload, level="DEBUG"):
        try:
            s = json.dumps(payload, ensure_ascii=False)
        except:
            s = str(payload)
        self.log_to_db(f"{tag}::{s}", level)

    # -------------------- DB SIGNALS --------------------
    def insert_signal(self, asset, direction, strategy, amount, status="PENDING", result="PENDING", profit=0.0):
        if not self.supabase:
            return None
        payload = {
            "pair": asset, "direction": direction, "strategy": strategy,
            "status": status, "result": result, "profit": profit,
            "amount": float(amount), "created_at": datetime.now(timezone.utc).isoformat()
        }
        try:
            with self.db_lock:
                res = self.supabase.table("trade_signals").insert(payload).execute()
            if res.data:
                return res.data[0].get("id")
        except:
            pass
        return None

    def update_signal(self, signal_id, status, result, profit):
        if not self.supabase or not signal_id:
            return
        try:
            with self.db_lock:
                self.supabase.table("trade_signals").update(
                    {"status": status, "result": result, "profit": profit}
                ).eq("id", signal_id).execute()
        except:
            pass

    # -------------------- EXNOVA CONEXÃO --------------------
    def connect(self):
        self.log_to_db("🔌 Conectando Exnova...", "SYSTEM")
        try:
            with self.api_lock:
                if self.api:
                    try:
                        self.api.api.close()
                    except:
                        pass
                
                # Instância da API
                self.api = Exnova(EXNOVA_EMAIL, EXNOVA_PASSWORD)
                ok, reason = self.api.connect()

                if ok:
                    self.log_to_db("✅ Conectado!", "SUCCESS")
                    self.api.change_balance(self.config["account_type"])
                    return True
                else:
                    self.log_to_db(f"❌ Falha conexão: {reason}", "ERROR")
        except Exception as e:
            self.log_to_db(f"❌ Erro conexão: {e}", "ERROR")
        return False

    def fetch_config(self):
        if not self.supabase:
            return
        try:
            with self.db_lock:
                res = self.supabase.table("bot_config").select("*").eq("id", 1).execute()
            if res.data:
                d = res.data[0]
                self.config.update({
                    "status": str(d.get("status", "PAUSED")).strip().upper(),
                    "mode": str(d.get("mode", "LIVE")).strip().upper(),
                    "strategy_mode": str(d.get("strategy_mode", "AUTO")).strip().upper().replace(" ", "_"),
                    "entry_value": float(d.get("entry_value", 1.0) or 1.0),
                    "account_type": str(d.get("account_type", "PRACTICE")).strip().upper(),
                    "max_trades_per_day": int(d.get("max_trades_per_day", 0) or 0),
                    "max_wins_per_day": int(d.get("max_wins_per_day", 0) or 0),
                    "max_losses_per_day": int(d.get("max_losses_per_day", 0) or 0),
                })
        except:
            pass

    # -------------------- LIMITES DIÁRIOS --------------------
    def reset_daily_if_needed(self):
        today = datetime.now(BR_TIMEZONE).date()
        if today != self.current_date:
            self.current_date = today
            self.daily_wins = 0
            self.daily_losses = 0
            self.daily_total = 0
            self.win_streak = 0
            self.loss_streak = 0
            self.pause_until_ts = 0
            self.next_trade_plan = None
            self.asset_cooldown = {}
            self.log_to_db("🚀 Nova sessão diária", "SYSTEM")

    def check_daily_limits(self):
        if self.config["max_trades_per_day"] > 0 and self.daily_total >= self.config["max_trades_per_day"]:
            self.log_to_db("🛑 Limite de trades do dia atingido", "WARNING")
            return False
        if self.config["max_wins_per_day"] > 0 and self.daily_wins >= self.config["max_wins_per_day"]:
            self.log_to_db("🏆 Meta de wins atingida", "SUCCESS")
            return False
        if self.config["max_losses_per_day"] > 0 and self.daily_losses >= self.config["max_losses_per_day"]:
            self.log_to_db("❌ Limite de losses atingido", "ERROR")
            return False
        return True

    def get_wr(self, strategy):
        mem = self.strategy_memory.get(strategy)
        if not mem:
            return 0.55
        return sum(mem) / len(mem)

    # -------------------- VERIFICADOR DE SINAL --------------------
    def check_strategy_signal(self, strategy_name, candles, asset_name=""):
        if strategy_name == "SHOCK_REVERSAL":
            with self.dynamic_lock:
                dyn = self.dynamic.copy()
            sig, lbl, _ = ShockLiveDetector.detect(candles, asset_name, dyn)
            return sig, lbl
        if strategy_name == "V2_TREND":
            if TechnicalAnalysis.check_compression(candles):
                return None, "Compressão"
            return TechnicalAnalysis.get_signal_v2(candles)
        if strategy_name == "TENDMAX":
            return TendMaxStrategy.get_signal(candles)
        if strategy_name == "TSUNAMI_FLOW":
            return TsunamiFlowStrategy.get_signal(candles)
        if strategy_name == "VOLUME_REACTOR":
            return VolumeReactorStrategy.get_signal(candles)
        return None, "Estratégia inválida"

    # -------------------- CALIBRATION (COMMANDER) --------------------
    def calibrate_market(self):
        if self.calibration_running:
            return
        self.calibration_running = True
        self.log_to_db("🔬 COMMANDER: calibrando mercado...", "SYSTEM")
        threading.Thread(target=self._run_calibration_task, daemon=True).start()

    def _run_calibration_task(self):
        try:
            if not self.api or not self.api.check_connect():
                return

            strategies = ["SHOCK_REVERSAL", "V2_TREND", "TENDMAX", "TSUNAMI_FLOW", "VOLUME_REACTOR"]
            new_map = {}
            map_log = []
            total_trades = 0
            total_wins = 0
            total_vol = 0.0
            strat_counts = {s: 0 for s in strategies}

            for asset in self.best_assets:
                try:
                    time.sleep(2)
                    with self.api_lock:
                        candles = self.api.get_candles(asset, 60, 120, int(time.time()))
                    if not candles or len(candles) < 100:
                        map_log.append(f"{asset}=NO_DATA")
                        continue

                    # Mini Backtest
                    scores = {s: {"wins": 0, "total": 0} for s in strategies}
                    for i in range(60, len(candles) - 2):
                        window = candles[i - 60: i + 1]
                        result = candles[i + 1]
                        for s in strategies:
                            sig, _ = self.check_strategy_signal(s, window, asset)
                            if sig:
                                scores[s]["total"] += 1
                                total_trades += 1
                                win = (sig == "call" and result["close"] > result["open"]) or (sig == "put" and result["close"] < result["open"])
                                if win:
                                    scores[s]["wins"] += 1
                                    total_wins += 1
                    
                    bodies = [abs(c["close"] - c["open"]) for c in candles[-20:]]
                    avg_body = sum(bodies) / len(bodies) if bodies else 0.0001
                    last_body = abs(candles[-1]["close"] - candles[-1]["open"])
                    volatility = round(last_body / avg_body, 2)
                    total_vol += volatility

                    formatted_scores = {}
                    for s in strategies:
                        t = scores[s]["total"]
                        w = scores[s]["wins"]
                        wr = int((w / t) * 100) if t > 0 else 0
                        formatted_scores[s] = f"{wr}% ({w}/{t})"

                    asset_data = {"asset": asset, "volatility": volatility, "scores": formatted_scores}
                    decision = self.commander.choose_strategy(asset_data)

                    strat = "NO_TRADE"
                    conf = 0.0
                    reason = "sem IA"
                    provider = "AI"

                    if decision:
                        strat = str(decision.get("strategy", "NO_TRADE")).strip().upper()
                        conf = float(decision.get("confidence", 0.0))
                        reason = decision.get("reason", "n/a")
                        provider = decision.get("provider", "AI")
                        self.log_to_db(f"🤖 {provider}::{asset} -> {strat} ({reason})", "DEBUG")

                    if strat in strategies and conf >= 0.55:
                        new_map[asset] = {"strategy": strat, "confidence": conf}
                        strat_counts[strat] += 1
                        map_log.append(f"{asset}={strat}")
                    else:
                        map_log.append(f"{asset}=NO_TRADE")

                except Exception as e:
                    self.log_to_db(f"⚠️ Calib asset erro {asset}: {e}", "DEBUG")

            # Tune global
            avg_vol = round(total_vol / len(self.best_assets), 2) if self.best_assets else 1.0
            avg_wr = int((total_wins / total_trades) * 100) if total_trades > 0 else 0
            dominant = max(strat_counts, key=strat_counts.get) if any(strat_counts.values()) else "MIXED"

            tune = self.commander.global_tune({
                "avg_volatility": avg_vol, "avg_wr": avg_wr, "dominant_strat": dominant
            })

            if tune:
                allowed = set(self.dynamic.keys())
                clean = {}
                for k, v in tune.items():
                    if k in allowed: clean[k] = v
                with self.dynamic_lock:
                    self.dynamic.update(clean)
                self.log_to_db(f"🧠 GLOBAL::{tune.get('provider','AI')} -> {tune.get('reason','ok')}", "SYSTEM")
                self.log_json("GLOBAL_DYNAMIC", self.dynamic, "DEBUG")

            self.asset_strategy_map = new_map
            self.last_calibration_time = time.time()
            self.log_to_db("🏁 Commander: mapa atualizado", "SUCCESS")

        finally:
            self.calibration_running = False

    # -------------------- SCAN & RESERVE (58-59s) --------------------
    def scan_and_reserve(self):
        if self.next_trade_plan or not self.check_daily_limits():
            return

        with self.dynamic_lock:
            allow_trading = bool(self.dynamic.get("allow_trading", True))
            prefer_strategy = str(self.dynamic.get("prefer_strategy", "AUTO")).strip().upper()
            min_conf = float(self.dynamic.get("min_confidence", 0.75))

        if not allow_trading:
            return

        if time.time() - self.last_global_trade_ts < GLOBAL_COOLDOWN_SECONDS:
            return

        assets = self.best_assets[:]
        random.shuffle(assets)
        strategies_pool = ["V2_TREND", "TSUNAMI_FLOW", "VOLUME_REACTOR", "TENDMAX", "SHOCK_REVERSAL"]
        candidates = []
        scan_info = []

        # LOOP PROTEGIDO: Pára se sair da janela de análise (58-59s)
        for asset in assets:
            current_second = datetime.now(BR_TIMEZONE).second
            if current_second not in RESERVE_SECONDS:
                self.log_to_db("⚠️ SCAN: Tempo limite excedido, parando scan.", "WARNING")
                break

            if time.time() < self.asset_cooldown.get(asset, 0):
                scan_info.append(f"{asset}:CD")
                continue

            mapped = self.asset_strategy_map.get(asset)
            mapped_strat = mapped["strategy"] if mapped else "NO_TRADE"
            mapped_conf = float(mapped["confidence"]) if mapped else 0.0

            if mapped_strat == "NO_TRADE":
                scan_info.append(f"{asset}:NO")
                continue

            target_list = []
            if mapped_strat != "NO_TRADE": target_list.append(mapped_strat)
            if prefer_strategy != "AUTO" and prefer_strategy in strategies_pool and prefer_strategy not in target_list:
                target_list.insert(0, prefer_strategy)
            for s in strategies_pool:
                if s not in target_list: target_list.append(s)

            try:
                with self.api_lock:
                    candles = self.api.get_candles(asset, 60, 60, int(time.time()))
                if not candles:
                    scan_info.append(f"{asset}:NO_DATA")
                    continue

                best_local = None
                for strat in target_list:
                    sig, lbl = self.check_strategy_signal(strat, candles, asset)
                    if not sig: continue

                    wr = self.get_wr(strat)
                    base_conf = mapped_conf if strat == mapped_strat else 0.70
                    conf = clamp((base_conf * 0.65) + (wr * 0.35), 0.0, 0.95)
                    score = (wr * 0.7) + (conf * 0.3)
                    
                    cand = {
                        "asset": asset, "direction": sig, "strategy": strat,
                        "label": lbl, "wr": round(wr, 3), "confidence": round(conf, 3),
                        "score": round(score, 3),
                    }
                    if (best_local is None) or (cand["score"] > best_local["score"]):
                        best_local = cand

                if best_local:
                    if best_local["confidence"] >= min_conf:
                        candidates.append(best_local)
                        scan_info.append(f"{asset}:OK({best_local['strategy']})")
                    else:
                        scan_info.append(f"{asset}:LOWCONF")
                else:
                    scan_info.append(f"{asset}:NOSIG")
            except:
                scan_info.append(f"{asset}:ERR")

        if not candidates:
            self.log_to_db("⛔ SKIP: nenhum candidato bom", "INFO")
            return

        candidates.sort(key=lambda x: x["score"], reverse=True)
        best = candidates[0]
        self.next_trade_plan = best
        self.next_trade_key = datetime.now(BR_TIMEZONE).strftime("%Y%m%d%H%M")
        self.log_to_db(f"🧠 RESERVADO_NEXT: {best['asset']} {best['direction'].upper()} {best['strategy']} conf={best['confidence']}", "SYSTEM")

    # -------------------- EXECUTE RESERVED --------------------
    def execute_reserved(self):
        if not self.next_trade_plan or time.time() < self.pause_until_ts or not self.check_daily_limits():
            self.next_trade_plan = None
            return

        plan = self.next_trade_plan
        self.next_trade_plan = None
        self.log_to_db(f"🚀 EXEC_NEXT: {plan['asset']} {plan['direction'].upper()} {plan['strategy']} ({plan['label']})", "SYSTEM")
        self.launch_trade(
            asset=plan["asset"], direction=plan["direction"],
            strategy_key=plan["strategy"], strategy_label=plan["label"]
        )

    # -------------------- TRADE THREAD --------------------
    def launch_trade(self, **kwargs):
        t = threading.Thread(target=self._trade_thread, kwargs=kwargs, daemon=True)
        t.start()

    def _trade_thread(self, asset, direction, strategy_key, strategy_label):
        now = time.time()
        if now - self.last_global_trade_ts < GLOBAL_COOLDOWN_SECONDS:
            return

        with self.trade_lock:
            if asset in self.active_trades:
                return
            self.active_trades.add(asset)

        signal_id = None
        try:
            amount = float(self.config["entry_value"])
            strat_name = f"{strategy_key}::{strategy_label}"
            signal_id = self.insert_signal(asset, direction, strat_name, amount, status="PENDING", result="PENDING", profit=0.0)

            balance_before = 0.0
            if self.config["mode"] == "LIVE":
                try:
                    with self.api_lock:
                        balance_before = self.api.get_balance()
                except:
                    pass

            self.log_to_db(f"🟡 BUY: {asset} {direction.upper()} ${amount} [{strat_name}]", "INFO")

            if self.config["mode"] == "OBSERVE":
                status, trade_id = True, "VIRTUAL"
            else:
                with self.api_lock:
                    status, trade_id = self.api.buy(amount, asset, direction, 1)

            if not status or not trade_id:
                self.log_to_db(f"❌ RECUSADA: {asset}", "ERROR")
                self.update_signal(signal_id, "FAILED", "FAILED", 0.0)
                return

            self.last_global_trade_ts = time.time()
            self.last_activity_ts = time.time()
            self.log_to_db(f"✅ ABERTA: {trade_id}", "INFO")
            
            # Aguarda resultado
            time.sleep(64)
            res_str = "UNKNOWN"
            profit = 0.0

            if self.config["mode"] == "OBSERVE":
                with self.api_lock:
                    candles = self.api.get_candles(asset, 60, 2, int(time.time()))
                last = candles[-2]
                win = (direction == "call" and last["close"] > last["open"]) or (direction == "put" and last["close"] < last["open"])
                res_str = "WIN" if win else "LOSS"
                profit = (amount * 0.87) if win else -amount
            else:
                # Checagem por saldo (Fallback robusto)
                bal_after = balance_before
                delta = 0.0
                for _ in range(7):
                    try:
                        with self.api_lock:
                            bal_after = self.api.get_balance()
                        delta = bal_after - balance_before
                        if abs(delta) > 0.01: break
                    except: pass
                    time.sleep(1)

                if delta > 0.01:
                    res_str = "WIN"
                    profit = delta
                elif delta < -0.01:
                    res_str = "LOSS"
                    profit = delta
                else:
                    res_str = "DOJI"
                    profit = 0.0

            if res_str in ["WIN", "LOSS"] and strategy_key in self.strategy_memory:
                self.strategy_memory[strategy_key].append(1 if res_str == "WIN" else 0)

            if res_str != "DOJI":
                self.daily_total += 1
                if res_str == "WIN":
                    self.daily_wins += 1
                    self.win_streak += 1
                    self.loss_streak = 0
                elif res_str == "LOSS":
                    self.daily_losses += 1
                    self.loss_streak += 1
                    self.win_streak = 0
                    self.asset_cooldown[asset] = time.time() + ASSET_LOSS_COOLDOWN_SECONDS
                    self.log_to_db(f"🚫 Cooldown no ativo {asset} por {ASSET_LOSS_COOLDOWN_SECONDS}s", "INFO")

            # Pause Logic
            with self.dynamic_lock:
                pause_win_streak = int(self.dynamic.get("pause_win_streak", 2))
                pause_win_seconds = int(self.dynamic.get("pause_win_seconds", 180))
                pause_loss_streak = int(self.dynamic.get("pause_loss_streak", 2))
                pause_loss_seconds = int(self.dynamic.get("pause_loss_seconds", 900))

            if self.win_streak >= pause_win_streak:
                self.pause_until_ts = time.time() + pause_win_seconds
                self.log_to_db(f"😴 PAUSA WIN: {pause_win_streak} wins -> {pause_win_seconds}s", "SYSTEM")
                self.win_streak = 0
            if self.loss_streak >= pause_loss_streak:
                self.pause_until_ts = time.time() + pause_loss_seconds
                self.log_to_db(f"🛑 PAUSA LOSS: {pause_loss_streak} losses -> {pause_loss_seconds}s", "WARNING")

            if res_str == "DOJI":
                self.update_signal(signal_id, "DOJI", "DOJI", 0.0)
            else:
                self.update_signal(signal_id, res_str, res_str, float(profit))

            level = "SUCCESS" if res_str == "WIN" else "ERROR"
            self.log_to_db(f"{'🏆' if res_str=='WIN' else '🔻'} {res_str}: {profit:.2f} | {self.daily_wins}W/{self.daily_losses}L", level)

        finally:
            with self.trade_lock:
                self.active_trades.discard(asset)

    # -------------------- START --------------------
    def start(self):
        threading.Thread(target=watchdog, daemon=True).start()
        self.log_to_db("🧠 Inicializando Bot...", "SYSTEM")

        if not self.api or not self.connect():
            time.sleep(3)
        
        # Inicia calibração
        threading.Thread(target=self._run_calibration_task, daemon=True).start()

        while True:
            try:
                if time.time() - self.last_heartbeat_ts >= 30:
                    self.last_heartbeat_ts = time.time()
                    self.touch_watchdog()

                self.reset_daily_if_needed()

                if time.time() - self.last_config_ts >= 5:
                    self.fetch_config()
                    self.last_config_ts = time.time()

                if not self.api or not self.api.check_connect():
                    if not self.connect():
                        time.sleep(5)
                        continue

                if self.config["status"] == "PAUSED" or time.time() < self.pause_until_ts:
                    time.sleep(1)
                    continue

                if (time.time() - self.last_calibration_time) > 7200:
                    self.calibrate_market()
                
                if time.time() - self.last_activity_ts > 300:
                    self.last_activity_ts = time.time()
                    self.calibrate_market()

                now_dt = datetime.now(BR_TIMEZONE)
                sec = now_dt.second

                if sec in RESERVE_SECONDS:
                    self.scan_and_reserve()
                
                if sec in NEXT_CANDLE_EXEC_SECONDS:
                    self.execute_reserved()

                time.sleep(0.1)

            except Exception as e:
                self.log_to_db(f"❌ Main loop error: {e}", "ERROR")
                time.sleep(3)

if __name__ == "__main__":
    SimpleBot().start()
