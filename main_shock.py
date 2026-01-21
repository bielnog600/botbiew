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

BOT_VERSION = "SHOCK_ENGINE_V12_BINARY_GALE_FIX_2026-01-21"
print(f"🚀 START::{BOT_VERSION}")

# ==============================================================================
# CONFIG GERAL
# ==============================================================================
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://ioduahwknfsktujthfyc.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
EXNOVA_EMAIL = os.environ.get("EXNOVA_EMAIL", "seu_email@exemplo.com")
EXNOVA_PASSWORD = os.environ.get("EXNOVA_PASSWORD", "sua_senha")

BR_TIMEZONE = timezone(timedelta(hours=-3))

# ✅ SEGUNDO DE ENTRADA (padrão 50s)
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
                    # Engolfo simplificado
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
                    # Engolfo simplificado
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

        explosive = (body_live >= avg_body * body_mult) and (range_live >= avg_range * range_mult)
        if not explosive:
            return None, "Sem explosão", debug

        if live["color"] == "green":
            if close_pos >= 0.85 and pullback_ratio <= 0.25:
                return "put", "SHOCK_LIVE_UP", debug
            return None, "Explodiu mas não travou no topo", debug

        if live["color"] == "red":
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


# ==============================================================================
# BOT
# ==============================================================================

class SimpleBot:
    def __init__(self):
        self.api = None
        self.supabase = None

        self.trade_lock = threading.RLock()
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

        self.last_trade_time = {}
        self.last_minute_trade = {}
        self.session_blocked = False

        self.block_until_ts = 0
        self.loss_streak = 0
        
        self.pending_gale = {}

        self.strategy_performance = {
            "TREND_STRONG": {'wins': 0, 'losses': 0, 'consecutive_losses': 0, 'active': True},
            "TREND_WEAK": {'wins': 0, 'losses': 0, 'consecutive_losses': 0, 'active': True},
            "SHOCK_REVERSAL": {'wins': 0, 'losses': 0, 'consecutive_losses': 0, 'active': True},
            "TENDMAX": {'wins': 0, 'losses': 0, 'consecutive_losses': 0, 'active': True},
            "RANGE": {'wins': 0, 'losses': 0, 'consecutive_losses': 0, 'active': False}
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

    def log_to_db(self, message, level="INFO"):
        global LAST_LOG_TIME
        LAST_LOG_TIME = time.time()
        print(f"[{level}] {message}")
        if level == "DEBUG":
            return
        if not self.supabase:
            return
        try:
            self.supabase.table("logs").insert(
                {
                    "message": message,
                    "level": level,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            ).execute()
        except:
            pass

    def insert_signal(self, asset, direction, strategy_name):
        # ✅ FIX: Removido 'amount' para evitar erro de schema no Supabase
        if not self.supabase:
            return None
        try:
            res = self.supabase.table("trade_signals").insert(
                {
                    "pair": asset,
                    "direction": direction,
                    "strategy": strategy_name,
                    "status": "PENDING",
                    "result": "PENDING",
                    "profit": 0,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    # "amount": amount,  <-- REMOVIDO PARA SEGURANÇA DO FRONT
                }
            ).execute()
            if res.data:
                return res.data[0].get("id")
        except:
            pass
        return None

    def update_signal(self, signal_id, status, result, profit):
        if not self.supabase or not signal_id:
            return
        try:
            self.supabase.table("trade_signals").update(
                {
                    "status": status,
                    "result": result,
                    "profit": profit,
                }
            ).eq("id", signal_id).execute()
        except:
            pass

    def connect(self):
        self.log_to_db("🔌 Conectando...", "SYSTEM")
        try:
            if self.api:
                try:
                    self.api.api.close()
                except:
                    pass

            self.api = Exnova(EXNOVA_EMAIL, EXNOVA_PASSWORD)
            ok, reason = self.api.connect()
            if ok:
                self.log_to_db("✅ Conectado!", "SUCCESS")
                self.api.change_balance(self.config["account_type"])
                self.update_balance_remote()
                return True
            else:
                self.log_to_db(f"❌ Falha conexão: {reason}", "ERROR")
        except Exception as e:
            self.log_to_db(f"❌ Erro crítico conexão: {e}", "ERROR")
        return False

    def update_balance_remote(self):
        if not self.api or not self.supabase: return
        try:
            balance = self.api.get_balance()
            self.supabase.table("bot_config").update({"current_balance": balance}).eq("id", 1).execute()
        except: pass

    def fetch_config(self):
        if not self.supabase:
            self.init_supabase()
            return
        try:
            res = self.supabase.table("bot_config").select("*").eq("id", 1).execute()
            if not res.data:
                self.supabase.table("bot_config").insert({"id": 1, "status": "PAUSED"}).execute()
                return

            data = res.data[0]

            new_status = (data.get("status") or "PAUSED").strip().upper()
            new_mode = (data.get("mode") or "LIVE").strip().upper()

            db_raw_strat = data.get("strategy_mode")
            db_strat = (str(db_raw_strat) or "AUTO").strip().upper().replace(" ", "_")

            if "SHOCK" in db_strat:
                strat = "SHOCK_REVERSAL"
            elif "TENDMAX" in db_strat:
                strat = "TENDMAX"
            elif "V2" in db_strat or "EMA" in db_strat or "AGGRESSIVE" in db_strat:
                strat = "V2_TREND"
            elif "AUTO" in db_strat:
                strat = "AUTO"
            else:
                strat = "AUTO"

            self.config.update(
                {
                    "status": new_status,
                    "mode": new_mode,
                    "strategy_mode": strat,
                    "account_type": (data.get("account_type") or "PRACTICE").strip().upper(),
                    "entry_value": float(data.get("entry_value") or 1.0),
                    "max_trades_per_day": int(data.get("max_trades_per_day") or 0),
                    "max_wins_per_day": int(data.get("max_wins_per_day") or 0),
                    "max_losses_per_day": int(data.get("max_losses_per_day") or 0),
                    "timer_enabled": bool(data.get("timer_enabled")),
                    "timer_start": str(data.get("timer_start") or "00:00"),
                    "timer_end": str(data.get("timer_end") or "00:00"),
                }
            )
        except Exception as e:
            self.log_to_db(f"❌ Erro fetch_config: {e}", "ERROR")

    def check_schedule(self):
        if not self.config.get("timer_enabled", False):
            return

        now_br = datetime.now(BR_TIMEZONE)
        now_str = now_br.strftime("%H:%M")
        start_str = self.config.get("timer_start", "00:00")
        end_str = self.config.get("timer_end", "00:00")

        hour = now_br.hour
        minute = now_br.minute
        if 0 <= hour < 4:
            return
        if hour == 13 and minute >= 30:
            return
        if hour == 14 and minute <= 30:
            return

        is_inside = False
        if start_str < end_str:
            is_inside = start_str <= now_str < end_str
        else:
            is_inside = now_str >= start_str or now_str < end_str

        if is_inside and self.config["status"] == "PAUSED":
            self.log_to_db(f"⏰ Agendador: RUNNING ({start_str}-{end_str})", "SYSTEM")
            try:
                self.supabase.table("bot_config").update({"status": "RUNNING"}).eq("id", 1).execute()
            except:
                pass

        if (not is_inside) and self.config["status"] == "RUNNING":
            self.log_to_db("⏰ Agendador: PAUSED (fim)", "SYSTEM")
            try:
                self.supabase.table("bot_config").update({"status": "PAUSED"}).eq("id", 1).execute()
            except:
                pass

    def reset_daily_if_needed(self):
        today = datetime.now(BR_TIMEZONE).date()
        if today != self.current_date:
            self.current_date = today
            self.daily_wins = 0
            self.daily_losses = 0
            self.daily_total = 0
            self.loss_streak = 0
            self.session_blocked = False
            self.block_until_ts = 0
            self.pending_gale = {} 
            self.log_to_db("🚀 Nova sessão diária", "SYSTEM")

    def check_daily_limits(self):
        if self.config["mode"] == "OBSERVE":
            return True

        if self.config["max_trades_per_day"] > 0 and self.daily_total >= self.config["max_trades_per_day"]:
            self.log_to_db(f"🛑 Limite trades ({self.daily_total})", "WARNING")
            return False
        if self.config["max_wins_per_day"] > 0 and self.daily_wins >= self.config["max_wins_per_day"]:
            self.log_to_db(f"🏆 Meta wins ({self.daily_wins})", "SUCCESS")
            return False
        if self.config["max_losses_per_day"] > 0 and self.daily_losses >= self.config["max_losses_per_day"]:
            self.log_to_db(f"❌ Limite losses ({self.daily_losses})", "ERROR")
            return False
        return True

    # ✅ FIX 4: Função Única e Exclusiva para Compra (BINÁRIA SOMENTE)
    def safe_buy(self, asset, amount, direction):
        if self.config["mode"] == "OBSERVE":
            return True, "VIRTUAL", "OBSERVE"

        # Tenta SOMENTE Binária (API buy)
        try:
            status, trade_id = self.api.buy(amount, asset, direction, 1)
            # Verifica se realmente veio ID (API às vezes devolve True sem ID)
            if status and trade_id:
                return True, trade_id, "BINARY"
            else:
                # Logar falha silenciosa se status=True mas ID=None
                self.log_to_db(f"⚠️ Binária falhou (ID nulo).", "WARNING")
        except Exception as e:
            self.log_to_db(f"⚠️ BINARY Exception: {e}", "WARNING")

        # Se falhar, retorna False. NADA DE DIGITAL.
        return False, None, "FAILED"

    def execute_trade(self, asset, direction, strategy_key, strategy_label, gale_level=0):
        # anti duplicação por asset (G0)
        now = time.time()
        if gale_level == 0:
            if asset in self.last_trade_time and now - self.last_trade_time[asset] < 60:
                return
            self.last_trade_time[asset] = now

            minute_key = datetime.now(BR_TIMEZONE).strftime("%Y%m%d%H%M")
            if self.last_minute_trade.get(asset) == minute_key:
                return
            self.last_minute_trade[asset] = minute_key

        if time.time() < self.block_until_ts:
            self.log_to_db(f"⏳ Bloqueado 15min (anti-chop). Ignorando {asset}", "DEBUG")
            return

        with self.trade_lock:
            # G1 pode "re-entrar" no lock (RLock), G0 novo não
            if gale_level == 0 and asset in self.active_trades:
                return
            self.active_trades.add(asset)

        signal_id = None
        base_amount = float(self.config["entry_value"])
        
        # ✅ FIX 2: Cálculo Martingale Escalável
        amount = base_amount
        if gale_level > 0:
            multiplier = self.config.get("martingale_multiplier", 2.0)
            amount = round(base_amount * (multiplier ** gale_level), 2)

        try:
            if not self.check_daily_limits():
                self.session_blocked = True
                self.log_to_db("⛔ Limite diário atingido. Pausando.", "WARNING")
                try:
                    self.supabase.table("bot_config").update({"status": "PAUSED"}).eq("id", 1).execute()
                except:
                    pass
                return

            tag_gale = f"::G{gale_level}"
            strategy_name = f"{strategy_key}::{strategy_label}{tag_gale}"
            
            # ✅ FIX 3: Insert sem 'amount'
            signal_id = self.insert_signal(asset, direction, strategy_name)

            self.log_to_db(
                f"🟡 TENTANDO ENTRAR (BINARIA) {strategy_key} [G{gale_level}]: {asset} | {direction.upper()} | ${amount}",
                "INFO",
            )

            balance_before = 0.0
            if self.config["mode"] == "LIVE":
                try:
                    balance_before = self.api.get_balance()
                    if balance_before <= 0:
                        self.log_to_db("❌ Saldo inválido", "ERROR")
                        return
                except:
                    return

            # ✅ FIX 4: Compra segura (Binária Only)
            status, trade_id, order_type = self.safe_buy(asset, amount, direction)
            
            if not status or not trade_id:
                self.log_to_db(f"❌ ORDEM RECUSADA: {asset} (Binária)", "ERROR")
                self.update_signal(signal_id, "FAILED", "FAILED", 0)
                return

            self.log_to_db(f"✅ CONFIRMADA: Ordem {trade_id} ({order_type}). Aguardando...", "INFO")

            # ✅ Wait Time
            time.sleep(70)

            # Resultado
            res_str = "UNKNOWN"
            profit = 0.0

            if self.config["mode"] == "OBSERVE":
                try:
                    candles = self.api.get_candles(asset, 60, 2, int(time.time()))
                    last_closed = candles[-2]
                    is_win = (direction == "call" and last_closed["close"] > last_closed["open"]) or (
                        direction == "put" and last_closed["close"] < last_closed["open"]
                    )
                    if is_win:
                        res_str = "WIN"
                        profit = amount * 0.87
                    else:
                        if abs(last_closed["close"] - last_closed["open"]) < 1e-9:
                            res_str = "DOJI"
                            profit = 0.0
                        else:
                            res_str = "LOSS"
                            profit = -amount
                except:
                    res_str = "UNKNOWN"
            else:
                try:
                    balance_after = self.api.get_balance()
                    delta = balance_after - balance_before
                    if delta > 0.01:
                        res_str = "WIN"
                        profit = delta
                    elif delta < -0.01:
                        res_str = "LOSS"
                        profit = delta
                    else:
                        res_str = "DOJI"
                        profit = 0.0
                except:
                    res_str = "UNKNOWN"

            if res_str == "UNKNOWN":
                 self.log_to_db("⚠️ Resultado UNKNOWN, reconectando API...", "WARNING")
                 self.api = None
                 return

            if res_str == "DOJI":
                self.log_to_db("⚪ DOJI (ignorado)", "DEBUG")
                self.update_signal(signal_id, "DOJI", "DOJI", 0)
                return

            # Contadores
            self.daily_total += 1
            if res_str == "WIN":
                self.daily_wins += 1
                self.loss_streak = 0
                if asset in self.pending_gale:
                    del self.pending_gale[asset]
                    
            elif res_str == "LOSS":
                self.daily_losses += 1
                self.loss_streak += 1
                
                # ✅ FIX 1: Martingale Assíncrono (Arma G1 na fila)
                if gale_level == 0 and self.config.get("martingale_enabled", True):
                    self.log_to_db(f"🎯 GALE G1 ARMADO para {asset} (Próximo minuto)", "WARNING")
                    self.pending_gale[asset] = {
                        'asset': asset,
                        'direction': direction,
                        'strategy_key': strategy_key,
                        'strategy_label': strategy_label,
                        # 'prefer_binary' removido pois agora é padrão
                        'execute_at': time.time() 
                    }

            if self.loss_streak >= 2:
                self.block_until_ts = time.time() + 900
                self.log_to_db("🛑 2 LOSSES SEGUIDOS — PAUSANDO 15 MIN (ANTI-CHOP)", "WARNING")
                self.pending_gale = {} # Limpa gales se bloqueado

            self.update_signal(signal_id, res_str, res_str, profit)

            log_type = "SUCCESS" if res_str == "WIN" else "ERROR"
            self.log_to_db(
                f"{'🏆' if res_str == 'WIN' else '🔻'} {res_str} [G{gale_level}]: {profit:.2f} ({self.daily_wins}W/{self.daily_losses}L)",
                log_type,
            )
            
            if self.config["mode"] == "LIVE":
                self.update_balance_remote()

            if not self.check_daily_limits():
                self.log_to_db("🛑 Limite diário atingido — PAUSANDO", "WARNING")
                self.session_blocked = True
                try:
                    self.supabase.table("bot_config").update({"status": "PAUSED"}).eq("id", 1).execute()
                except:
                    pass

        finally:
            with self.trade_lock:
                self.active_trades.discard(asset)

    def catalog_assets(self, assets_pool):
        strat = self.config.get("strategy_mode", "AUTO")
        if strat in ["SHOCK_REVERSAL", "TENDMAX"]:
            self.log_to_db("🔥 Modo SHOCK/TENDMAX: usando TODOS os ativos", "SYSTEM")
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
                self.reset_daily_if_needed()
                self.fetch_config()
                self.check_schedule()

                if self.config["status"] == "PAUSED":
                    time.sleep(2)
                    continue

                if time.time() < self.block_until_ts:
                    time.sleep(2)
                    continue

                if not self.api or not self.api.check_connect():
                    if not self.connect():
                        time.sleep(5)
                        continue
                
                # ✅ EXECUÇÃO MARTINGALE PRIORITÁRIA (G1)
                if self.pending_gale:
                    assets_gale = list(self.pending_gale.keys())
                    for asset in assets_gale:
                        gale_info = self.pending_gale[asset]
                        del self.pending_gale[asset]
                        
                        self.log_to_db(f"🚀 EXECUTANDO GALE G1: {asset}", "INFO")
                        self.execute_trade(
                            asset=gale_info['asset'],
                            direction=gale_info['direction'],
                            strategy_key=gale_info['strategy_key'],
                            strategy_label=gale_info['strategy_label'],
                            gale_level=1
                        )
                    time.sleep(1)
                    continue

                if not self.best_assets or (time.time() - self.last_catalog_time > 900):
                    self.best_assets = self.catalog_assets(assets_pool)
                    self.last_catalog_time = time.time()

                now_dt = datetime.now(BR_TIMEZONE)
                now_sec = now_dt.second
                strat_mode = self.config.get("strategy_mode", "AUTO")

                if now_sec in [0, 10, 20, 30, 40, 50]:
                    self.log_to_db(f"MODE_ATIVO::{strat_mode}::{now_dt.strftime('%H:%M:%S')}::ENTRY={ENTRY_SECOND}s", "DEBUG")

                # ✅ FIX 5: JANELA DE ENTRADA CORRIGIDA (ENTRY_SECOND + 2s)
                if ENTRY_SECOND <= now_sec <= ENTRY_SECOND + 2:
                    if strat_mode in ["AUTO", "SHOCK_REVERSAL"]:
                        random_assets = self.best_assets.copy()
                        random.shuffle(random_assets)

                        for asset in random_assets:
                            with self.trade_lock:
                                if asset in self.active_trades:
                                    continue
                            try:
                                candles = self.api.get_candles(asset, 60, 100, int(time.time()))
                                if not candles:
                                    continue

                                sig, reason, dbg = ShockLiveDetector.detect(candles, asset)

                                if strat_mode == "SHOCK_REVERSAL":
                                    self.log_to_db(f"⚡ SHOCK_LIVE_CHECK {asset}: {reason}", "DEBUG")

                                if sig:
                                    self.execute_trade(
                                        asset=asset,
                                        direction=sig,
                                        strategy_key="SHOCK_REVERSAL",
                                        strategy_label=reason,
                                        gale_level=0
                                    )
                                    break
                            except:
                                pass

                # ✅ V2 TREND + TENDMAX (55-59s)
                if 55 <= now_sec <= 59:
                    
                    if strat_mode in ["AUTO", "TENDMAX"]:
                        trade_executed = False
                        random_assets = self.best_assets.copy()
                        random.shuffle(random_assets)

                        for asset in random_assets:
                            with self.trade_lock:
                                if asset in self.active_trades: continue
                            try:
                                candles = self.api.get_candles(asset, 60, 100, int(time.time()))
                                if not candles: continue

                                sig_tm, reason_tm = TendMaxStrategy.get_signal(candles)
                                if strat_mode == "TENDMAX":
                                    self.log_to_db(f"📈 TENDMAX_CHECK {asset}: {reason_tm}", "DEBUG")

                                if sig_tm:
                                    self.execute_trade(asset, sig_tm, "TENDMAX", reason_tm, gale_level=0)
                                    trade_executed = True
                                    break
                            except: pass
                        
                        if trade_executed:
                            time.sleep(1)
                            continue

                    if strat_mode in ["AUTO", "V2_TREND"]:
                        assets_to_scan = self.best_assets if self.best_assets else assets_pool
                        random.shuffle(assets_to_scan)

                        for asset in assets_to_scan:
                            with self.trade_lock:
                                if asset in self.active_trades:
                                    continue
                            try:
                                candles = self.api.get_candles(asset, 60, 100, int(time.time()))
                                if not candles:
                                    continue

                                if TechnicalAnalysis.check_compression(candles):
                                    continue

                                sig, reason = TechnicalAnalysis.get_signal_v2(candles)
                                if sig:
                                    self.execute_trade(
                                        asset=asset,
                                        direction=sig,
                                        strategy_key="V2_TREND",
                                        strategy_label=reason,
                                        gale_level=0
                                    )
                                    break
                            except:
                                pass

                time.sleep(0.25)

            except Exception as e:
                self.log_to_db(f"Erro loop principal: {e}", "ERROR")
                time.sleep(3)


if __name__ == "__main__":
    SimpleBot().start()
