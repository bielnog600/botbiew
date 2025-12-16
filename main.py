import sys
import time
import logging
import json
import threading
import os
import random
from datetime import datetime
from supabase import create_client, Client

# --- IMPORTAÇÃO DA EXNOVA ---
try:
    from exnovaapi.stable_api import Exnova
except ImportError:
    print("[ERRO] Biblioteca 'exnovaapi' não instalada.")

# --- CONFIGURAÇÃO SUPABASE ---
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://ioduahwknfsktujthfyc.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImlvZHVhaHdrbmZza3R1anRoZnljIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTEzMDc0NDcsImV4cCI6MjA2Njg4MzQ0N30.96f8wZO6SvABKFMWjIiw1pSugAB4Isldj7yxLcLJRSE")
EXNOVA_EMAIL = os.environ.get("EXNOVA_EMAIL", "seu_email@exemplo.com")
EXNOVA_PASSWORD = os.environ.get("EXNOVA_PASSWORD", "sua_senha")

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    print(f"[CRÍTICO] Falha ao iniciar Supabase: {e}")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
logging.getLogger("urllib3").setLevel(logging.WARNING)

# --- CLASSES AUXILIARES ---
class MoneyManager:
    def get_amount(self, asset, base_amount, martingale_factor):
        return float(base_amount)
    def register_result(self, asset, result, levels):
        pass

class TechnicalAnalysis:
    @staticmethod
    def get_signal(candles):
        if len(candles) < 3: return None
        last = candles[-1]
        if last['close'] > last['open']:
            return 'put' if random.random() > 0.6 else None
        else:
            return 'call' if random.random() > 0.6 else None

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
        self.money_manager = MoneyManager()
        self.blacklist = set()
        self.active_trades = set()
        self.config = {
            "status": "PAUSED",
            "account_type": "PRACTICE",
            "entry_value": 1.0,
            "martingale_factor": 2.0,
            "martingale_levels": 1
        }

    def log_to_db(self, message, level="INFO"):
        print(f"[{level}] {message}")
        try:
            supabase.table("logs").insert({
                "message": message,
                "level": level,
                "created_at": datetime.now().isoformat()
            }).execute()
        except: pass

    def update_balance_remote(self):
        """Lê o saldo da API e atualiza a base de dados"""
        try:
            balance = self.api.get_balance()
            supabase.table("bot_config").update({"current_balance": balance}).eq("id", 1).execute()
        except Exception as e:
            print(f"Erro ao atualizar saldo: {e}")

    def fetch_config(self):
        try:
            response = supabase.table("bot_config").select("*").eq("id", 1).execute()
            if response.data:
                data = response.data[0]
                self.config["status"] = data.get("status", "PAUSED")
                self.config["account_type"] = data.get("account_type", "PRACTICE")
                self.config["entry_value"] = float(data.get("entry_value", 1.0))
            else:
                supabase.table("bot_config").insert({"id": 1, "status": "PAUSED"}).execute()
        except: pass

    def connect(self):
        self.log_to_db(f"🔌 Conectando à Exnova...", "SYSTEM")
        try:
            if self.api and self.api.check_connect():
                self.api.api.close()
            
            self.api = Exnova(EXNOVA_EMAIL, EXNOVA_PASSWORD)
            check, reason = self.api.connect()
            
            if not check:
                self.log_to_db(f"❌ Erro ao conectar: {reason}", "ERROR")
                return False
            
            self.log_to_db("✅ Conectado com sucesso!", "SUCCESS")
            
            # Atualiza tipo de conta e saldo IMEDIATAMENTE
            self.api.change_balance(self.config["account_type"])
            self.update_balance_remote()
            
            return True
        except Exception as e:
            self.log_to_db(f"❌ Erro crítico: {e}", "ERROR")
            return False

    def execute_trade(self, asset, direction):
        amount = self.config["entry_value"]
        self.log_to_db(f"➡️ ABRINDO: {asset} | {direction.upper()} | ${amount}", "INFO")
        
        # 1. Cria sinal PENDING
        try:
            sig = supabase.table("trade_signals").insert({
                "pair": asset,
                "direction": direction,
                "strategy": "Técnica",
                "result": "PENDING",
                "created_at": datetime.now().isoformat()
            }).execute()
            sig_id = sig.data[0]['id'] if sig.data else None
        except: sig_id = None

        # 2. Envia Ordem
        id = None
        try: status, id = self.api.buy_digital_spot(asset, amount, direction, 1)
        except: status = False
        
        if not status:
            try: status, id = self.api.buy(amount, asset, direction, 1)
            except: status = False

        if status:
            self.log_to_db(f"✅ Ordem {id} aceita. Aguardando...", "INFO")
            self.active_trades.add(asset)
            time.sleep(60) 
            
            # 3. Verifica Win
            is_win = False
            profit = 0
            try:
                win_dig = self.api.check_win_digital_v2(id)
                if isinstance(win_dig, tuple) and win_dig[1] > 0: is_win, profit = True, win_dig[1]
                elif self.api.check_win_v4(id)[0] == 'win': is_win, profit = True, self.api.check_win_v4(id)[1]
            except: pass

            result_str = 'WIN' if is_win else 'LOSS'
            if is_win: self.log_to_db(f"🏆 WIN! +${profit:.2f}", "SUCCESS")
            else: self.log_to_db(f"🔻 LOSS.", "ERROR")

            # 4. Atualiza DB
            if sig_id:
                supabase.table("trade_signals").update({"result": result_str, "profit": profit}).eq("id", sig_id).execute()
            
            # Atualiza saldo após operação
            self.update_balance_remote()
            self.active_trades.discard(asset)
        else:
            self.log_to_db("❌ Falha na ordem.", "ERROR")
            if sig_id: supabase.table("trade_signals").delete().eq("id", sig_id).execute()

    def start(self):
        if not self.connect(): return
        
        ASSETS = ["EURUSD-OTC", "GBPUSD-OTC", "USDJPY-OTC", "USDCHF-OTC", "AUDCAD-OTC"]
        last_scan = 0
        last_balance_check = 0

        while True:
            try:
                self.fetch_config()
                
                # --- REINÍCIO ---
                if self.config["status"] == "RESTARTING":
                    self.log_to_db("🔄 Reiniciando...", "WARNING")
                    time.sleep(1)
                    if self.connect():
                        supabase.table("bot_config").update({"status": "RUNNING"}).eq("id", 1).execute()
                    else: time.sleep(5)
                    continue
                
                # --- CHECK CONEXÃO ---
                if not self.api.check_connect():
                    self.log_to_db("⚠️ Reconectando...", "WARNING")
                    self.connect()
                    time.sleep(5)
                    continue

                # --- SINCRONIZAÇÃO PERIÓDICA DE SALDO (1 min) ---
                if time.time() - last_balance_check > 60:
                    self.update_balance_remote()
                    last_balance_check = time.time()

                # --- HEARTBEAT ---
                if time.time() - last_scan > 5:
                    try:
                        candles = self.api.get_candles("EURUSD-OTC", 60, 1, int(time.time()))
                        price = candles[-1]['close']
                        self.log_to_db(f"ANALISE_DETALHADA::EUR/USD-OTC::Preço:{price}::RSI:--", "SYSTEM")
                    except: pass
                    last_scan = time.time()

                if self.config["status"] == "PAUSED":
                    time.sleep(2)
                    continue

                # --- OPERACIONAL ---
                if datetime.now().second <= 5:
                    for asset in ASSETS:
                        if asset in self.active_trades: continue
                        try:
                            candles = self.api.get_candles(asset, 60, 60, int(time.time()))
                            signal = TechnicalAnalysis.get_signal(candles)
                            if signal:
                                self.log_to_db(f"🔔 SINAL: {asset} -> {signal}", "INFO")
                                self.execute_trade(asset, signal)
                        except: pass
                    time.sleep(50)
                
                time.sleep(1)

            except KeyboardInterrupt: break
            except Exception as e:
                print(f"Erro Loop: {e}")
                time.sleep(5)

if __name__ == "__main__":
    SimpleBot().start()
