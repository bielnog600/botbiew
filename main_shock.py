import sys
import time
import logging
import json
import threading
import os
import random
import math
import requests
from datetime import datetime, timedelta, timezone
from collections import deque
from supabase import create_client, Client

# --- IMPORTAÇÃO DA EXNOVA ---
try:
    from exnovaapi.stable_api import Exnova
except ImportError:
    print("[ERRO] Biblioteca 'exnovaapi' não instalada.")

BOT_VERSION = "SHOCK_ENGINE_V35_SMART_LOCK_DB_SAFE_2026-01-22"
print(f"🚀 START::{BOT_VERSION}")

# ==============================================================================
# CONFIG GERAL
# ==============================================================================
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://ioduahwknfsktujthfyc.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
EXNOVA_EMAIL = os.environ.get("EXNOVA_EMAIL", "seu_email@exemplo.com")
EXNOVA_PASSWORD = os.environ.get("EXNOVA_PASSWORD", "sua_senha")

BR_TIMEZONE = timezone(timedelta(hours=-3))

# ✅ SEGUNDO DE ENTRADA
ENTRY_SECOND = int(os.environ.get("ENTRY_SECOND", "50"))

# ✅ CONFIGURAÇÃO MARTINGALE
MARTINGALE_ENABLED = os.environ.get("MARTINGALE_ENABLED", "1") == "1"
MARTINGALE_MULTIPLIER = float(os.environ.get("MARTINGALE_MULTIPLIER", "2.0"))

# ==============================================================================
# LOGGING / WATCHDOG
# ==============================================================================
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
for logger_name in ["websocket", "exnovaapi", "iqoptionapi", "urllib3", "iqoptionapi.websocket.client"]:
    logging.getLogger(logger_name).setLevel(logging.CRITICAL)

WATCHDOG_CHECK_EVERY = 60
WATCHDOG_MAX_SILENCE = 300
COOLIFY_RESTART_URL = "https://biewdev.se/api/v1/applications/ig80skg8ssog04g4oo88wswg/restart"
COOLIFY_API_TOKEN = os.environ.get("COOLIFY_API_TOKEN")
LAST_LOG_TIME = time.time()


def watchdog():
    global LAST_LOG_TIME
    print("[WATCHDOG] Monitoramento iniciado.")
    while True:
        time.sleep(WATCHDOG_CHECK_EVERY)
        if time.time() - LAST_LOG_TIME > WATCHDOG_MAX_SILENCE:
            print("[WATCHDOG] ⚠️ Bot travado. Tentando reiniciar...")
            if COOLIFY_API_TOKEN:
                try:
                    requests.post(
                        COOLIFY_RESTART_URL,
                        headers={"Authorization": f"Bearer {COOLIFY_API_TOKEN}"},
                        timeout=10,
                    )
                except:
                    pass
            os._exit(1)


# ==============================================================================
# MOTORES DE ANÁLISE
# ==============================================================================

class TechnicalAnalysis:
    @staticmethod
    def calculate_sma(candles, period):
        if len(candles) < period:
            return 0
        return sum(c["close"] for c in candles[-period:]) / period

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
    def sma_series(values, period):
        if len(values) < period:
            return []
        out = []
        for i in range(period - 1, len(values)):
            out.append(sum(values[i - period + 1 : i + 1]) / period)
        return out

    @staticmethod
    def ema_series(values, period):
        if len(values) < period:
            return []
        out = []
        sma = sum(values[:period]) / period
        out.append(sma)
        k = 2 / (period + 1)
        for v in values[period:]:
            new_ema = v * k + out[-1] * (1 - k)
            out.append(new_ema)
        return out

    @staticmethod
    def analyze_candle(candle):
        open_p = candle["open"]
        close_p = candle["close"]
        high_p = candle["max"]
        low_p = candle["min"]
        body = abs(close_p - open_p)
        upper_wick = high_p - max(open_p, close_p)
        lower_wick = min(open_p, close_p) - low_p
        color = "green" if close_p > open_p else "red" if close_p < open_p else "doji"
        rng = high_p - low_p
        
        # Safe volume check
        vol = candle.get("volume", 0)
        
        return {
            "color": color,
            "body": body,
            "upper_wick": upper_wick,
            "lower_wick": lower_wick,
            "close": close_p,
            "open": open_p,
            "max": high_p,
            "min": low_p,
            "range": rng,
            "volume": vol
        }

    @staticmethod
    def check_compression(candles):
        if len(candles) < 20:
            return False
        ema9 = TechnicalAnalysis.calculate_ema(candles[:-1], 9)
        ema21 = TechnicalAnalysis.calculate_ema(candles[:-1], 21)
        bodies = [abs(c["close"] - c["open"]) for c in candles[-11:-1]]
        avg_body = sum(bodies) / len(bodies) if bodies else 0.00001
        spread = abs(ema9 - ema21)
        return spread < (avg_body * 0.15)

    @staticmethod
    def get_signal_v2(candles):
        if len(candles) < 60:
            return None, "Dados insuficientes"

        current_hour = datetime.now(BR_TIMEZONE).hour
        engulf_required = True
        if current_hour >= 14:
            engulf_required = False

        ema9 = TechnicalAnalysis.calculate_ema(candles[:-1], 9)
        ema21 = TechnicalAnalysis.calculate_ema(candles[:-1], 21)
        ema21_prev = TechnicalAnalysis.calculate_ema(candles[:-2], 21)

        confirm = TechnicalAnalysis.analyze_candle(candles[-2])
        reject = TechnicalAnalysis.analyze_candle(candles[-3])

        avg_body = sum([abs(c["close"] - c["open"]) for c in candles[-8:-3]]) / 5
        min_slope = avg_body * 0.02
        ema21_slope = ema21 - ema21_prev

        if ema9 > ema21 and ema21_slope > min_slope:
            touched_ema = reject["min"] <= (ema21 + (avg_body * 0.1))
            held_support = reject["close"] >= (ema21 - (avg_body * 0.3))
            if touched_ema and held_support:
                if confirm["color"] == "green":
                    last = confirm
                    prev = reject
                    is_engulf = (last["color"] == "green" and prev["color"] == "red" and last["body"] >= prev["body"] * 0.6)
                    
                    if engulf_required and not is_engulf:
                        return None, "Sem engolfo"
                    return "call", "V2 CALL"

        elif ema9 < ema21 and ema21_slope < -min_slope:
            touched_ema = reject["max"] >= (ema21 - (avg_body * 0.1))
            held_resist = reject["close"] <= (ema21 + (avg_body * 0.3))
            if touched_ema and held_resist:
                if confirm["color"] == "red":
                    last = confirm
                    prev = reject
                    is_engulf = (last["color"] == "red" and prev["color"] == "green" and last["body"] >= prev["body"] * 0.6)

                    if engulf_required and not is_engulf:
                        return None, "Sem engolfo"
                    return "put", "V2 PUT"

        return None, "Sem configuração"


class ShockLiveDetector:
    @staticmethod
    def detect(candles, asset_name):
        if len(candles) < 30:
            return None, "Dados insuficientes", {}

        live = TechnicalAnalysis.analyze_candle(candles[-1])
        # ✅ PROTEÇÃO NANO TENDÊNCIA: Analisa 2 velas anteriores
        prev1 = TechnicalAnalysis.analyze_candle(candles[-2])
        prev2 = TechnicalAnalysis.analyze_candle(candles[-3])

        closed = candles[:-1]

        bodies = [abs(c["close"] - c["open"]) for c in closed[-20:]]
        ranges = [(c["max"] - c["min"]) for c in closed[-20:]]

        avg_body = (sum(bodies) / len(bodies)) if bodies else 0.00001
        avg_range = (sum(ranges) / len(ranges)) if ranges else 0.00001

        body_live = live["body"]
        range_live = live["range"]

        if range_live <= 0:
            return None, "Doji", {}

        close_pos = (live["close"] - live["min"]) / range_live 

        if live["color"] == "green":
            pullback = live["max"] - live["close"]
        elif live["color"] == "red":
            pullback = live["close"] - live["min"]
        else:
            pullback = range_live * 0.5

        pullback_ratio = pullback / range_live if range_live > 0 else 1.0

        body_mult = 1.4
        range_mult = 1.4

        min_body_abs = 0.015 if "JPY" in asset_name else 0.00015
        if body_live < min_body_abs:
            return None, "Mercado morto (live)", {}

        debug = {
            "avg_body": avg_body,
            "avg_range": avg_range,
            "body_live": body_live,
            "range_live": range_live,
            "close_pos": close_pos,
            "pullback_ratio": pullback_ratio,
            "color": live["color"],
        }

        # ✅ SUPER EXPLOSÃO: Permite contra-tendência se for exaustão absurda (> 2.2x)
        super_explosive = (body_live >= avg_body * 2.2) and (range_live >= avg_range * 2.2)
        
        explosive = (body_live >= avg_body * body_mult) and (range_live >= avg_range * range_mult)
        if not explosive:
            return None, "Sem explosão", debug

        if live["color"] == "green":
            # ✅ FILTRO INTELIGENTE: Se 3 verdes e NÃO for super explosão, aborta.
            if prev1["color"] == "green" and prev2["color"] == "green" and not super_explosive:
                return None, "Abortar: Nano Tendência de Alta (3 Green)", debug

            if close_pos >= 0.85 and pullback_ratio <= 0.25:
                return "put", "SHOCK_LIVE_UP", debug
            return None, "Explodiu mas não travou no topo", debug

        if live["color"] == "red":
            # ✅ FILTRO INTELIGENTE: Se 3 vermelhas e NÃO for super explosão, aborta.
            if prev1["color"] == "red" and prev2["color"] == "red" and not super_explosive:
                return None, "Abortar: Nano Tendência de Baixa (3 Red)", debug

            if close_pos <= 0.15 and pullback_ratio <= 0.25:
                return "call", "SHOCK_LIVE_DOWN", debug
            return None, "Explodiu mas não travou no fundo", debug

        return None, "Sem padrão", debug


class TendMaxStrategy:
    @staticmethod
    def get_signal(candles):
        if len(candles) < 50:
            return None, "Dados insuficientes"

        closes = [c["close"] for c in candles]
        
        sma_fast = TechnicalAnalysis.sma_series(closes, 1)
        sma_slow = TechnicalAnalysis.sma_series(closes, 34)

        min_len = min(len(sma_fast), len(sma_slow))
        sma_fast = sma_fast[-min_len:]
        sma_slow = sma_slow[-min_len:]

        buffer1 = [f - s for f, s in zip(sma_fast, sma_slow)]
        buffer2 = TechnicalAnalysis.ema_series(buffer1, 6)

        if len(buffer2) < 3:
            return None, "Série insuficiente"
        
        b1_now, b1_prev = buffer1[-2], buffer1[-3]
        b2_now, b2_prev = buffer2[-2], buffer2[-3]

        if b1_now > b2_now and b1_prev < b2_prev:
            return "call", "TENDMAX_CALL"

        if b1_now < b2_now and b1_prev > b2_prev:
            return "put", "TENDMAX_PUT"

        return None, "Sem cruzamento"


class TsunamiFlowStrategy:
    """
    🌊 TSUNAMI FLOW: Estratégia de seguimento de tendência e momentum.
    """
    @staticmethod
    def get_signal(candles):
        if len(candles) < 55:
            return None, "Dados insuficientes"

        c1 = TechnicalAnalysis.analyze_candle(candles[-2])
        c2 = TechnicalAnalysis.analyze_candle(candles[-3])
        c3 = TechnicalAnalysis.analyze_candle(candles[-4])

        ema50 = TechnicalAnalysis.calculate_ema(candles[:-1], 50)

        if c1["color"] == "green" and c2["color"] == "green" and c3["color"] == "green":
            if c1["body"] > c2["body"]:
                if c1["close"] > ema50:
                    rejection = c1["upper_wick"] / c1["range"] if c1["range"] > 0 else 0
                    if rejection > 0.35: return None, "Rejeição alta no topo"
                    avg_body = (c2["body"] + c3["body"]) / 2
                    if c1["body"] < avg_body * 3.0: return "call", "TSUNAMI_FLOW_UP"

        if c1["color"] == "red" and c2["color"] == "red" and c3["color"] == "red":
            if c1["body"] > c2["body"]:
                if c1["close"] < ema50:
                    rejection = c1["lower_wick"] / c1["range"] if c1["range"] > 0 else 0
                    if rejection > 0.35: return None, "Rejeição alta no fundo"
                    avg_body = (c2["body"] + c3["body"]) / 2
                    if c1["body"] < avg_body * 3.0: return "put", "TSUNAMI_FLOW_DOWN"

        return None, "Sem fluxo"


class VolumeReactorStrategy:
    """
    ☢️ VOLUME REACTOR (HÍBRIDO): Estratégia de Exaustão.
    """
    @staticmethod
    def get_signal(candles):
        if len(candles) < 30:
            return None, "Dados insuficientes"
            
        c1 = TechnicalAnalysis.analyze_candle(candles[-2])
        volumes = [c.get("volume", 0) for c in candles[-22:-2]]
        has_real_volume = sum(volumes) > 10
        avg_vol = sum(volumes) / len(volumes) if has_real_volume else 0
        
        is_exhaustion = False
        label = ""

        if has_real_volume:
            if c1["volume"] > (avg_vol * 2.0):
                is_exhaustion = True; label = "VOL_CLIMAX"
        else:
            ranges = [(c["max"] - c["min"]) for c in candles[-22:-2]]
            avg_range = sum(ranges) / len(ranges) if ranges else 0.00001
            if c1["range"] > (avg_range * 2.5):
                is_exhaustion = True; label = "RANGE_CLIMAX"

        if not is_exhaustion: return None, "Sem exaustão"

        if c1["color"] == "green":
            rejection_ratio = c1["upper_wick"] / c1["range"] if c1["range"] > 0 else 0
            if rejection_ratio > 0.25: return "put", f"REACTOR_{label}_TOP"

        if c1["color"] == "red":
            rejection_ratio = c1["lower_wick"] / c1["range"] if c1["range"] > 0 else 0
            if rejection_ratio > 0.25: return "call", f"REACTOR_{label}_BOTTOM"
                
        return None, "Sem padrão reactor"


# ==============================================================================
# BOT
# ==============================================================================

class SimpleBot:
    def __init__(self):
        self.api = None
        self.supabase = None

        self.trade_lock = threading.RLock()
        self.api_lock = threading.RLock()
        self.db_lock = threading.RLock() # ✅ LOCK PARA DB (Thread Safety)
        self.active_trades = set()

        self.config = {
            "status": "PAUSED",
            "account_type": "PRACTICE",
            "entry_value": 1.0,
            "max_trades_per_day": 0,
            "max_wins_per_day": 0,
            "max_losses_per_day": 0,
            "timer_enabled": False,
            "timer_start": "00:00",
            "timer_end": "00:00",
            "mode": "LIVE",
            "strategy_mode": "AUTO",
            "martingale_enabled": MARTINGALE_ENABLED,
            "martingale_multiplier": MARTINGALE_MULTIPLIER,
        }

        self.current_date = datetime.now(BR_TIMEZONE).date()
        self.daily_wins = 0
        self.daily_losses = 0
        self.daily_total = 0

        self.best_assets = []
        self.last_catalog_time = 0
        self.last_calibration_time = 0
        self.asset_strategy_map = {} 
        self.calibration_running = False 
        
        self.asset_cooldown = {}
        self.last_heartbeat_ts = 0 
        self.last_config_ts = 0 
        self.last_global_minute = None 

        self.last_trade_time = {}
        self.last_minute_trade = {}
        self.session_blocked = False

        self.block_until_ts = 0
        self.loss_streak = 0
        
        self.pending_gale = {}

        self.auto_candidate = None
        self.auto_candidate_key = None

        self.strategy_memory = {
            "SHOCK_REVERSAL": deque(maxlen=20),
            "V2_TREND": deque(maxlen=20),
            "TENDMAX": deque(maxlen=20),
            "TSUNAMI_FLOW": deque(maxlen=20),
            "VOLUME_REACTOR": deque(maxlen=20),
        }

        self.init_supabase()

    def init_supabase(self):
        try:
            if not SUPABASE_KEY:
                print("⚠️ SUPABASE_KEY não encontrada nas variáveis de ambiente!")
            self.supabase = create_client(SUPABASE_URL, SUPABASE_KEY or "invalid_key")
            print("✅ Supabase conectado.")
        except Exception as e:
            print(f"❌ Erro Supabase: {e}")

    def touch_watchdog(self):
        global LAST_LOG_TIME
        LAST_LOG_TIME = time.time()

    def log_to_db(self, message, level="INFO"):
        global LAST_LOG_TIME
        LAST_LOG_TIME = time.time()
        print(f"[{level}] {message}")
        if level == "DEBUG": return
        if not self.supabase: return
        try:
            # ✅ DB LOCK
            with self.db_lock:
                self.supabase.table("logs").insert(
                    {"message": message, "level": level, "created_at": datetime.now(timezone.utc).isoformat()}
                ).execute()
        except: pass

    def check_strategy_signal(self, strategy_name, candles):
        if strategy_name == "TENDMAX": return TendMaxStrategy.get_signal(candles)
        elif strategy_name == "V2_TREND":
            if not TechnicalAnalysis.check_compression(candles): return TechnicalAnalysis.get_signal_v2(candles)
        elif strategy_name == "TSUNAMI_FLOW": return TsunamiFlowStrategy.get_signal(candles)
        elif strategy_name == "VOLUME_REACTOR": return VolumeReactorStrategy.get_signal(candles)
        return None, None

    def calibrate_market(self):
        if self.calibration_running: return
        self.calibration_running = True
        self.log_to_db("🔬 Disparando Thread de Calibração...", "SYSTEM")
        t = threading.Thread(target=self._run_calibration_task, daemon=True)
        t.start()

    def _run_calibration_task(self):
        try:
            if not self.api or not self.api.check_connect():
                self.log_to_db("⚠️ Calibração abortada: API offline", "WARNING"); return

            try:
                strategies = ["V2_TREND", "TENDMAX", "TSUNAMI_FLOW", "VOLUME_REACTOR"]
                if not self.best_assets:
                     assets_pool = [
                        "EURUSD-OTC", "EURGBP-OTC", "USDCHF-OTC", "EURJPY-OTC",
                        "NZDUSD-OTC", "GBPUSD-OTC", "GBPJPY-OTC", "USDJPY-OTC",
                        "AUDCAD-OTC", "AUDUSD-OTC", "USDCAD-OTC", "AUDJPY-OTC"
                    ]
                     self.best_assets = self.catalog_assets(assets_pool)

                assets = self.best_assets
                new_map = {}
                
                for asset in assets:
                    try:
                        candles = None
                        with self.api_lock:
                            try: candles = self.api.get_candles(asset, 60, 120, int(time.time()))
                            except: candles = None
                        if not candles or len(candles) < 100: continue
                        
                        scores = {s: {'wins': 0, 'total': 0} for s in strategies}
                        for i in range(60, len(candles)-1, 2):
                            window = candles[i-60 : i+1]; result_candle = candles[i+1]
                            for s in strategies:
                                sig, _ = self.check_strategy_signal(s, window)
                                if sig:
                                    scores[s]['total'] += 1
                                    is_win = (sig == "call" and result_candle["close"] > result_candle["open"]) or (sig == "put" and result_candle["close"] < result_candle["open"])
                                    if is_win: scores[s]['wins'] += 1
                        
                        best_s = None; best_score = -1
                        for s, stats in scores.items():
                            total = stats['total']
                            if total > 0:
                                wr = stats['wins'] / total
                                score = wr * math.sqrt(total)
                                if total >= 8 and wr >= 0.52 and score > best_score:
                                    best_score = score; best_s = s
                        
                        if best_s:
                            new_map[asset] = {"strategy": best_s, "score": best_score}
                            self.log_to_db(f"✅ {asset} -> {best_s} (Score: {best_score:.2f} | WR: {scores[best_s]['wins']/scores[best_s]['total']:.2f})", "DEBUG")
                        else: new_map[asset] = {"strategy": "V2_TREND", "score": 1.0}
                    except: pass
                
                self.asset_strategy_map = new_map
                self.last_calibration_time = time.time()
                self.log_to_db(f"🏁 Calibração concluída. {len(new_map)} pares mapeados.", "SUCCESS")
            except Exception as e: self.log_to_db(f"❌ Erro na Lógica de Calibração: {e}", "ERROR")
        finally: self.calibration_running = False

    def insert_signal(self, asset, direction, strategy_name, amount):
        if not self.supabase: return None
        payload = {
            "pair": asset, "direction": direction, "strategy": strategy_name, "status": "PENDING",
            "result": "PENDING", "profit": 0, "created_at": datetime.now(timezone.utc).isoformat(), "amount": amount
        }
        try:
            with self.db_lock: # ✅ DB LOCK
                res = self.supabase.table("trade_signals").insert(payload).execute()
                if res.data: return res.data[0].get("id")
        except:
            try:
                del payload["amount"]
                with self.db_lock:
                    res = self.supabase.table("trade_signals").insert(payload).execute()
                    if res.data: return res.data[0].get("id")
            except: pass
        return None

    def update_signal(self, signal_id, status, result, profit):
        if not self.supabase or not signal_id: return
        try:
            with self.db_lock: # ✅ DB LOCK
                self.supabase.table("trade_signals").update({"status": status, "result": result, "profit": profit}).eq("id", signal_id).execute()
        except: pass

    def connect(self):
        self.log_to_db("🔌 Conectando...", "SYSTEM")
        ok = False; reason = "UNKNOWN"
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
            if ok:
                self.update_balance_remote()
                return True
            else: self.log_to_db(f"❌ Falha conexão: {reason}", "ERROR")
        except Exception as e: self.log_to_db(f"❌ Erro crítico conexão: {e}", "ERROR")
        return False

    def update_balance_remote(self):
        if not self.api or not self.supabase: return
        try:
            with self.api_lock: balance = self.api.get_balance()
            with self.db_lock: # ✅ DB LOCK
                self.supabase.table("bot_config").update({"current_balance": balance}).eq("id", 1).execute()
        except: pass

    def fetch_config(self):
        if not self.supabase: self.init_supabase(); return
        try:
            with self.db_lock: # ✅ DB LOCK
                res = self.supabase.table("bot_config").select("*").eq("id", 1).execute()
            if not res.data:
                with self.db_lock:
                    self.supabase.table("bot_config").insert({"id": 1, "status": "PAUSED"}).execute()
                return
            data = res.data[0]
            new_status = (data.get("status") or "PAUSED").strip().upper()
            new_mode = (data.get("mode") or "LIVE").strip().upper()
            db_raw_strat = data.get("strategy_mode")
            db_strat = (str(db_raw_strat) or "AUTO").strip().upper().replace(" ", "_")
            if "SHOCK" in db_strat: strat = "SHOCK_REVERSAL"
            elif "TENDMAX" in db_strat: strat = "TENDMAX"
            elif "V2" in db_strat: strat = "V2_TREND"
            elif "TSUNAMI" in db_strat: strat = "TSUNAMI_FLOW"
            elif "REACTOR" in db_strat or "VOLUME" in db_strat: strat = "VOLUME_REACTOR"
            elif "AUTO" in db_strat: strat = "AUTO"
            else: strat = "AUTO"
            self.config.update({
                "status": new_status, "mode": new_mode, "strategy_mode": strat,
                "account_type": (data.get("account_type") or "PRACTICE").strip().upper(),
                "entry_value": float(data.get("entry_value") or 1.0),
                "max_trades_per_day": int(data.get("max_trades_per_day") or 0),
                "max_wins_per_day": int(data.get("max_wins_per_day") or 0),
                "max_losses_per_day": int(data.get("max_losses_per_day") or 0),
                "timer_enabled": bool(data.get("timer_enabled")),
                "timer_start": str(data.get("timer_start") or "00:00"),
                "timer_end": str(data.get("timer_end") or "00:00"),
            })
        except: pass

    def check_schedule(self):
        now_br = datetime.now(BR_TIMEZONE)
        now_str = now_br.strftime("%H:%M")
        start_str = self.config.get("timer_start", "00:00")
        end_str = self.config.get("timer_end", "00:00")
        hour = now_br.hour; minute = now_br.minute
        blocked_time = False
        if 0 <= hour < 4: blocked_time = True
        if hour == 13 and minute >= 30: blocked_time = True
        if hour == 14 and minute <= 30: blocked_time = True
        if blocked_time:
            if self.config["status"] == "RUNNING":
                self.log_to_db("⛔ Horário bloqueado — PAUSANDO", "WARNING")
                try: 
                    with self.db_lock:
                        self.supabase.table("bot_config").update({"status": "PAUSED"}).eq("id", 1).execute()
                    self.config["status"] = "PAUSED"
                except: pass
            return
        if not self.config.get("timer_enabled", False): return
        is_inside = False
        if start_str < end_str: is_inside = start_str <= now_str < end_str
        else: is_inside = now_str >= start_str or now_str < end_str
        if is_inside and self.config["status"] == "PAUSED":
            self.log_to_db(f"⏰ Agendador: RUNNING ({start_str}-{end_str})", "SYSTEM")
            try: 
                with self.db_lock: self.supabase.table("bot_config").update({"status": "RUNNING"}).eq("id", 1).execute()
            except: pass
        if (not is_inside) and self.config["status"] == "RUNNING":
            self.log_to_db("⏰ Agendador: PAUSED (fim)", "SYSTEM")
            try: 
                with self.db_lock: self.supabase.table("bot_config").update({"status": "PAUSED"}).eq("id", 1).execute()
            except: pass

    def reset_daily_if_needed(self):
        today = datetime.now(BR_TIMEZONE).date()
        if today != self.current_date:
            self.current_date = today
            self.daily_wins = 0; self.daily_losses = 0; self.daily_total = 0; self.loss_streak = 0
            self.session_blocked = False; self.block_until_ts = 0; self.pending_gale = {}
            self.auto_candidate = None; self.auto_candidate_key = None
            self.asset_cooldown = {} 
            self.log_to_db("🚀 Nova sessão diária", "SYSTEM")

    def check_daily_limits(self):
        if self.config["mode"] == "OBSERVE": return True
        if self.config["max_trades_per_day"] > 0 and self.daily_total >= self.config["max_trades_per_day"]:
            self.log_to_db(f"🛑 Limite trades ({self.daily_total})", "WARNING"); return False
        if self.config["max_wins_per_day"] > 0 and self.daily_wins >= self.config["max_wins_per_day"]:
            self.log_to_db(f"🏆 Meta wins ({self.daily_wins})", "SUCCESS"); return False
        if self.config["max_losses_per_day"] > 0 and self.daily_losses >= self.config["max_losses_per_day"]:
            self.log_to_db(f"❌ Limite losses ({self.daily_losses})", "ERROR"); return False
        return True

    def safe_buy(self, asset, amount, direction, prefer_binary=True):
        if self.config["mode"] == "OBSERVE": return True, "VIRTUAL"
        try:
            with self.api_lock:
                status, trade_id = self.api.buy(amount, asset, direction, 1)
            if status and trade_id: return True, trade_id
            self.log_to_db(f"⚠️ Binária falhou (ID nulo).", "WARNING")
            return False, None
        except Exception as e:
            self.log_to_db(f"⚠️ Erro Safe Buy: {e}", "ERROR"); return False, None

    def get_strategy_wr(self, strategy_key):
        mem = self.strategy_memory.get(strategy_key, [])
        if not mem: return 0.55
        return sum(mem) / len(mem)

    def pick_best_candidate(self, candidates):
        if not candidates: return None
        for c in candidates: c["priority"] = (c["wr"] * 0.7) + (c["confidence"] * 0.3)
        candidates.sort(key=lambda x: x["priority"], reverse=True)
        return candidates[0]

    def score_candidate(self, c): return (c["wr"] * 0.7) + (c["confidence"] * 0.3)
    def choose_best(self, candidates):
        if not candidates: return None
        for c in candidates: c["score"] = self.score_candidate(c)
        candidates.sort(key=lambda x: x["score"], reverse=True)
        return candidates[0]

    def launch_trade(self, **kwargs):
        t = threading.Thread(target=self.execute_trade, kwargs=kwargs, daemon=True)
        t.start()

    def execute_trade(self, asset, direction, strategy_key, strategy_label, prefer_binary=False, gale_level=0):
        if gale_level == 0 and time.time() < self.asset_cooldown.get(asset, 0): return

        entry_dt = datetime.now(BR_TIMEZONE)
        now = time.time()
        
        # ✅ SMART GLOBAL LOCK: Reserva sem travar, só trava se confirmar ordem
        global_minute = entry_dt.strftime("%Y%m%d%H%M")
        reserved_minute = False
        
        if gale_level == 0:
            with self.trade_lock:
                # ✅ MAX ACTIVE TRADES CHECK (G0)
                if len(self.active_trades) >= 1: return
                
                if self.last_global_minute == global_minute: return
                reserved_minute = True

        if gale_level == 0:
            if asset in self.last_trade_time and now - self.last_trade_time[asset] < 60: return
            self.last_trade_time[asset] = now
            minute_key = entry_dt.strftime("%Y%m%d%H%M")
            if self.last_minute_trade.get(asset) == minute_key: return
            self.last_minute_trade[asset] = minute_key

        if time.time() < self.block_until_ts: return
        with self.trade_lock:
            if gale_level == 0 and asset in self.active_trades: return
            self.active_trades.add(asset)

        signal_id = None
        base_amount = float(self.config["entry_value"])
        amount = base_amount
        if gale_level > 0:
            multiplier = self.config.get("martingale_multiplier", 2.0)
            amount = round(base_amount * (multiplier ** gale_level), 2)

        try:
            if not self.check_daily_limits():
                self.session_blocked = True
                self.log_to_db("⛔ Limite diário atingido. Pausando.", "WARNING")
                try: 
                    with self.db_lock: self.supabase.table("bot_config").update({"status": "PAUSED"}).eq("id", 1).execute()
                except: pass
                return

            tag_gale = f"::G{gale_level}"
            strategy_name = f"{strategy_key}::{strategy_label}{tag_gale}"
            signal_id = self.insert_signal(asset, direction, strategy_name, amount)

            route = "BINARIA"
            self.log_to_db(f"🟡 TENTANDO ENTRAR [{route}] {strategy_key} [G{gale_level}]: {asset} | {direction.upper()} | ${amount}", "INFO")

            balance_before = 0.0
            if self.config["mode"] == "LIVE":
                try:
                    with self.api_lock: balance_before = self.api.get_balance()
                    if balance_before <= 0: self.log_to_db("❌ Saldo inválido", "ERROR"); return
                except: return

            status, trade_id = self.safe_buy(asset, amount, direction, prefer_binary=prefer_binary)
            if not status or not trade_id:
                self.log_to_db(f"❌ ORDEM RECUSADA: {asset}", "ERROR")
                self.update_signal(signal_id, "FAILED", "FAILED", 0)
                return
            
            # ✅ CONFIRM GLOBAL LOCK (Só trava se ordem entrou)
            if gale_level == 0 and reserved_minute:
                with self.trade_lock: self.last_global_minute = global_minute

            self.log_to_db(f"✅ CONFIRMADA: Ordem {trade_id}. Aguardando...", "INFO")
            time.sleep(70)

            res_str = "UNKNOWN"; profit = 0.0
            if self.config["mode"] == "OBSERVE":
                try:
                    with self.api_lock: candles = self.api.get_candles(asset, 60, 2, int(time.time()))
                    last_closed = candles[-2]
                    is_win = (direction == "call" and last_closed["close"] > last_closed["open"]) or (direction == "put" and last_closed["close"] < last_closed["open"])
                    if is_win: res_str = "WIN"; profit = amount * 0.87
                    else:
                        if abs(last_closed["close"] - last_closed["open"]) < 1e-9: res_str = "DOJI"; profit = 0.0
                        else: res_str = "LOSS"; profit = -amount
                except: res_str = "UNKNOWN"
            else:
                try:
                    with self.api_lock: balance_after = self.api.get_balance()
                    delta = balance_after - balance_before
                    if delta > 0.01: res_str = "WIN"; profit = delta
                    elif delta < -0.01: res_str = "LOSS"; profit = delta
                    else: res_str = "DOJI"; profit = 0.0
                except: res_str = "UNKNOWN"

            if res_str == "DOJI":
                self.log_to_db("⚪ DOJI (ignorado)", "DEBUG")
                self.update_signal(signal_id, "DOJI", "DOJI", 0); return
            
            if res_str in ["WIN", "LOSS"] and strategy_key in self.strategy_memory:
                 self.strategy_memory[strategy_key].append(1 if res_str == "WIN" else 0)

            self.daily_total += 1
            if res_str == "WIN":
                self.daily_wins += 1; self.loss_streak = 0
                if asset in self.pending_gale: del self.pending_gale[asset]
            elif res_str == "LOSS":
                self.daily_losses += 1; self.loss_streak += 1
                self.asset_cooldown[asset] = time.time() + 180
                if gale_level == 0 and self.config.get("martingale_enabled", True):
                    next_minute = (entry_dt + timedelta(minutes=1)).strftime("%Y%m%d%H%M")
                    entry_sec = ENTRY_SECOND
                    self.log_to_db(f"🎯 GALE G1 ARMADO para {asset} (Min: {next_minute} Sec: {entry_sec})", "WARNING")
                    self.pending_gale[asset] = {
                        'asset': asset, 'direction': direction, 'strategy_key': strategy_key,
                        'strategy_label': strategy_label, 'prefer_binary': True,
                        'minute_key': next_minute, 'second_key': entry_sec
                    }

            if self.loss_streak >= 2:
                self.block_until_ts = time.time() + 900
                self.log_to_db("🛑 2 LOSSES SEGUIDOS — PAUSANDO 15 MIN (ANTI-CHOP)", "WARNING")
                self.pending_gale = {}; self.auto_candidate = None; self.auto_candidate_key = None

            self.update_signal(signal_id, res_str, res_str, profit)
            log_type = "SUCCESS" if res_str == "WIN" else "ERROR"
            self.log_to_db(f"{'🏆' if res_str == 'WIN' else '🔻'} {res_str} [G{gale_level}]: {profit:.2f} ({self.daily_wins}W/{self.daily_losses}L)", log_type)
            if self.config["mode"] == "LIVE": self.update_balance_remote()
            if not self.check_daily_limits():
                self.log_to_db("🛑 Limite diário atingido — PAUSANDO", "WARNING")
                self.session_blocked = True
                try: 
                    with self.db_lock: self.supabase.table("bot_config").update({"status": "PAUSED"}).eq("id", 1).execute()
                except: pass
        finally:
            with self.trade_lock: self.active_trades.discard(asset)

    def catalog_assets(self, assets_pool):
        strat = self.config.get("strategy_mode", "AUTO")
        if strat in ["SHOCK_REVERSAL", "TENDMAX", "AUTO", "TSUNAMI_FLOW", "VOLUME_REACTOR"]:
            self.log_to_db("🔥 Modo FULL ASSETS: usando TODOS os ativos", "SYSTEM")
            return assets_pool
        return assets_pool

    def start(self):
        t_watchdog = threading.Thread(target=watchdog, daemon=True)
        t_watchdog.start()
        assets_pool = [
            "EURUSD-OTC", "EURGBP-OTC", "USDCHF-OTC", "EURJPY-OTC",
            "NZDUSD-OTC", "GBPUSD-OTC", "GBPJPY-OTC", "USDJPY-OTC",
            "AUDCAD-OTC", "AUDUSD-OTC", "USDCAD-OTC", "AUDJPY-OTC"
        ]

        while True:
            try:
                if time.time() - self.last_heartbeat_ts >= 30:
                    self.last_heartbeat_ts = time.time(); self.touch_watchdog()

                self.reset_daily_if_needed()
                
                if time.time() - self.last_config_ts >= 5:
                    self.fetch_config(); self.last_config_ts = time.time()

                self.check_schedule()
                if self.config["status"] == "PAUSED": time.sleep(2); continue
                if time.time() < self.block_until_ts: time.sleep(2); continue

                if not self.api or not self.api.check_connect():
                    if not self.connect(): time.sleep(5); continue
                
                if (time.time() - self.last_calibration_time) > 7200: self.calibrate_market()

                executed_gale = False
                if self.pending_gale:
                    now_dt = datetime.now(BR_TIMEZONE)
                    current_key = now_dt.strftime("%Y%m%d%H%M")
                    now_sec = now_dt.second
                    assets_gale = list(self.pending_gale.keys())
                    for asset in assets_gale:
                        g = self.pending_gale.get(asset)
                        if not g: continue
                        if g.get("minute_key") != current_key: continue
                        sec_target = int(g.get("second_key", ENTRY_SECOND))
                        if not (sec_target - 3 <= now_sec <= sec_target + 3): continue
                        del self.pending_gale[asset]
                        self.log_to_db(f"🚀 EXECUTANDO GALE G1: {asset} (SYNC {current_key} @{sec_target}s)", "INFO")
                        self.launch_trade(
                            asset=g['asset'], direction=g['direction'], strategy_key=g['strategy_key'],
                            strategy_label=g['strategy_label'], prefer_binary=g['prefer_binary'], gale_level=1
                        )
                        executed_gale = True
                    if executed_gale: time.sleep(0.25); continue

                if not self.best_assets or (time.time() - self.last_catalog_time > 900):
                    self.best_assets = self.catalog_assets(assets_pool)
                    self.last_catalog_time = time.time()

                now_dt = datetime.now(BR_TIMEZONE)
                now_sec = now_dt.second
                strat_mode = self.config.get("strategy_mode", "AUTO")

                if now_sec in [0, 10, 20, 30, 40, 50]:
                    self.log_to_db(f"MODE_ATIVO::{strat_mode}::{now_dt.strftime('%H:%M:%S')}::ENTRY={ENTRY_SECOND}s", "DEBUG")

                current_minute_key = now_dt.strftime("%Y%m%d%H%M")
                if self.auto_candidate_key != current_minute_key:
                    self.auto_candidate = None; self.auto_candidate_key = current_minute_key

                # FASE 1: SHOCK LIVE
                if ENTRY_SECOND <= now_sec <= ENTRY_SECOND + 2:
                    if strat_mode in ["AUTO", "SHOCK_REVERSAL"]:
                        random_assets = self.best_assets.copy()
                        random.shuffle(random_assets)
                        for asset in random_assets:
                            with self.trade_lock:
                                if asset in self.active_trades: continue
                            try:
                                with self.api_lock: candles = self.api.get_candles(asset, 60, 60, int(time.time()))
                                if not candles: continue
                                sig, reason, dbg = ShockLiveDetector.detect(candles, asset)
                                if strat_mode == "SHOCK_REVERSAL": self.log_to_db(f"⚡ SHOCK_CHECK {asset}: {reason}", "DEBUG")
                                if sig:
                                    if strat_mode == "AUTO":
                                        cand = {
                                            "asset": asset, "direction": sig, "strategy": "SHOCK_REVERSAL",
                                            "label": reason, "confidence": 0.82, 
                                            "wr": self.get_strategy_wr("SHOCK_REVERSAL"), "prefer_binary": True 
                                        }
                                        cand["score"] = self.score_candidate(cand)
                                        if not self.auto_candidate or cand["score"] > self.score_candidate(self.auto_candidate):
                                             self.auto_candidate = cand; self.auto_candidate_key = current_minute_key
                                        self.log_to_db(f"🤖 AUTO_CANDIDATE(SHOCK) {asset} Score={cand['score']:.2f}", "SYSTEM")
                                        
                                        if ENTRY_SECOND >= 53:
                                            self.log_to_db(f"⚡ AUTO_EXEC (Late Entry) {asset}", "SYSTEM")
                                            self.launch_trade(
                                                asset=cand["asset"], direction=cand["direction"], strategy_key=cand["strategy"],
                                                strategy_label=cand["label"], prefer_binary=cand["prefer_binary"], gale_level=0
                                            )
                                            self.auto_candidate = None; break 

                                    elif strat_mode == "SHOCK_REVERSAL":
                                         self.launch_trade(asset=asset, direction=sig, strategy_key="SHOCK_REVERSAL", strategy_label=reason, prefer_binary=True, gale_level=0)
                                         break
                            except: pass

                # FASE 2: ESTRATÉGIAS DE FECHAMENTO (55-59s)
                if 55 <= now_sec <= 59 and ENTRY_SECOND < 53:
                    if strat_mode in ["TENDMAX", "V2_TREND", "TSUNAMI_FLOW", "VOLUME_REACTOR"]:
                        trade_executed = False
                        random_assets = self.best_assets.copy()
                        random.shuffle(random_assets)
                        for asset in random_assets:
                            with self.trade_lock:
                                if asset in self.active_trades: continue
                            try:
                                with self.api_lock: candles = self.api.get_candles(asset, 60, 60, int(time.time()))
                                if not candles: continue
                                sig, reason = self.check_strategy_signal(strat_mode, candles)
                                if sig:
                                    self.launch_trade(asset=asset, direction=sig, strategy_key=strat_mode, strategy_label=reason, prefer_binary=True, gale_level=0)
                                    trade_executed = True; break
                            except: pass
                        if trade_executed: time.sleep(1); continue

                    if strat_mode == "AUTO":
                        candidates = []
                        if self.auto_candidate and self.auto_candidate_key == current_minute_key:
                             candidates.append(self.auto_candidate)

                        assets_to_scan = list(self.asset_strategy_map.keys()) if self.asset_strategy_map else self.best_assets
                        random.shuffle(assets_to_scan)

                        for asset in assets_to_scan:
                            with self.trade_lock:
                                if asset in self.active_trades: continue
                            try:
                                target_info = self.asset_strategy_map.get(asset, {"strategy": "V2_TREND", "score": 1.0})
                                target_strat = target_info["strategy"]
                                with self.api_lock: candles = self.api.get_candles(asset, 60, 60, int(time.time()))
                                if not candles: continue
                                sig, lbl = self.check_strategy_signal(target_strat, candles)
                                if sig:
                                     boost = min(0.15, target_info["score"] / 10.0)
                                     confidence = 0.70 + boost
                                     candidates.append({
                                        "asset": asset, "direction": sig, "strategy": target_strat,
                                        "label": lbl, "confidence": confidence,
                                        "wr": self.get_strategy_wr(target_strat), "prefer_binary": True 
                                    })
                            except: pass
                        
                        if candidates:
                             best = self.pick_best_candidate(candidates)
                             if best:
                                  self.log_to_db(f"🤖 AUTO_DECISION {best['strategy']}::{best['label']} {best['asset']} {best['direction'].upper()}", "SYSTEM")
                                  self.launch_trade(
                                      asset=best["asset"], direction=best["direction"], strategy_key=best["strategy"],
                                      strategy_label=best["label"], prefer_binary=best["prefer_binary"], gale_level=0
                                  )
                                  self.auto_candidate = None; time.sleep(2)

                time.sleep(0.25)
            except Exception as e:
                self.log_to_db(f"Erro loop principal: {e}", "ERROR"); time.sleep(3)

if __name__ == "__main__":
    SimpleBot().start()
