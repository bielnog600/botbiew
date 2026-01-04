import sys
import time
import logging
import json
import threading
import os
import random
import requests
from datetime import datetime, timedelta, timezone
# Certifique-se de instalar: pip install supabase exnovaapi requests
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

# --- CONFIGURAÇÃO AVANÇADA ---
WATCHDOG_CHECK_EVERY = 60
WATCHDOG_MAX_SILENCE = 180
COOLIFY_RESTART_URL = "https://biewdev.se/api/v1/applications/ig80skg8ssog04g4oo88wswg/restart"
COOLIFY_API_TOKEN = os.environ.get("COOLIFY_API_TOKEN")
GLOBAL_TIME_OFFSET = 0
LAST_LOG_TIME = time.time()

# --- FUSO HORÁRIO BRASIL (UTC-3) ---
BR_TIMEZONE = timezone(timedelta(hours=-3))

# --- SUPRESSÃO DE LOGS ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
for logger_name in ["websocket", "exnovaapi", "iqoptionapi", "urllib3", "iqoptionapi.websocket.client"]:
    logging.getLogger(logger_name).setLevel(logging.CRITICAL)

# --- FUNÇÃO WATCHDOG ---
def watchdog():
    global LAST_LOG_TIME
    print("[WATCHDOG] Monitoramento de saúde iniciado.")
    
    while True:
        time.sleep(WATCHDOG_CHECK_EVERY)
        silence_duration = time.time() - LAST_LOG_TIME
        
        if silence_duration > WATCHDOG_MAX_SILENCE:
            print(f"[WATCHDOG] ⚠️ ALERTA: Bot travado por {int(silence_duration)}s. Reiniciando via Coolify...")
            if COOLIFY_API_TOKEN:
                try:
                    requests.post(
                        COOLIFY_RESTART_URL,
                        headers={"Authorization": f"Bearer {COOLIFY_API_TOKEN}", "Content-Type": "application/json"},
                        timeout=15
                    )
                except Exception as e: 
                    print(f"[WATCHDOG ERROR] Falha ao reiniciar: {e}")
            os._exit(1)

# --- ANÁLISE TÉCNICA (V2 ENGINE) ---
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
    def flow_filter(candles):
        if len(candles) < 50: return None 
        candles = candles[-80:]
        buffer_series = []
        for i in range(35, len(candles) + 1):
            slice_c = candles[:i]
            fast = TechnicalAnalysis.calculate_sma(slice_c, 3)
            slow = TechnicalAnalysis.calculate_sma(slice_c, 34)
            buffer_series.append(fast - slow)
        
        ema_values = []
        if buffer_series:
             ema = buffer_series[0]
             k = 2 / (6 + 1)
             for val in buffer_series:
                 ema = val * k + ema * (1 - k)
                 ema_values.append(ema)
        
        if len(ema_values) < 2: return None
        buffer_now = buffer_series[-1]
        signal_now = ema_values[-1]
        
        if buffer_now > signal_now: return "BULL"
        elif buffer_now < signal_now: return "BEAR"
        return None

    @staticmethod
    def engulf_filter(candles, direction):
        last = TechnicalAnalysis.analyze_candle(candles[-1])
        prev = TechnicalAnalysis.analyze_candle(candles[-2])
        if direction == "call": return (last['color'] == 'green' and prev['color'] == 'red' and last['body'] >= prev['body'] * 0.6)
        if direction == "put": return (last['color'] == 'red' and prev['color'] == 'green' and last['body'] >= prev['body'] * 0.6)
        return False

    @staticmethod
    def get_signal(candles):
        """Estratégia original EMA V2 (Para Tendência Forte)"""
        if len(candles) < 60: return None, "Dados insuficientes"
        
        current_hour = datetime.now(BR_TIMEZONE).hour
        engulf_required = True
        if current_hour >= 14: engulf_required = False

        ema9 = TechnicalAnalysis.calculate_ema(candles, 9)
        ema21 = TechnicalAnalysis.calculate_ema(candles, 21)
        ema21_prev = TechnicalAnalysis.calculate_ema(candles[:-1], 21)
        
        confirm_candle = TechnicalAnalysis.analyze_candle(candles[-1])
        reject_candle = TechnicalAnalysis.analyze_candle(candles[-2])
        
        avg_body = sum([abs(c['close']-c['open']) for c in candles[-7:-2]]) / 5
        spread = abs(ema9 - ema21)
        min_spread = avg_body * 0.1
        if spread < min_spread: return None, f"Filtro: EMAs coladas"

        ema21_slope = ema21 - ema21_prev
        min_slope = avg_body * 0.02 
        
        if ema9 > ema21 and ema21_slope > min_slope:
            touched_ema = reject_candle['min'] <= (ema21 + (avg_body * 0.1))
            held_support = reject_candle['close'] >= (ema21 - (avg_body * 0.3))
            if touched_ema and held_support:
                if reject_candle['lower_wick'] < (reject_candle['body'] * 0.4): return None, "Rejeição fraca (Pavio)"
                if confirm_candle['color'] == 'green':
                    has_strength = (confirm_candle['body'] >= (reject_candle['body'] * 0.6) and confirm_candle['body'] >= (avg_body * 0.8))
                    clean_top = confirm_candle['upper_wick'] < (confirm_candle['body'] * 0.5)
                    if has_strength and clean_top:
                        flow = TechnicalAnalysis.flow_filter(candles)
                        if flow != "BULL": return None, "Filtro Fluxo contra"
                        if engulf_required:
                            if not TechnicalAnalysis.engulf_filter(candles, "call"): return None, "Sem força (Engolfo)"
                        return 'call', "V2 CALL (Rejeição + Força + Fluxo)"
                    else: return None, "Confirmação fraca"
                else: return None, "Sem confirmação verde"

        elif ema9 < ema21 and ema21_slope < -min_slope:
            touched_ema = reject_candle['max'] >= (ema21 - (avg_body * 0.1))
            held_resistance = reject_candle['close'] <= (ema21 + (avg_body * 0.3))
            if touched_ema and held_resistance:
                if reject_candle['upper_wick'] < (reject_candle['body'] * 0.4): return None, "Rejeição fraca (Pavio)"
                if confirm_candle['color'] == 'red':
                    has_strength = (confirm_candle['body'] >= (reject_candle['body'] * 0.6) and confirm_candle['body'] >= (avg_body * 0.8))
                    clean_bottom = confirm_candle['lower_wick'] < (confirm_candle['body'] * 0.5)
                    if has_strength and clean_bottom:
                        flow = TechnicalAnalysis.flow_filter(candles)
                        if flow != "BEAR": return None, "Filtro Fluxo contra"
                        if engulf_required:
                            if not TechnicalAnalysis.engulf_filter(candles, "put"): return None, "Sem força (Engolfo)"
                        return 'put', "V2 PUT (Rejeição + Força + Fluxo)"
                    else: return None, "Confirmação fraca"
                else: return None, "Sem confirmação vermelha"
        return None, "Sem configuração V2"

class MarketRegimeClassifier:
    @staticmethod
    def classify(candles):
        """
        Retorna: 'TREND' ou 'RANGE'
        Usa apenas candles M1
        """
        if not candles or len(candles) < 50:
            return "RANGE"

        # --- PARAMETROS ---
        MIN_SLOPE_MULT = 0.15
        MIN_SPREAD_MULT = 0.25
        MIN_DIRECTIONAL_RATIO = 0.55

        # --- CALCULOS BASE ---
        bodies = [abs(c['close'] - c['open']) for c in candles[-20:]]
        avg_body = sum(bodies) / len(bodies) if bodies else 0.00001

        ema9_now = TechnicalAnalysis.calculate_ema(candles, 9)
        ema21_now = TechnicalAnalysis.calculate_ema(candles, 21)
        ema21_prev = TechnicalAnalysis.calculate_ema(candles[:-1], 21)

        # --- FILTRO 1: SLOPE EMA21 ---
        ema_slope = abs(ema21_now - ema21_prev)
        slope_ok = ema_slope >= (avg_body * MIN_SLOPE_MULT)

        # --- FILTRO 2: SPREAD ENTRE EMAS ---
        spread = abs(ema9_now - ema21_now)
        spread_ok = spread >= (avg_body * MIN_SPREAD_MULT)

        # --- FILTRO 3: DIRECIONALIDADE ---
        strong_candles = 0
        for c in candles[-20:]:
            body = abs(c['close'] - c['open'])
            rng = c['max'] - c['min']
            if rng == 0: continue
            if body / rng >= 0.55:
                strong_candles += 1

        directional_ratio = strong_candles / 20
        direction_ok = directional_ratio >= MIN_DIRECTIONAL_RATIO

        # --- DECISAO FINAL ---
        trend_score = sum([slope_ok, spread_ok, direction_ok])

        return "TREND" if trend_score >= 2 else "RANGE"

class RangeStrategy:
    @staticmethod
    def get_signal(candles):
        if len(candles) < 40: return None, "Dados insuficientes"

        last = candles[-1]
        prev = candles[-2]
        ema21 = TechnicalAnalysis.calculate_ema(candles, 21)

        avg_body = sum(abs(c['close'] - c['open']) for c in candles[-20:]) / 20
        price = last['close']
        distance = price - ema21

        # --- CONDICAO 1: EXTREMO ---
        if abs(distance) < avg_body * 1.5: return None, "Sem extremo"

        # --- CONDICAO 2: REJEICAO ---
        body = abs(prev['close'] - prev['open'])
        rng = prev['max'] - prev['min']
        if rng == 0: return None, "Range zero"

        wick_ratio = (rng - body) / rng
        if wick_ratio < 0.6: return None, "Sem rejeicao clara"

        # --- CONDICAO 3: CONFIRMACAO ---
        confirm = last['close'] < prev['close'] if distance > 0 else last['close'] > prev['close']
        if not confirm: return None, "Sem confirmacao"

        direction = "put" if distance > 0 else "call"
        return direction, "SAFE_RANGE_REVERSION"

class TrendStrength:
    @staticmethod
    def classify(candles):
        if len(candles) < 60: return "WEAK"

        ema9 = TechnicalAnalysis.calculate_ema(candles, 9)
        ema21 = TechnicalAnalysis.calculate_ema(candles, 21)
        ema21_prev = TechnicalAnalysis.calculate_ema(candles[:-1], 21)

        avg_body = sum(abs(c['close'] - c['open']) for c in candles[-20:]) / 20
        spread = abs(ema9 - ema21)
        slope = abs(ema21 - ema21_prev)

        if spread > avg_body * 0.25 and slope > avg_body * 0.05:
            return "STRONG"
        return "WEAK"

class MicroPullbackStrategy:
    @staticmethod
    def get_signal(candles):
        if len(candles) < 50:
            return None, "Dados insuficientes"

        ema9 = TechnicalAnalysis.calculate_ema(candles, 9)
        ema21 = TechnicalAnalysis.calculate_ema(candles, 21)

        last = TechnicalAnalysis.analyze_candle(candles[-1])
        prev = TechnicalAnalysis.analyze_candle(candles[-2])

        bodies = [abs(c['close'] - c['open']) for c in candles[-20:]]
        avg_body = sum(bodies) / len(bodies)

        # FILTRO CRÍTICO: mercado morto
        if avg_body <= 0:
            return None, "Sem volatilidade"

        # --- TREND UP ---
        if ema9 > ema21:
            if prev['color'] == 'red' and prev['body'] < avg_body * 0.6:
                if (
                    last['color'] == 'green'
                    and last['body'] >= avg_body * 0.9   # 🔥 corpo obrigatório
                    and last['close'] > ema9
                    and last['upper_wick'] < last['body'] * 0.4
                ):
                    return "call", "MICRO_PULLBACK_CALL_STRONG"

        # --- TREND DOWN ---
        if ema9 < ema21:
            if prev['color'] == 'green' and prev['body'] < avg_body * 0.6:
                if (
                    last['color'] == 'red'
                    and last['body'] >= avg_body * 0.9
                    and last['close'] < ema9
                    and last['lower_wick'] < last['body'] * 0.4
                ):
                    return "put", "MICRO_PULLBACK_PUT_STRONG"

        return None, "Micro pullback fraco"

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
            "stop_win": 10.0, "stop_loss": 5.0, "stop_mode": "value", "daily_initial_balance": 0.0,
            "timer_enabled": False, "timer_start": "00:00", "timer_end": "00:00"
        }
        self.last_loss_time = 0
        self.asset_cooldowns = {}  
        self.last_trade_time = {}
        self.consecutive_losses = {} 
        self.range_loss_by_hour = {} 
        
        # --- CONTROLE DE SESSÃO & MEMÓRIA DE ESTRATÉGIA ---
        self.session_blocked = False
        self.session_start_time = None
        self.session_initial_balance = 0.0
        self.last_blocked_log = 0 
        
        # MEMÓRIA DE PERFORMANCE POR ESTRATÉGIA
        # Reseta a cada nova sessão
        self.strategy_performance = {
            "TREND_STRONG": {'wins': 0, 'losses': 0, 'consecutive_losses': 0, 'active': True},
            "TREND_WEAK": {'wins': 0, 'losses': 0, 'consecutive_losses': 0, 'active': True},
            "RANGE": {'wins': 0, 'losses': 0, 'consecutive_losses': 0, 'active': True}
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
        """Inicia uma nova sessão de trading, zerando contadores"""
        self.session_blocked = False 
        self.session_start_time = datetime.now(timezone.utc)
        self.consecutive_losses.clear() 
        self.range_loss_by_hour.clear() 
        
        # RESET DE ESTRATÉGIAS
        self.strategy_performance = {
            "TREND_STRONG": {'wins': 0, 'losses': 0, 'consecutive_losses': 0, 'active': True},
            "TREND_WEAK": {'wins': 0, 'losses': 0, 'consecutive_losses': 0, 'active': True},
            "RANGE": {'wins': 0, 'losses': 0, 'consecutive_losses': 0, 'active': True}
        }
        
        if self.api:
            self.session_initial_balance = self.api.get_balance()
            if self.supabase:
                try: self.supabase.table("bot_config").update({"daily_initial_balance": self.session_initial_balance}).eq("id", 1).execute()
                except: pass
        
        self.log_to_db(f"🚀 NOVA SESSÃO INICIADA. Saldo ref: ${self.session_initial_balance:.2f}", "SYSTEM")

    def update_strategy_stats(self, strategy_key, result):
        """Atualiza a performance da estratégia e desativa se necessário"""
        # Se a chave não existir, tenta mapear (fallback), mas o ideal é usar a chave direta
        key = strategy_key
        
        if key not in self.strategy_performance:
             # Fallback para tentar mapear strings antigas (caso necessário)
            if "RANGE" in strategy_key: key = "RANGE"
            elif "MICRO_PULLBACK" in strategy_key: key = "TREND_WEAK"
            elif "V2" in strategy_key or "Trend" in strategy_key: key = "TREND_STRONG"
            else: key = "UNKNOWN"

        if key not in self.strategy_performance: return

        stats = self.strategy_performance[key]
        
        if result == 'WIN':
            stats['wins'] += 1
            stats['consecutive_losses'] = 0
        elif result == 'LOSS':
            stats['losses'] += 1
            stats['consecutive_losses'] += 1
            
            # --- LÓGICA DE SELF-DISABLE ---
            if key == "RANGE" and stats['losses'] >= 1:
                 stats['active'] = False
                 self.log_to_db(f"🚫 Estratégia RANGE DESATIVADA (Limite: 1 Loss)", "WARNING")
            
            elif key == "TREND_WEAK" and stats['losses'] >= 2:
                 stats['active'] = False
                 self.log_to_db(f"🚫 Estratégia MICRO-TREND DESATIVADA (Limite: 2 Losses)", "WARNING")

            elif key == "TREND_STRONG":
                 # Mais tolerante, mas corta se ficar muito ruim
                 if stats['consecutive_losses'] >= 3 or stats['losses'] >= 4:
                     stats['active'] = False
                     self.log_to_db(f"🚫 Estratégia TREND STRONG DESATIVADA (Performance Ruim)", "WARNING")

    def is_strategy_active(self, strategy_key):
        return self.strategy_performance.get(strategy_key, {}).get('active', True)

    def fetch_config(self):
        if not self.supabase: self.init_supabase(); return
        try:
            res = self.supabase.table("bot_config").select("*").eq("id", 1).execute()
            if res.data:
                data = res.data[0]
                prev_status = self.config.get("status")
                new_status = data.get("status", "PAUSED")
                
                if prev_status != "RUNNING" and new_status == "RUNNING":
                    self.start_new_session()
                
                self.config["status"] = new_status
                self.config["account_type"] = data.get("account_type", "PRACTICE").strip().upper()
                self.config["entry_value"] = float(data.get("entry_value", 1.0))
                self.config["stop_win"] = float(data.get("stop_win", 0))
                self.config["stop_loss"] = float(data.get("stop_loss", 0))
                self.config["stop_mode"] = data.get("stop_mode", "value")
                self.config["timer_enabled"] = data.get("timer_enabled", False)
                self.config["timer_start"] = data.get("timer_start", "00:00")
                self.config["timer_end"] = data.get("timer_end", "00:00")
            else:
                self.supabase.table("bot_config").insert({"id": 1, "status": "PAUSED"}).execute()
        except: pass

    def check_schedule(self):
        if not self.config.get("timer_enabled", False): return 
        
        now_br = datetime.now(BR_TIMEZONE)
        now_str = now_br.strftime("%H:%M")
        start_str = self.config.get("timer_start", "00:00")
        end_str = self.config.get("timer_end", "00:00")
        
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

    def calculate_session_profit(self):
        if not self.session_start_time: return 0.0
        try:
            start_iso = self.session_start_time.isoformat()
            res = self.supabase.table("trade_signals").select("profit").gte("created_at", start_iso).execute()
            if res.data:
                total = sum([float(x['profit']) for x in res.data if x['profit'] is not None])
                return total
            return 0.0
        except Exception as e:
            print(f"[CALC ERROR] {e}")
            return 0.0

    def check_management(self):
        if not self.supabase or not self.api: return True
        if not self.session_start_time: return True 

        try:
            res_exists = self.supabase.table("trade_signals").select("id").gte("created_at", self.session_start_time.isoformat()).limit(1).execute()
            if not res_exists.data:
                return True 
            
            profit = self.calculate_session_profit()
            if profit == 0: return True 
            
            stop_mode = self.config.get("stop_mode")
            stop_win = abs(float(self.config.get("stop_win", 0)))
            stop_loss = abs(float(self.config.get("stop_loss", 0)))

            if stop_mode == "percentage":
                target_win = self.session_initial_balance * (stop_win / 100)
                target_loss = self.session_initial_balance * (stop_loss / 100)
            else: # "value"
                target_win = stop_win
                target_loss = stop_loss

            self.log_to_db(
                f"[MGMT] PnL Sessão: ${profit:.2f} | Meta Win: ${target_win:.2f} | Max Loss: -${target_loss:.2f}",
                "DEBUG"
            )

            if target_win > 0 and profit >= target_win:
                self.log_to_db(f"🏆 STOP WIN DA SESSÃO ATINGIDO! Lucro: ${profit:.2f}", "SUCCESS")
                self.session_blocked = True 
                self.pause_bot_by_management()
                return False

            if target_loss > 0 and profit <= -target_loss:
                self.log_to_db(f"🛑 STOP LOSS DA SESSÃO ATINGIDO! Perda: ${profit:.2f}", "ERROR")
                self.session_blocked = True 
                self.pause_bot_by_management()
                return False

            return True

        except Exception as e:
            self.log_to_db(f"Erro no gerenciamento: {e}", "ERROR")
            return True

    def pause_bot_by_management(self):
        self.config["status"] = "PAUSED"
        if self.supabase: self.supabase.table("bot_config").update({"status": "PAUSED"}).eq("id", 1).execute()
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
                
                # Se conectar e estiver configurado como RUNNING, inicia sessão se não houver
                if self.config.get("status") == "RUNNING" and not self.session_start_time:
                    self.start_new_session()
                    
                return True
            else:
                self.log_to_db(f"Falha conexão: {reason}", "ERROR")
        except Exception as e:
            self.log_to_db(f"Erro critico conexão: {e}", "ERROR")
        return False

    def catalog_assets(self, assets_list):
        self.log_to_db(f"📊 Catalogando Top 3 (Classificação Adaptativa)...", "SYSTEM")
        results = []
        for asset in assets_list:
            try:
                candles = self.api.get_candles(asset, 60, 200, int(time.time()))
                if not candles or len(candles) < 100: continue
                wins, total = 0, 0
                for i in range(60, len(candles)-1):
                    subset = candles[i-60:i+1]
                    regime = MarketRegimeClassifier.classify(subset)
                    sig = None
                    
                    if regime == "TREND":
                        strength = TrendStrength.classify(subset)
                        if strength == "STRONG": sig, _ = TechnicalAnalysis.get_signal(subset)
                        else: sig, _ = MicroPullbackStrategy.get_signal(subset)
                    elif regime == "RANGE":
                        sig, _ = RangeStrategy.get_signal(subset)
                    
                    if sig:
                        total += 1
                        nxt = candles[i+1]
                        is_win = (sig == 'call' and nxt['close'] > nxt['open']) or \
                                 (sig == 'put' and nxt['close'] < nxt['open'])
                        if is_win: wins += 1
                
                if total >= 2: 
                    wr = (wins / total) * 100
                    score = (wr * 0.7) + (total * 5)
                    results.append({"pair": asset, "win_rate": wr, "wins": wins, "losses": total-wins, "best_strategy": "Adaptativa", "score": score})
            except: pass
            time.sleep(0.05)
        
        results.sort(key=lambda x: x['score'], reverse=True)
        valid_results = [r for r in results if r['win_rate'] >= 65] 
        
        top_list = []
        if valid_results:
            top_3 = valid_results[:3]
            pairs_str = ", ".join([f"{r['pair']} ({r['win_rate']:.0f}%)" for r in top_3])
            self.log_to_db(f"💎 Melhores: {pairs_str}", "SUCCESS")
            top_list = top_3
        elif results:
             top_1 = results[:1]
             wr_fb = top_1[0]['win_rate']
             if wr_fb < 60: 
                 self.log_to_db(f"⛔ Fallback abortado: WR muito baixo ({wr_fb:.1f}%)", "ERROR")
                 top_list = []
             else:
                 self.log_to_db(f"⚠️ Fallback agressivo: {top_1[0]['pair']} (WR: {wr_fb:.1f}%)", "WARNING")
                 top_list = top_1
        else:
            self.log_to_db("⚠️ Sem ativos viáveis.", "WARNING")
        
        if top_list:
            for r in top_list: self.asset_stats[r['pair']] = r
            try:
                if self.supabase:
                    self.supabase.table("cataloged_assets").delete().neq("pair", "XYZ").execute() 
                    self.supabase.table("cataloged_assets").insert(top_list).execute()
            except: pass
            return [r['pair'] for r in top_list]
        else:
            try:
                if self.supabase:
                    self.supabase.table("cataloged_assets").delete().neq("pair", "XYZ").execute() 
            except: pass
            return []

    def safe_buy(self, asset, amount, direction, type="digital"):
        result = [None]
        def target():
            try:
                if type == "digital": result[0] = self.api.buy_digital_spot(asset, amount, direction, 1)
                else: result[0] = self.api.buy(amount, asset, direction, 1)
            except: pass
        t = threading.Thread(target=target); t.daemon = True; t.start()
        t.join(timeout=10.0)
        return result[0] if result[0] else (False, None)

    # 1. ASSINATURA CORRIGIDA
    def execute_trade(self, asset, direction, strategy_key, strategy_name="Unknown"):
        last = self.last_trade_time.get(asset)
        if last and time.time() - last < 70:
            return
        self.last_trade_time[asset] = time.time()

        if not self.api: return
        try: balance_before = self.api.get_balance()
        except: return
        
        if not self.check_management(): return

        with self.trade_lock:
            if asset in self.active_trades: return
            self.active_trades.add(asset)

        amount = self.config["entry_value"]
        self.log_to_db(f"➡️ ABRINDO ({strategy_name}): {asset} | {direction.upper()} | ${amount}", "INFO")
        
        sig_id = None
        try:
            if self.supabase:
                # 2. USA NOME HUMANO PARA O BANCO
                res = self.supabase.table("trade_signals").insert({
                    "pair": asset, "direction": direction, "strategy": strategy_name,
                    "status": "PENDING", "result": "PENDING", 
                    "created_at": datetime.now(timezone.utc).isoformat(), 
                    "profit": 0
                }).execute()
                if res.data: sig_id = res.data[0]['id']
        except: pass

        status, id = self.safe_buy(asset, amount, direction, "digital")
        if not status: status, id = self.safe_buy(asset, amount, direction, "binary")

        if status:
            self.log_to_db(f"✅ Ordem {id} aceita. Aguardando (64s)...", "INFO")
            time.sleep(64)
            profit = 0.0; res_str = "PENDING"
            try:
                balance_after = self.api.get_balance()
                delta = balance_after - balance_before
                if delta > 0: res_str, profit = 'WIN', delta
                elif delta < 0: res_str, profit = 'LOSS', delta
                else: 
                    res_str = 'DOJI'
                    profit = None
            except: res_str = 'UNKNOWN'

            # 3. USA CHAVE TÉCNICA PARA PERFORMANCE
            self.update_strategy_stats(strategy_key, res_str)

            if res_str == 'DOJI':
                self.log_to_db("⚠️ DOJI ignorado (não contabilizado)", "WARNING")
                with self.trade_lock: self.active_trades.discard(asset)
                if sig_id and self.supabase:
                    try: self.supabase.table("trade_signals").delete().eq("id", sig_id).execute()
                    except: pass
                return

            if res_str == 'WIN':
                 self.consecutive_losses[asset] = 0

            if res_str == 'LOSS': 
                # Usa a chave correta para identificar RANGE
                if strategy_key == "RANGE":
                    hour = datetime.now(BR_TIMEZONE).hour
                    self.range_loss_by_hour[hour] = True
                    self.log_to_db(f"⚠️ RANGE bloqueado para a hora {hour}h devido a LOSS.", "WARNING")

                current_cons = self.consecutive_losses.get(asset, 0) + 1
                self.consecutive_losses[asset] = current_cons
                
                if current_cons == 1: cd = 60
                elif current_cons == 2: cd = 120
                else: cd = 300
                
                self.asset_cooldowns[asset] = time.time() + cd
                self.log_to_db(f"🛑 Cooldown {asset}: {cd}s (Loss #{current_cons})", "WARNING")

            log_type = "SUCCESS" if res_str == 'WIN' else "ERROR" if res_str == 'LOSS' else "WARNING"
            self.log_to_db(f"{'🏆' if res_str == 'WIN' else '🔻'} {res_str}: ${profit:.2f}", log_type)

            if sig_id and self.supabase:
                try: self.supabase.table("trade_signals").update({"status": res_str, "result": res_str, "profit": profit}).eq("id", sig_id).execute()
                except: pass
            
            self.update_balance_remote()
            self.check_management() 
            with self.trade_lock: self.active_trades.discard(asset)
        else:
            self.log_to_db("❌ Falha ordem na corretora.", "ERROR")
            with self.trade_lock: self.active_trades.discard(asset)
            if sig_id and self.supabase: 
                try: self.supabase.table("trade_signals").delete().eq("id", sig_id).execute()
                except: pass

    def start(self):
        t_watchdog = threading.Thread(target=watchdog, daemon=True)
        t_watchdog.start()
        self.check_ip()
        
        while True:
            try:
                self.fetch_config()
                if not self.connect(): time.sleep(10); continue
                
                ASSETS_POOL = [
                    "EURUSD-OTC", "EURGBP-OTC", "USDCHF-OTC", "EURJPY-OTC", "NZDUSD-OTC", "GBPUSD-OTC", 
                    "GBPJPY-OTC", "USDJPY-OTC", "AUDCAD-OTC", "AUDUSD-OTC", "USDCAD-OTC", "AUDJPY-OTC"
                ]
                
                self.best_assets = self.catalog_assets(ASSETS_POOL)
                last_scan = 0
                last_bal = 0
                last_catalog = time.time()
                last_blocked_log = 0

                while True:
                    self.fetch_config()
                    
                    if self.session_blocked:
                        if self.config["status"] == "RUNNING":
                            if time.time() - last_blocked_log > 60:
                                self.log_to_db("⛔ Sessão bloqueada por stop. Aguardando reset manual (Pause/Play)", "WARNING")
                                last_blocked_log = time.time()
                            self.pause_bot_by_management()
                        time.sleep(5)
                        continue 

                    if self.config["status"] == "RESTARTING":
                        if self.supabase: self.supabase.table("bot_config").update({"status": "RUNNING"}).eq("id", 1).execute()
                        break
                    
                    if not self.api.check_connect(): break
                    
                    catalog_interval = 900 if self.best_assets else 60
                    if time.time() - last_catalog > catalog_interval:
                        self.best_assets = self.catalog_assets(ASSETS_POOL)
                        last_catalog = time.time()

                    self.check_schedule()

                    if time.time() - last_scan > 10:
                        try:
                            self.update_balance_remote()
                            targets = self.best_assets[:3] if self.best_assets else ["EURUSD-OTC"]
                            self.log_to_db(f"MODE_ATIVO::ADAPTATIVE_REGIME_FLOW", "SYSTEM")

                            for asset in targets:
                                try:
                                    candles = self.api.get_candles(asset, 60, 100, int(time.time()))
                                    if candles:
                                        price = candles[-1]['close']
                                        cd_msg = ""
                                        if asset in self.asset_cooldowns:
                                             if time.time() < self.asset_cooldowns[asset]: cd_msg = " [COOLDOWN]"
                                        
                                        regime = MarketRegimeClassifier.classify(candles)
                                        self.log_to_db(f"ANALISE_DETALHADA::{asset}::Preço:{price:.5f}::Regime:{regime}{cd_msg}", "DEBUG")
                                        time.sleep(0.2)
                                except: pass
                        except Exception as e: self.log_to_db(f"Erro monitoramento: {e}", "WARNING")
                        last_scan = time.time()
                    
                    if time.time() - last_bal > 60: self.update_balance_remote(); last_bal = time.time()

                    if self.config["status"] == "PAUSED": time.sleep(2); continue
                    if not self.check_management(): time.sleep(5); continue

                    now_sec = datetime.now().second
                    if 55 <= now_sec <= 59:
                        if not self.best_assets:
                            self.log_to_db("⛔ Sem ativos válidos (nem fallback).", "WARNING")
                            time.sleep(2); continue

                        current_assets = self.best_assets.copy()
                        random.shuffle(current_assets)
                        trade_executed = False
                        
                        for asset in current_assets:
                            if asset in self.asset_cooldowns:
                                 if time.time() < self.asset_cooldowns[asset]: continue

                            with self.trade_lock:
                                if asset in self.active_trades: continue
                            try:
                                candles = self.api.get_candles(asset, 60, 100, int(time.time()))
                                
                                # --- LÓGICA DE REGIME ADAPTATIVO ---
                                regime = MarketRegimeClassifier.classify(candles)
                                sig = None
                                reason = ""
                                strategy_key = "UNKNOWN"
                                
                                if regime == "TREND":
                                    strength = TrendStrength.classify(candles)
                                    if strength == "STRONG":
                                        strategy_key = "TREND_STRONG"
                                        # FILTRO DE SELF-DISABLE
                                        if self.is_strategy_active("TREND_STRONG"):
                                            sig, reason = TechnicalAnalysis.get_signal(candles)
                                    else:
                                        strategy_key = "TREND_WEAK"
                                        # FILTRO DE SELF-DISABLE
                                        if self.is_strategy_active("TREND_WEAK"):
                                            sig, reason = MicroPullbackStrategy.get_signal(candles)
                                        
                                elif regime == "RANGE":
                                    strategy_key = "RANGE"
                                    # FILTRO DE SELF-DISABLE
                                    if self.is_strategy_active("RANGE"):
                                        current_hour = datetime.now(BR_TIMEZONE).hour
                                        if self.range_loss_by_hour.get(current_hour):
                                            self.log_to_db(f"⛔ RANGE bloqueado neste horário ({current_hour}h)", "DEBUG")
                                            continue

                                        if self.consecutive_losses.get(asset, 0) >= 1:
                                            self.log_to_db(f"⏸ {asset} RANGE + Loss recente. Ignorado.", "DEBUG")
                                            continue
                                        sig, reason = RangeStrategy.get_signal(candles)
                                
                                if sig: 
                                    self.log_to_db(f"🔔 SINAL EM {asset}: {sig.upper()} ({reason})", "INFO")
                                    # 4. CHAMA EXECUTE_TRADE CORRETAMENTE COM AMBOS OS PARÂMETROS
                                    self.execute_trade(asset, sig, strategy_key, reason)
                                    trade_executed = True
                                    break 
                                else:
                                     self.log_to_db(f"SCAN_ENTRADA::{asset}::{regime}::Sem Sinal", "DEBUG")

                            except: pass
                        
                        if trade_executed: time.sleep(50) 
                        else: time.sleep(4) 
                    time.sleep(0.5)
            except Exception as e:
                self.log_to_db(f"Erro loop principal: {e}", "ERROR")
                time.sleep(5)

if __name__ == "__main__":
    SimpleBot().start()
