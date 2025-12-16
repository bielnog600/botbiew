import sys
import time
import logging
import json
import threading
import os
import random
from datetime import datetime, timedelta
from supabase import create_client, Client

# --- IMPORTAÇÃO DA EXNOVA ---
try:
    from exnovaapi.stable_api import Exnova
except ImportError:
    print("[ERRO] Biblioteca 'exnovaapi' não instalada.")

# --- CONFIGURAÇÃO ---
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://ioduahwknfsktujthfyc.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImlvZHVhaHdrbmZza3R1anRoZnljIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTEzMDc0NDcsImV4cCI6MjA2Njg4MzQ0N30.96f8wZO6SvABKFMWjIiw1pSugAB4Isldj7yxLcLJRSE")
EXNOVA_EMAIL = os.environ.get("EXNOVA_EMAIL", "seu_email@exemplo.com")
EXNOVA_PASSWORD = os.environ.get("EXNOVA_PASSWORD", "sua_senha")

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
logging.getLogger("urllib3").setLevel(logging.WARNING)

# --- CLASSES AUXILIARES ---
class MoneyManager:
    def get_amount(self, asset, base_amount, martingale_factor):
        return float(base_amount)

class TechnicalAnalysis:
    @staticmethod
    def calculate_sma(candles, period):
        if len(candles) < period: return 0
        slice_candles = candles[-period:]
        total_close = sum([c['close'] for c in slice_candles])
        return total_close / period

    @staticmethod
    def get_signal(candles):
        if len(candles) < 25: return None
        sma_20 = TechnicalAnalysis.calculate_sma(candles, 20) # SMA 20 para tendência
        if sma_20 == 0: return None
        last_candle = candles[-1]
        
        # Estratégia: A favor da tendência
        if last_candle['close'] > sma_20:
            if last_candle['close'] > last_candle['open']: return 'call' # Tendencia Alta + Vela Verde
        elif last_candle['close'] < sma_20:
            if last_candle['close'] < last_candle['open']: return 'put' # Tendencia Baixa + Vela Vermelha
        return None

# --- CORREÇÕES OTC ---
try:
    def update_consts():
        import exnovaapi.constants as OP_code
        OTC_MAP = {
            "EURUSD-OTC": 76, "GBPUSD-OTC": 81, "USDJPY-OTC": 85, "EURJPY-OTC": 79,
            "USDCHF-OTC": 78, "AUDCAD-OTC": 86, "NZDUSD-OTC": 80, "EURGBP-OTC": 77,
            "AUDUSD-OTC": 2111, "USDCAD-OTC": 2112, "USDMXN-OTC": 1548, 
            "FWONA-OTC": 2169, "XNGUSD-OTC": 2170, "AUDJPY-OTC": 2113, 
            "GBPCAD-OTC": 2114, "GBPCHF-OTC": 2115, "GBPAUD-OTC": 2116, "EURCAD-OTC": 2117
        }
        OP_code.ACTIVES.update(OTC_MAP)
    update_consts()
except: pass

# --- BOT PRINCIPAL ---
class SimpleBot:
    def __init__(self):
        self.api = None
        self.supabase = None
        self.money_manager = MoneyManager()
        self.blacklist = set()
        self.active_trades = set()
        self.active_account_type = None 
        self.config = {
            "status": "PAUSED",
            "account_type": "PRACTICE",
            "entry_value": 1.0,
            "martingale_factor": 2.0,
            "martingale_levels": 1
        }
        self.init_supabase()

    def init_supabase(self):
        try:
            self.supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
            print("✅ Supabase conectado.")
        except Exception as e:
            print(f"❌ Erro Supabase: {e}")

    def log_to_db(self, message, level="INFO"):
        print(f"[{level}] {message}")
        if not self.supabase: return
        try:
            self.supabase.table("logs").insert({
                "message": message,
                "level": level,
                "created_at": datetime.now().isoformat()
            }).execute()
        except: 
            try: self.supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
            except: pass

    def update_balance_remote(self):
        if not self.api: return
        try:
            balance = self.api.get_balance()
            self.supabase.table("bot_config").update({"current_balance": balance}).eq("id", 1).execute()
        except: pass

    def fetch_config(self):
        if not self.supabase: self.init_supabase()
        try:
            response = self.supabase.table("bot_config").select("*").eq("id", 1).execute()
            if response.data:
                data = response.data[0]
                self.config["status"] = data.get("status", "PAUSED")
                acc_type = data.get("account_type", "PRACTICE").strip().upper()
                self.config["account_type"] = acc_type
                self.config["entry_value"] = float(data.get("entry_value", 1.0))
            else:
                self.supabase.table("bot_config").insert({"id": 1, "status": "PAUSED"}).execute()
        except Exception as e:
            print(f"Erro config: {e}")

    def connect(self):
        self.log_to_db(f"🔌 A conectar à Exnova...", "SYSTEM")
        try:
            if self.api:
                try: self.api.api.close()
                except: pass
                self.api = None
            
            self.api = Exnova(EXNOVA_EMAIL, EXNOVA_PASSWORD)
            check, reason = self.api.connect()
            
            if not check:
                self.log_to_db(f"❌ Erro ao conectar: {reason}", "ERROR")
                return False
            
            self.log_to_db("✅ Conectado com sucesso!", "SUCCESS")
            
            target_account = self.config["account_type"]
            self.api.change_balance(target_account)
            self.active_account_type = target_account
            
            self.log_to_db(f"💳 Conta definida para: {target_account}", "SYSTEM")
            self.update_balance_remote()
            return True
        except Exception as e:
            self.log_to_db(f"❌ Erro crítico connect: {e}", "ERROR")
            return False

    def safe_buy(self, asset, amount, direction, type="digital"):
        result = [None]
        def target():
            try:
                if type == "digital":
                    result[0] = self.api.buy_digital_spot(asset, amount, direction, 1)
                else:
                    result[0] = self.api.buy(amount, asset, direction, 1)
            except: pass

        t = threading.Thread(target=target)
        t.daemon = True
        t.start()
        t.join(timeout=10.0)
        
        if t.is_alive():
            self.log_to_db(f"⚠️ Timeout ao enviar ordem para {asset}", "WARNING")
            return False, None
        
        return result[0] if result[0] else (False, None)

    def execute_trade(self, asset, direction):
        if not self.api: return
        amount = self.config["entry_value"]
        self.log_to_db(f"➡️ ABRINDO: {asset} | {direction.upper()} | ${amount}", "INFO")
        
        # 1. Sinal PENDING na coluna STATUS
        sig_id = None
        try:
            sig_data = {
                "pair": asset,
                "direction": direction,
                "strategy": "Micro Tendência",
                "status": "PENDING", # Força nome da coluna status
                "created_at": datetime.now().isoformat()
            }
            sig = self.supabase.table("trade_signals").insert(sig_data).execute()
            if sig.data and len(sig.data) > 0:
                sig_id = sig.data[0]['id']
        except Exception as e:
            self.log_to_db(f"Erro DB (Insert): {e}", "WARNING")

        # 2. Ordem
        status, id = self.safe_buy(asset, amount, direction, "digital")
        if not status: status, id = self.safe_buy(asset, amount, direction, "binary")

        if status:
            self.log_to_db(f"✅ Ordem {id} aceite.", "INFO")
            self.active_trades.add(asset)
            time.sleep(60) 
            
            # 3. Resultado
            is_win = False
            profit = 0.0
            try:
                win_dig = self.api.check_win_digital_v2(id)
                if isinstance(win_dig, tuple) and win_dig[1] > 0: 
                    is_win, profit = True, float(win_dig[1])
                elif isinstance(win_dig, (int, float)) and win_dig > 0:
                    is_win, profit = True, float(win_dig)
                elif self.api.check_win_v4(id)[0] == 'win': 
                    is_win, profit = True, float(self.api.check_win_v4(id)[1])
            except: pass

            result_str = 'WIN' if is_win else 'LOSS'
            if not is_win: profit = -float(amount)

            if is_win: self.log_to_db(f"🏆 WIN! +${profit:.2f}", "SUCCESS")
            else: self.log_to_db(f"🔻 LOSS. ${profit:.2f}", "ERROR")

            # 4. Atualiza DB na coluna STATUS
            updated = False
            if sig_id:
                try: 
                    # Atualiza STATUS e PROFIT
                    self.supabase.table("trade_signals").update({"status": result_str, "profit": profit}).eq("id", sig_id).execute()
                    updated = True
                except Exception as e:
                    self.log_to_db(f"Erro DB (Update ID): {e}", "ERROR")
            
            if not updated:
                try:
                    # Fallback usando par e status PENDING
                    recent = self.supabase.table("trade_signals").select("id")\
                        .eq("pair", asset).eq("status", "PENDING")\
                        .order("created_at", desc=True).limit(1).execute()
                    
                    if recent.data:
                        rec_id = recent.data[0]['id']
                        self.supabase.table("trade_signals").update({"status": result_str, "profit": profit}).eq("id", rec_id).execute()
                        self.log_to_db("Sinal atualizado via Fallback.", "SUCCESS")
                except Exception as e:
                    self.log_to_db(f"Erro DB (Update Fallback): {e}", "ERROR")
            
            self.update_balance_remote()
            self.active_trades.discard(asset)
        else:
            self.log_to_db("❌ Falha na ordem.", "ERROR")
            if sig_id:
                try: self.supabase.table("trade_signals").delete().eq("id", sig_id).execute()
                except: pass

    def start(self):
        self.fetch_config()
        self.log_to_db(f"Configuração carregada: Conta {self.config['account_type']}", "SYSTEM")

        while True:
            try:
                if not self.connect():
                    time.sleep(10)
                    continue
                
                ASSETS = ["EURUSD-OTC", "GBPUSD-OTC", "USDJPY-OTC", "USDCHF-OTC", "AUDCAD-OTC"]
                last_scan = 0
                last_bal = 0

                while True:
                    self.fetch_config()
                    
                    if self.config["account_type"] != self.active_account_type:
                        self.log_to_db(f"🔄 Trocando conta para {self.config['account_type']}...", "SYSTEM")
                        self.api.change_balance(self.config["account_type"])
                        self.active_account_type = self.config["account_type"]
                        self.update_balance_remote()

                    if self.config["status"] == "RESTARTING":
                        self.log_to_db("🔄 Reiniciando...", "WARNING")
                        self.supabase.table("bot_config").update({"status": "RUNNING"}).eq("id", 1).execute()
                        break 

                    if not self.api.check_connect():
                        self.log_to_db("⚠️ Reconectando...", "WARNING")
                        break 

                    if time.time() - last_scan > 5:
                        try:
                            candles = self.api.get_candles("EURUSD-OTC", 60, 25, int(time.time()))
                            if candles:
                                price = candles[-1]['close']
                                self.log_to_db(f"ANALISE_DETALHADA::EUR/USD-OTC::Preço:{price}::RSI:--", "SYSTEM")
                        except: pass
                        last_scan = time.time()

                    if time.time() - last_bal > 60:
                        self.update_balance_remote()
                        last_bal = time.time()

                    if self.config["status"] == "PAUSED":
                        time.sleep(2)
                        continue

                    if datetime.now().second <= 5:
                        for asset in ASSETS:
                            if asset in self.active_trades: continue
                            try:
                                candles = self.api.get_candles(asset, 60, 30, int(time.time()))
                                signal = TechnicalAnalysis.get_signal(candles)
                                if signal:
                                    self.log_to_db(f"🔔 SINAL: {asset} -> {signal.upper()}", "INFO")
                                    self.execute_trade(asset, signal)
                            except: pass
                        time.sleep(50)
                    
                    time.sleep(1)

            except Exception as e:
                print(f"Crash: {e}")
                time.sleep(10)

if __name__ == "__main__":
    while True:
        try:
            bot = SimpleBot()
            bot.start()
        except Exception as e:
            print(f"Reinício forçado: {e}")
            time.sleep(5)
