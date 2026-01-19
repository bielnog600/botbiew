import sys
import time
import logging
import json
import threading
import os
import random
import requests
from datetime import datetime, timedelta, timezone
from supabase import create_client, Client

# --- IMPORTAÇÃO DA EXNOVA ---
try:
    from exnovaapi.stable_api import Exnova
except ImportError:
    print("[ERRO] Biblioteca 'exnovaapi' não instalada.")

# --- CONFIGURAÇÃO GERAL ---
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://ioduahwknfsktujthfyc.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImlvZHVhaHdrbmZza3R1anRoZnljIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTEzMDc0NDcsImV4cCI6MjA2Njg4MzQ0N30.96f8wZO6SvABKFMWjIiw1pSugAB4Isldj7yxLcLJRSE")
EXNOVA_EMAIL = os.environ.get("EXNOVA_EMAIL", "seu_email@exemplo.com")
EXNOVA_PASSWORD = os.environ.get("EXNOVA_PASSWORD", "sua_senha")
BR_TIMEZONE = timezone(timedelta(hours=-3))

# --- SUPRESSÃO DE LOGS ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
for logger_name in ["websocket", "exnovaapi", "iqoptionapi", "urllib3", "iqoptionapi.websocket.client"]:
    logging.getLogger(logger_name).setLevel(logging.CRITICAL)

# --- WATCHDOG ---
WATCHDOG_CHECK_EVERY = 60
WATCHDOG_MAX_SILENCE = 180
COOLIFY_RESTART_URL = "https://biewdev.se/api/v1/applications/ig80skg8ssog04g4oo88wswg/restart"
COOLIFY_API_TOKEN = os.environ.get("COOLIFY_API_TOKEN")
LAST_LOG_TIME = time.time()

def watchdog():
    global LAST_LOG_TIME
    print("[WATCHDOG] Monitoramento iniciado.")
    while True:
        time.sleep(WATCHDOG_CHECK_EVERY)
        if time.time() - LAST_LOG_TIME > WATCHDOG_MAX_SILENCE:
            print(f"[WATCHDOG] ⚠️ Bot travado. Tentando reiniciar...")
            if COOLIFY_API_TOKEN:
                try: requests.post(COOLIFY_RESTART_URL, headers={"Authorization": f"Bearer {COOLIFY_API_TOKEN}"}, timeout=10)
                except: pass
            os._exit(1)

# ==============================================================================
#                               MOTORES DE ANÁLISE
# ==============================================================================

class TechnicalAnalysis:
    @staticmethod
    def calculate_sma(candles, period):
        if len(candles) < period: return 0
        return sum(c['close'] for c in candles[-period:]) / period

    @staticmethod
    def calculate_ema(candles, period):
        if len(candles) < period: return 0
        prices = [c['close'] for c in candles]
        ema = sum(prices[:period]) / period
        k = 2 / (period + 1)
        for price in prices[period:]:
            ema = (price * k) + (ema * (1 - k))
        return ema

    @staticmethod
    def calculate_ema_series(values, period):
        if len(values) < period: return []
        ema_values = []
        sma = sum(values[:period]) / period
        ema_values.append(sma)
        k = 2 / (period + 1)
        for price in values[period:]:
            ema = price * k + ema_values[-1] * (1 - k)
            ema_values.append(ema)
        return ema_values

    @staticmethod
    def analyze_candle(candle):
        open_p = candle['open']
        close_p = candle['close']
        high_p = candle['max']
        low_p = candle['min']
        body = abs(close_p - open_p)
        upper_wick = high_p - max(open_p, close_p)
        lower_wick = min(open_p, close_p) - low_p
        color = 'green' if close_p > open_p else 'red' if close_p < open_p else 'doji'
        return { 'color': color, 'body': body, 'upper_wick': upper_wick, 'lower_wick': lower_wick, 'close': close_p, 'open': open_p, 'max': high_p, 'min': low_p }

    @staticmethod
    def check_candle_quality(candles, asset_name):
        if len(candles) < 20: return False, "Dados insuficientes"
        last_closed = candles[-2] 
        current_body = abs(last_closed['close'] - last_closed['open'])
        
        MIN_BODY = 0.015 if "JPY" in asset_name else 0.00015
        if current_body < MIN_BODY: return False, "Mercado Morto"

        bodies = [abs(c['close'] - c['open']) for c in candles[-12:-2]]
        avg_body = sum(bodies) / len(bodies) if bodies else 0.00001
        
        if current_body < (avg_body * 0.6): return False, "Candle fraco (<60% média)"
            
        ema21 = TechnicalAnalysis.calculate_ema(candles[:-1], 21) 
        distance = abs(last_closed['close'] - ema21)
        if distance < (avg_body * 0.5): return False, "Sem deslocamento real"

        ranges = [(c['max'] - c['min']) for c in candles[-15:-2]]
        avg_range = sum(ranges) / len(ranges) if ranges else 0.0001
        last_range = last_closed['max'] - last_closed['min']
        
        if last_range > (avg_range * 2.5):
            return False, "Spike de volatilidade (Exaustão)"
            
        return True, "OK"

    @staticmethod
    def calculate_entry_score(candles, regime, strength, sig, asset_name, strategy_type="TREND"):
        """Calcula score de 0 a 100 para a entrada."""
        score = 0
        details = []

        last_closed = candles[-2]
        body = abs(last_closed['close'] - last_closed['open'])
        bodies = [abs(c['close'] - c['open']) for c in candles[-12:-2]]
        avg_body = sum(bodies) / len(bodies) if bodies else 0.00001
        
        # --- SCORE PARA ESTRATÉGIA DE SHOCK ---
        if strategy_type == "SHOCK_REVERSAL":
            score = 70 # Base alta pois já passou pelos filtros rígidos
            details.append("Base Shock")
            
            # Bônus por força extrema do corpo
            if body >= avg_body * 2.0:
                score += 10
                details.append("Corpo Massivo (>2x)")
            
            # Bônus por fechamento extremo (top/bottom 10%)
            rng = last_closed['max'] - last_closed['min']
            if sig == 'put': # Shock de alta
                if last_closed['close'] >= last_closed['max'] - (rng * 0.10):
                    score += 10
                    details.append("Fechamento no Talo")
            else: # Shock de baixa
                if last_closed['close'] <= last_closed['min'] + (rng * 0.10):
                    score += 10
                    details.append("Fechamento no Fundo")

            # Penalidade se for contra tendência forte (Safety)
            if regime == "TREND" and strength == "STRONG":
                score -= 20
                details.append("Contra Trend Forte")

            return score, ", ".join(details)

        # --- SCORE PARA ESTRATÉGIAS DE TENDÊNCIA (V2 / MICRO) ---
        score += 20 
        details.append("Contexto OK")
        
        ema9 = TechnicalAnalysis.calculate_ema(candles[:-1], 9)
        ema21 = TechnicalAnalysis.calculate_ema(candles[:-1], 21)
        spread = abs(ema9 - ema21)
        if spread > (avg_body * 0.5):
            score += 10
            details.append("Spread Forte")

        if regime == "TREND" and strength == "STRONG":
            score += 25
            details.append("Trend Strong")
        elif regime == "TREND" and strength == "WEAK":
            score += 15 
            details.append("Micro Pullback")

        if body > (avg_body * 1.3):
            score += 20
            details.append("Expansão Forte")
        elif body > (avg_body * 1.1):
            score += 10
            details.append("Expansão Moderada")

        if TechnicalAnalysis.engulf_filter(candles, sig):
            score += 15
            details.append("Engolfo Limpo")
        
        hr = datetime.now(BR_TIMEZONE).hour
        if 8 <= hr <= 11 or 15 <= hr <= 17:
            score += 10
            details.append("Horário Nobre")

        return score, ", ".join(details)

    @staticmethod
    def check_compression(candles):
        if len(candles) < 20: return False
        ema9 = TechnicalAnalysis.calculate_ema(candles[:-1], 9)
        ema21 = TechnicalAnalysis.calculate_ema(candles[:-1], 21)
        bodies = [abs(c['close'] - c['open']) for c in candles[-11:-1]]
        avg_body = sum(bodies) / len(bodies) if bodies else 0.00001
        spread = abs(ema9 - ema21)
        if spread < (avg_body * 0.15): return True 
        return False

    @staticmethod
    def get_signal(candles):
        """Estratégia EMA V2 (Tendência Forte)"""
        if len(candles) < 60: return None, "Dados insuficientes"
        
        current_hour = datetime.now(BR_TIMEZONE).hour
        engulf_required = True
        if current_hour >= 14: engulf_required = False

        ema9 = TechnicalAnalysis.calculate_ema(candles[:-1], 9)
        ema21 = TechnicalAnalysis.calculate_ema(candles[:-1], 21)
        ema21_prev = TechnicalAnalysis.calculate_ema(candles[:-2], 21)
        
        confirm_candle = TechnicalAnalysis.analyze_candle(candles[-2])
        reject_candle = TechnicalAnalysis.analyze_candle(candles[-3])
        
        avg_body = sum([abs(c['close']-c['open']) for c in candles[-8:-3]]) / 5
        min_slope = avg_body * 0.02
        ema21_slope = ema21 - ema21_prev
        
        if ema9 > ema21 and ema21_slope > min_slope:
            touched_ema = reject_candle['min'] <= (ema21 + (avg_body * 0.1))
            held_support = reject_candle['close'] >= (ema21 - (avg_body * 0.3))
            if touched_ema and held_support:
                if confirm_candle['color'] == 'green' and confirm_candle['close'] > confirm_candle['open']:
                     return 'call', "V2 CALL"

        elif ema9 < ema21 and ema21_slope < -min_slope:
            touched_ema = reject_candle['max'] >= (ema21 - (avg_body * 0.1))
            held_resistance = reject_candle['close'] <= (ema21 + (avg_body * 0.3))
            if touched_ema and held_resistance:
                if confirm_candle['color'] == 'red' and confirm_candle['close'] < confirm_candle['open']:
                     return 'put', "V2 PUT"
        return None, "Sem configuração"

    @staticmethod
    def engulf_filter(candles, direction):
        last = TechnicalAnalysis.analyze_candle(candles[-2])
        prev = TechnicalAnalysis.analyze_candle(candles[-3])
        if direction == "call": return (last['color'] == 'green' and prev['color'] == 'red' and last['body'] >= prev['body'] * 0.6)
        if direction == "put": return (last['color'] == 'red' and prev['color'] == 'green' and last['body'] >= prev['body'] * 0.6)
        return False

# --- 🔥 NOVA ESTRATÉGIA: SHOCK REVERSAL ---
class ShockReversalStrategy:
    @staticmethod
    def get_signal(candles):
        if len(candles) < 20: return None, "Dados insuficientes"
        
        last_closed = candles[-2] # Vela de explosão
        # prev = candles[-3]
        
        # Estatísticas recentes (10 velas ANTES do shock)
        bodies = [abs(c['close'] - c['open']) for c in candles[-12:-2]]
        avg_body = sum(bodies) / len(bodies) if bodies else 0.00001
        
        ranges = [(c['max'] - c['min']) for c in candles[-12:-2]]
        avg_range = sum(ranges) / len(ranges) if ranges else 0.00001
        
        # Dados da vela atual
        body = abs(last_closed['close'] - last_closed['open'])
        rng = last_closed['max'] - last_closed['min']
        
        if rng == 0: return None, "Doji"

        # --- SHOCK UP (Explosão de Alta) ---
        if last_closed['close'] > last_closed['open']: # Verde
            upper_wick = last_closed['max'] - last_closed['close']
            
            # 1. Tamanho do corpo e range (Explosão)
            if body >= (avg_body * 1.6) and rng >= (avg_range * 1.6):
                # 2. Fechamento no topo (esticado)
                if last_closed['close'] >= last_closed['max'] - (rng * 0.15):
                    # 3. Wick controlado
                    if upper_wick <= (body * 0.6):
                        return "put", "SHOCK_UP_REVERSAL"
        
        # --- SHOCK DOWN (Explosão de Baixa) ---
        elif last_closed['close'] < last_closed['open']: # Vermelha
            lower_wick = last_closed['close'] - last_closed['min']
            
            if body >= (avg_body * 1.6) and rng >= (avg_range * 1.6):
                if last_closed['close'] <= last_closed['min'] + (rng * 0.15):
                    if lower_wick <= (body * 0.6):
                        return "call", "SHOCK_DOWN_REVERSAL"
                        
        return None, "Sem Shock"

class MarketRegimeClassifier:
    @staticmethod
    def classify(candles):
        if not candles or len(candles) < 50: return "RANGE"
        if TechnicalAnalysis.check_compression(candles): return "NO_TRADE"

        bodies = [abs(c['close'] - c['open']) for c in candles[-21:-1]]
        avg_body = sum(bodies) / len(bodies) if bodies else 0.00001
        
        ema9_now = TechnicalAnalysis.calculate_ema(candles[:-1], 9)
        ema21_now = TechnicalAnalysis.calculate_ema(candles[:-1], 21)
        ema21_prev = TechnicalAnalysis.calculate_ema(candles[:-2], 21)

        ema_slope = abs(ema21_now - ema21_prev)
        slope_ok = ema_slope >= (avg_body * 0.15)
        spread = abs(ema9_now - ema21_now)
        spread_ok = spread >= (avg_body * 0.25)

        return "TREND" if (slope_ok and spread_ok) else "RANGE"

class TrendStrength:
    @staticmethod
    def classify(candles):
        if len(candles) < 60: return "WEAK"
        ema9 = TechnicalAnalysis.calculate_ema(candles[:-1], 9)
        ema21 = TechnicalAnalysis.calculate_ema(candles[:-1], 21)
        ema21_prev = TechnicalAnalysis.calculate_ema(candles[:-2], 21)
        avg_body = sum(abs(c['close'] - c['open']) for c in candles[-21:-1]) / 20
        spread = abs(ema9 - ema21)
        slope = abs(ema21 - ema21_prev)
        if spread > avg_body * 0.25 and slope > avg_body * 0.05: return "STRONG"
        return "WEAK"

class MicroPullbackStrategy:
    @staticmethod
    def get_signal(candles):
        if len(candles) < 50: return None, "Dados insuficientes"
        ema9 = TechnicalAnalysis.calculate_ema(candles[:-1], 9)
        ema21 = TechnicalAnalysis.calculate_ema(candles[:-1], 21)
        last = TechnicalAnalysis.analyze_candle(candles[-2])
        prev = TechnicalAnalysis.analyze_candle(candles[-3])
        bodies = [abs(c['close'] - c['open']) for c in candles[-22:-2]]
        avg_body = sum(bodies) / len(bodies)

        if avg_body <= 0: return None, "Sem volatilidade"

        if ema9 > ema21:
            if prev['color'] == 'red' and prev['body'] < avg_body * 0.6:
                if (last['color'] == 'green' and last['body'] >= avg_body * 0.9 and last['close'] > ema9 and last['upper_wick'] < last['body'] * 0.4):
                    return "call", "MICRO_PULLBACK_CALL"
        if ema9 < ema21:
            if prev['color'] == 'green' and prev['body'] < avg_body * 0.6:
                if (last['color'] == 'red' and last['body'] >= avg_body * 0.9 and last['close'] < ema9 and last['lower_wick'] < last['body'] * 0.4):
                    return "put", "MICRO_PULLBACK_PUT"
        return None, "Sem padrão"

class RangeStrategy:
    @staticmethod
    def get_signal(candles):
        return None, "RANGE_DISABLED"

# ==============================================================================
#                               BOT PRINCIPAL
# ==============================================================================

class SimpleBot:
    def __init__(self):
        self.api = None
        self.supabase = None
        self.trade_lock = threading.Lock()
        self.active_trades = set()
        self.active_account_type = None
        self.best_assets = []
        self.asset_stats = {} 
        self.config = { 
            "status": "PAUSED", "account_type": "PRACTICE", "entry_value": 1.0,
            "max_trades_per_day": 0, "max_wins_per_day": 0, "max_losses_per_day": 0,
            "timer_enabled": False, "timer_start": "00:00", "timer_end": "00:00",
            "mode": "LIVE",
            "strategy_mode": "AUTO" # V2_TREND, SHOCK_REVERSAL, AUTO
        }
        self.last_loss_time = 0
        self.asset_cooldowns = {}  
        self.last_trade_time = {}
        self.consecutive_losses = {} 
        self.range_loss_by_hour = {} 
        self.hourly_loss_count = {}
        self.last_catalog_time = 0 
        
        # --- CONTADORES DIÁRIOS/SESSÃO ---
        self.session_blocked = False
        self.session_start_time = None 
        self.session_initial_balance = 0.0
        self.last_blocked_log = 0 
        
        self.daily_wins = 0
        self.daily_losses = 0
        self.daily_total = 0
        self.current_date = datetime.now(BR_TIMEZONE).date()

        self.strategy_performance = {
            "TREND_STRONG": {'wins': 0, 'losses': 0, 'consecutive_losses': 0, 'active': True},
            "TREND_WEAK": {'wins': 0, 'losses': 0, 'consecutive_losses': 0, 'active': True},
            "SHOCK_REVERSAL": {'wins': 0, 'losses': 0, 'consecutive_losses': 0, 'active': True},
            "RANGE": {'wins': 0, 'losses': 0, 'consecutive_losses': 0, 'active': False} 
        }
        self.init_supabase()

    def init_supabase(self):
        try:
            self.supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
            print("✅ Supabase conectado.")
        except Exception as e:
            print(f"❌ Erro Supabase: {e}")

    def log_to_db(self, message, level="INFO"):
        global LAST_LOG_TIME
        LAST_LOG_TIME = time.time()
        print(f"[{level}] {message}")
        if level == "DEBUG": return 
        if not self.supabase: return
        try:
            self.supabase.table("logs").insert({
                "message": message, "level": level, "created_at": datetime.now(timezone.utc).isoformat()
            }).execute()
        except: 
            try: self.supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
            except: pass
    
    def log_rejection(self, asset, reason, regime):
        try:
            hr = datetime.now(BR_TIMEZONE).hour
            if self.supabase:
                self.supabase.table("rejection_logs").insert({
                    "pair": asset, "reason": reason, "regime": regime, "hour": hr
                }).execute()
        except: pass
        self.log_to_db(f"⛔ {asset} Ignorado: {reason}", "DEBUG")

    def check_ip(self):
        try:
            ip = requests.get('https://api.ipify.org', timeout=5).text
            print(f"[NET] IP Público: {ip}")
        except: 
            print("[NET] Não foi possível verificar IP")

    def update_balance_remote(self):
        if not self.api or not self.supabase: return
        try:
            balance = self.api.get_balance()
            self.supabase.table("bot_config").update({"current_balance": balance}).eq("id", 1).execute()
        except: pass

    def start_new_session(self):
        self.session_blocked = False 
        self.consecutive_losses.clear() 
        self.range_loss_by_hour.clear()
        self.hourly_loss_count.clear() 
        self.daily_wins = 0
        self.daily_losses = 0
        self.daily_total = 0
        
        # Reset Strategies
        for k in self.strategy_performance:
             self.strategy_performance[k] = {'wins': 0, 'losses': 0, 'consecutive_losses': 0, 'active': True}
        self.strategy_performance["RANGE"]["active"] = False

        if self.api: self.update_balance_remote()
        self.log_to_db(f"🚀 NOVA SESSÃO INICIADA ({self.config.get('mode', 'LIVE')})", "SYSTEM")

    def get_min_score(self):
        base = 75
        if self.daily_losses >= 2 and self.daily_wins == 0: return base + 5
        if self.daily_wins >= 3 and self.daily_losses == 0: return base - 5
        return base

    def get_entry_value(self):
        base = self.config["entry_value"]
        if self.daily_losses >= 1: return round(base * 0.8, 2)
        if self.daily_wins >= 2 and self.daily_losses == 0: return round(base * 1.2, 2)
        return base

    def update_strategy_stats(self, strategy_key, result, asset):
        current_hour = datetime.now(BR_TIMEZONE).hour
        self.daily_total += 1
        
        if result == 'WIN':
            self.daily_wins += 1
            self.consecutive_losses[asset] = 0
            self.asset_cooldowns.pop(asset, None)
        elif result == 'LOSS':
            self.daily_losses += 1
            self.hourly_loss_count[current_hour] = self.hourly_loss_count.get(current_hour, 0) + 1
            
            if self.hourly_loss_count[current_hour] >= 2:
                 self.log_to_db(f"⛔ Horário {current_hour}h bloqueado hoje (2 Losses)", "WARNING")

            current_cons = self.consecutive_losses.get(asset, 0) + 1
            self.consecutive_losses[asset] = current_cons
            cd = 120 if current_cons == 1 else 300
            self.asset_cooldowns[asset] = time.time() + cd
            self.log_to_db(f"🛑 Cooldown {asset}: {cd}s", "WARNING")

        if self.config["mode"] == "OBSERVE": return 

        key = strategy_key if strategy_key in self.strategy_performance else "UNKNOWN"
        if key == "UNKNOWN": return
        stats = self.strategy_performance[key]
        if result == 'WIN':
            stats['wins'] += 1
            stats['consecutive_losses'] = 0
        else:
            stats['losses'] += 1
            stats['consecutive_losses'] += 1
            # Self-Disable
            if key == "SHOCK_REVERSAL" and stats['losses'] >= 2:
                 stats['active'] = False
                 self.log_to_db(f"🚫 SHOCK_REVERSAL Desativada (2 Losses)", "WARNING")
            elif key == "TREND_WEAK" and stats['losses'] >= 2:
                 stats['active'] = False
                 self.log_to_db(f"🚫 Estratégia MICRO-TREND Desativada", "WARNING")
            elif key == "TREND_STRONG" and (stats['consecutive_losses'] >= 3 or stats['losses'] >= 4):
                 stats['active'] = False
                 self.log_to_db(f"🚫 Estratégia TREND STRONG Desativada", "WARNING")

    def check_auto_disable(self):
        active_strats = [k for k, v in self.strategy_performance.items() if v['active']]
        if not active_strats:
            self.log_to_db("🧠 Todas estratégias falharam. Pausando bot.", "WARNING")
            self.session_blocked = True
            self.pause_bot_by_management()
            return False
        return True

    def is_strategy_active(self, strategy_key):
        return self.strategy_performance.get(strategy_key, {}).get('active', True)

    def fetch_config(self):
        if not self.supabase: self.init_supabase(); return
        try:
            res = self.supabase.table("bot_config").select("*").eq("id", 1).execute()
            if not res.data:
                self.supabase.table("bot_config").insert({"id": 1, "status": "PAUSED"}).execute()
                return

            data = res.data[0]
            
            prev_status = self.config.get("status")
            new_status = (data.get("status") or "PAUSED").strip().upper()
            prev_mode = self.config.get("mode")
            new_mode = (data.get("mode") or "LIVE").strip().upper()

            if new_status == "RESTARTING":
                self.log_to_db("♻️ RESTARTING recebido...", "SYSTEM")
                if self.supabase:
                    try: self.supabase.table("bot_config").update({"status": "RUNNING"}).eq("id", 1).execute()
                    except: pass
                if self.api: 
                    try: self.api.api.close()
                    except: pass
                self.api = None
                time.sleep(2)
                self.connect()
                new_status = "RUNNING" 

            if self.session_blocked and new_status == "RUNNING":
                 self.log_to_db("⛔ Bloqueado por limite diário. Ignorando RUNNING.", "WARNING")
                 try: self.supabase.table("bot_config").update({"status": "PAUSED"}).eq("id", 1).execute()
                 except: pass
                 new_status = "PAUSED"

            if ((prev_status != "RUNNING" and new_status == "RUNNING") or (prev_mode != new_mode)) and not self.session_blocked:
                self.start_new_session()
            
            self.config.update({
                "status": new_status,
                "mode": new_mode,
                "strategy_mode": (data.get("strategy_mode") or "AUTO").strip().upper(),
                "account_type": (data.get("account_type") or "PRACTICE").strip().upper(),
                "entry_value": float(data.get("entry_value") or 1.0),
                "max_trades_per_day": int(data.get("max_trades_per_day") or 0),
                "max_wins_per_day": int(data.get("max_wins_per_day") or 0),
                "max_losses_per_day": int(data.get("max_losses_per_day") or 0),
                "timer_enabled": bool(data.get("timer_enabled")),
                "timer_start": str(data.get("timer_start") or "00:00"),
                "timer_end": str(data.get("timer_end") or "00:00")
            })

        except Exception as e:
            self.log_to_db(f"❌ Erro fetch_config: {e}", "ERROR")
            self.init_supabase()

    def check_schedule(self):
        if self.session_blocked: return

        if not self.config.get("timer_enabled", False): return 
        now_br = datetime.now(BR_TIMEZONE)
        now_str = now_br.strftime("%H:%M")
        start_str = self.config.get("timer_start", "00:00")
        end_str = self.config.get("timer_end", "00:00")
        hour = now_br.hour
        minute = now_br.minute
        
        if 0 <= hour < 4: return
        if hour == 13 and minute >= 30: return
        if hour == 14 and minute <= 30: return

        is_inside = False
        if start_str < end_str: is_inside = start_str <= now_str < end_str
        else: is_inside = now_str >= start_str or now_str < end_str
        
        current_status = self.config["status"]
        if is_inside and current_status == "PAUSED":
            if self.session_blocked: return 
            self.log_to_db(f"⏰ Agendador: Iniciando operações ({start_str}-{end_str})", "SYSTEM")
            if self.supabase: self.supabase.table("bot_config").update({"status": "RUNNING"}).eq("id", 1).execute()
        elif not is_inside and current_status == "RUNNING":
            self.log_to_db(f"⏰ Agendador: Pausando operações (Fim do horário)", "SYSTEM")
            if self.supabase: self.supabase.table("bot_config").update({"status": "PAUSED"}).eq("id", 1).execute()

    def check_daily_limits(self):
        today = datetime.now(BR_TIMEZONE).date()
        if today != self.current_date:
            self.current_date = today
            self.start_new_session()
            return True

        if self.config["mode"] == "OBSERVE": return True

        max_trades = self.config["max_trades_per_day"]
        max_wins = self.config["max_wins_per_day"]
        max_losses = self.config["max_losses_per_day"]

        if max_trades > 0 and self.daily_total >= max_trades:
            self.log_to_db(f"🛑 Limite de Trades atingido ({self.daily_total}/{max_trades})", "WARNING")
            return False
        if max_wins > 0 and self.daily_wins >= max_wins:
            self.log_to_db(f"🏆 Meta de Wins atingida ({self.daily_wins}/{max_wins})", "SUCCESS")
            return False
        if max_losses > 0 and self.daily_losses >= max_losses:
            self.log_to_db(f"❌ Limite de Losses atingido ({self.daily_losses}/{max_losses})", "ERROR")
            return False
        return True

    def pause_bot_by_management(self):
        self.config["status"] = "PAUSED"
        if self.supabase: 
            try: self.supabase.table("bot_config").update({"status": "PAUSED"}).eq("id", 1).execute()
            except: pass
        time.sleep(2)

    def connect(self):
        self.log_to_db(f"🔌 Conectando...", "SYSTEM")
        try:
            if self.api: 
                try: self.api.api.close() 
                except: pass
            self.api = Exnova(EXNOVA_EMAIL, EXNOVA_PASSWORD)
            check, reason = self.api.connect()
            if check:
                self.log_to_db("✅ Conectado!", "SUCCESS")
                self.active_account_type = self.config["account_type"]
                self.api.change_balance(self.active_account_type)
                self.update_balance_remote()
                return True
            else:
                self.log_to_db(f"Falha conexão: {reason}", "ERROR")
        except Exception as e:
            self.log_to_db(f"Erro critico conexão: {e}", "ERROR")
        return False

    def catalog_assets(self, assets_pool):
        if time.time() - self.last_catalog_time < 1800 and self.best_assets:
             return self.best_assets

        self.log_to_db(f"📊 Catalogando Top 3 (Win Rate >= 70%)...", "SYSTEM")
        results = []
        for asset in assets_pool:
            try:
                candles = self.api.get_candles(asset, 60, 100, int(time.time()))
                if not candles: continue
                wins, total = 0, 0
                for i in range(50, len(candles)-1):
                    sub = candles[i-50:i+1]
                    # Simula V2
                    sig, _ = TechnicalAnalysis.get_signal(sub)
                    if sig:
                        total += 1
                        nxt = candles[i+1]
                        is_win = (sig == 'call' and nxt['close'] > nxt['open']) or (sig=='put' and nxt['close']<nxt['open'])
                        if is_win: wins += 1
                if total >= 5: 
                    wr = (wins / total) * 100
                    if wr >= 70:
                       results.append({'pair': asset, 'win_rate': wr, 'best_strategy': 'V2/Shock'})
            except: pass
            time.sleep(0.05)
        
        results.sort(key=lambda x: x['win_rate'], reverse=True)
        final_list = results[:3]
        if self.supabase:
             try:
                 self.supabase.table("cataloged_assets").delete().neq("pair", "XYZ").execute()
                 if final_list: self.supabase.table("cataloged_assets").insert(final_list).execute()
             except: pass
        
        self.last_catalog_time = time.time()
        if not final_list: self.log_to_db("⚠️ Nenhum ativo >= 70% WR. Aguardando.", "WARNING")
        else: 
            pairs_str = ", ".join([f"{r['pair']} ({r['win_rate']:.0f}%)" for r in final_list])
            self.log_to_db(f"💎 Melhores: {pairs_str}", "SUCCESS")

        return [x['pair'] for x in final_list]

    def safe_buy(self, asset, amount, direction):
        if self.config["mode"] == "OBSERVE": return True, "VIRTUAL"
        try:
             status, id = self.api.buy_digital_spot(asset, amount, direction, 1)
             if not status:
                 status, id = self.api.buy(amount, asset, direction, 1)
             return status, id
        except: return False, None

    def execute_trade(self, asset, direction, strategy_key, strategy_name="Unknown"):
        # AJUSTE 2: uso de last_trade_time
        now = time.time()
        if asset in self.last_trade_time and now - self.last_trade_time[asset] < 120:
             return
        self.last_trade_time[asset] = now

        with self.trade_lock:
            if asset in self.active_trades: return
            self.active_trades.add(asset)

        try:
            current_hour = datetime.now(BR_TIMEZONE).hour
            if self.hourly_loss_count.get(current_hour, 0) >= 2:
                 self.log_rejection(asset, f"Horário {current_hour}h bloqueado", "ALL")
                 return

            if asset in self.asset_cooldowns:
                 if time.time() < self.asset_cooldowns[asset]: return

            if not self.check_daily_limits():
                self.session_blocked = True
                self.pause_bot_by_management()
                return
            
            if not self.check_auto_disable(): return

            if not self.strategy_performance.get(strategy_key, {}).get("active", True):
                self.log_rejection(asset, f"Estratégia {strategy_key} desativada", "ALL")
                return

            # 🔥 STAKE ADAPTATIVO
            if self.config["mode"] == "OBSERVE":
                amount = self.config["entry_value"]
            else:
                amount = self.get_entry_value()
            
            mode_prefix = "[OBSERVE] " if self.config["mode"] == "OBSERVE" else ""
            self.log_to_db(f"➡️ {mode_prefix}ENTRADA ({strategy_name}): {asset} | {direction.upper()} | ${amount}", "INFO")

            balance_before = 0.0
            if self.config["mode"] == "LIVE":
                try: 
                    balance_before = self.api.get_balance()
                    if balance_before <= 0:
                        self.log_to_db("❌ Saldo zerado ou inválido.", "ERROR")
                        self.pause_bot_by_management()
                        return
                except: return

            status, id = self.safe_buy(asset, amount, direction)

            if status:
                self.log_to_db(f"✅ Ordem {id} aceita. Aguardando...", "INFO")
                self.log_to_db("⏳ Aguardando fechamento da vela...", "DEBUG")
                time.sleep(62) 
                
                res_str = "DOJI"
                profit = 0.0
                
                if self.config["mode"] == "OBSERVE":
                    try:
                        candles = self.api.get_candles(asset, 60, 2, int(time.time()))
                        last = candles[-2] 
                        is_win = (direction == 'call' and last['close'] > last['open']) or \
                                 (direction == 'put' and last['close'] < last['open'])
                        
                        if is_win: 
                            res_str = "WIN"
                            profit = amount * 0.87
                        elif abs(last['close'] - last['open']) < 0.000001:
                            res_str = "DOJI"
                            profit = 0
                        else:
                            res_str = "LOSS"
                            profit = -amount
                    except: res_str = "UNKNOWN"
                else:
                    try:
                        balance_after = self.api.get_balance()
                        delta = balance_after - balance_before
                        if delta > 0.01: res_str = "WIN"; profit = delta
                        elif delta < -0.01: res_str = "LOSS"; profit = delta
                    except: res_str = "UNKNOWN"

                if res_str == 'DOJI':
                    self.log_to_db("DOJI neutro", "DEBUG")
                    return

                # 🔥 ATUALIZAÇÃO CENTRALIZADA
                self.update_strategy_stats(strategy_key, res_str, asset)

                log_type = "SUCCESS" if res_str == 'WIN' else "ERROR"
                self.log_to_db(f"{mode_prefix}{'🏆' if res_str == 'WIN' else '🔻'} {res_str}: ${profit:.2f} ({self.daily_wins}W/{self.daily_losses}L)", log_type)
                
                if self.supabase:
                     try: self.supabase.table("trade_signals").insert({
                         "pair": asset, "direction": direction, "result": res_str, 
                         "profit": profit, "created_at": datetime.now(timezone.utc).isoformat(),
                         "strategy": f"{strategy_key} ({self.config['mode']})"
                     }).execute()
                     except: pass
                     if self.config["mode"] == "LIVE": self.update_balance_remote()

                # 🔥 BLOQUEIO IMEDIATO AO ATINGIR LIMITE
                if not self.check_daily_limits():
                     self.log_to_db("🛑 LIMITE DIÁRIO ATINGIDO — PAUSANDO BOT IMEDIATAMENTE", "WARNING")
                     self.session_blocked = True
                     self.pause_bot_by_management()

            else:
                self.log_to_db("❌ Falha na ordem", "ERROR")

        finally:
            with self.trade_lock: self.active_trades.discard(asset)

    def start(self):
        t_watchdog = threading.Thread(target=watchdog, daemon=True)
        t_watchdog.start()
        self.check_ip()
        
        while True:
            try:
                global LAST_LOG_TIME
                LAST_LOG_TIME = time.time()
                self.fetch_config()
                
                if not self.check_daily_limits():
                    if time.time() - self.last_blocked_log > 300:
                         self.log_to_db("⛔ Limite diário atingido (Loop).", "WARNING")
                         self.last_blocked_log = time.time()
                    self.session_blocked = True
                    self.pause_bot_by_management()
                    time.sleep(10)
                    continue

                if self.session_blocked:
                    if time.time() - self.last_blocked_log > 300:
                        self.log_to_db("⛔ Bloqueado por limite diário.", "WARNING")
                        self.last_blocked_log = time.time()
                    self.supabase.table("bot_config").update({"status": "PAUSED"}).eq("id", 1).execute()
                    time.sleep(10)
                    continue
                
                self.check_schedule()
                
                if self.config["status"] == "PAUSED":
                    time.sleep(5)
                    continue

                if self.config["status"] == "RESTARTING":
                    if self.supabase: self.supabase.table("bot_config").update({"status": "RUNNING"}).eq("id", 1).execute()
                    break
                
                if not self.api.check_connect(): 
                    self.connect()
                    continue

                if not self.best_assets or int(time.time()) % 900 < 5:
                    self.best_assets = self.catalog_assets(["EURUSD-OTC", "EURGBP-OTC", "USDCHF-OTC", "EURJPY-OTC", "NZDUSD-OTC", "GBPUSD-OTC", "GBPJPY-OTC", "USDJPY-OTC", "AUDCAD-OTC", "AUDUSD-OTC", "USDCAD-OTC", "AUDJPY-OTC"])

                now_sec = datetime.now().second
                if 55 <= now_sec <= 59:
                     strat_mode = self.config.get("strategy_mode", "AUTO")
                     for asset in self.best_assets:
                         with self.trade_lock:
                             if asset in self.active_trades: continue
                         try:
                             candles = self.api.get_candles(asset, 60, 100, int(time.time()))
                             if candles:
                                 qual, q_reason = TechnicalAnalysis.check_candle_quality(candles, asset)
                                 if not qual: 
                                     self.log_rejection(asset, q_reason, "QUALITY")
                                     continue
                                 if TechnicalAnalysis.check_compression(candles): 
                                     self.log_rejection(asset, "Compressão", "COMPRESSION")
                                     continue

                                 regime = MarketRegimeClassifier.classify(candles)
                                 sig, reason, strat_key = None, "", "UNKNOWN"
                                 strength = "WEAK" 
                                 
                                 # 1. SHOCK REVERSAL (SE HABILITADO)
                                 if strat_mode in ["AUTO", "SHOCK_REVERSAL"]:
                                     sig_shock, reason_shock = ShockReversalStrategy.get_signal(candles)
                                     if sig_shock:
                                          # Filtro extra: Não opera contra TREND STRONG
                                          st = TrendStrength.classify(candles)
                                          if regime == "TREND" and st == "STRONG":
                                               self.log_rejection(asset, "Shock contra Trend Forte", "SHOCK")
                                          else:
                                               sig, reason, strat_key = sig_shock, reason_shock, "SHOCK_REVERSAL"

                                 # 2. V2 TREND (SE AINDA NÃO ACHOU SINAL E MODO PERMITIR)
                                 if not sig and strat_mode in ["AUTO", "V2_TREND"]:
                                     if regime == "TREND":
                                         strength = TrendStrength.classify(candles)
                                         if strength == "STRONG": 
                                             sig, reason = TechnicalAnalysis.get_signal(candles)
                                             strat_key = "TREND_STRONG"
                                         else: 
                                             sig, reason = MicroPullbackStrategy.get_signal(candles)
                                             strat_key = "TREND_WEAK"
                                 
                                 if sig:
                                     min_score = self.get_min_score()
                                     score, score_det = TechnicalAnalysis.calculate_entry_score(candles, regime, strength, sig, asset, strat_key) # Passa strat_key
                                     
                                     if score >= min_score:
                                         self.execute_trade(asset, sig, strat_key, reason)
                                         break 
                                     else:
                                         self.log_rejection(asset, f"Score {score} < {min_score}: {score_det}", regime)
                         except: pass
                     time.sleep(1)
                time.sleep(0.5)
            except Exception as e:
                self.log_to_db(f"Erro loop principal: {e}", "ERROR")
                time.sleep(5)

if __name__ == "__main__":
    SimpleBot().start()
