import sys
import time
import logging
import json
import threading
import os
import random
from datetime import datetime, timedelta
from supabase import create_client, Client

try:
    from exnovaapi.stable_api import Exnova
except ImportError:
    print("[ERRO] Biblioteca 'exnovaapi' não instalada.")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://ioduahwknfsktujthfyc.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImlvZHVhaHdrbmZza3R1anRoZnljIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTEzMDc0NDcsImV4cCI6MjA2Njg4MzQ0N30.96f8wZO6SvABKFMWjIiw1pSugAB4Isldj7yxLcLJRSE")
EXNOVA_EMAIL = os.environ.get("EXNOVA_EMAIL", "seu_email@exemplo.com")
EXNOVA_PASSWORD = os.environ.get("EXNOVA_PASSWORD", "sua_senha")

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
logging.getLogger("urllib3").setLevel(logging.WARNING)

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
        if len(candles) < 15: return None
        sma = TechnicalAnalysis.calculate_sma(candles, 9) # SMA 9
        if sma == 0: return None
        last = candles[-1]
        
        # Filtro de Pavio (Rejeição)
        body = abs(last['close'] - last['open'])
        upper_wick = last['max'] - max(last['close'], last['open'])
        lower_wick = min(last['close'], last['open']) - last['min']
        
        if last['close'] > sma: # Tendência Alta
            if last['close'] > last['open'] and upper_wick < body * 2: return 'call'
        elif last['close'] < sma: # Tendência Baixa
            if last['close'] < last['open'] and lower_wick < body * 2: return 'put'
        return None

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

class SimpleBot:
    def __init__(self):
        self.api = None
        self.supabase = None
        self.active_trades = set()
        self.config = { "status": "PAUSED", "account_type": "PRACTICE", "entry_value": 1.0 }
        self.init_supabase()

    def init_supabase(self):
        try: self.supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        except: pass

    def log_to_db(self, message, level="INFO"):
        print(f"[{level}] {message}")
        if not self.supabase: return
        try: self.supabase.table("logs").insert({"message": message, "level": level, "created_at": datetime.now().isoformat()}).execute()
        except: pass

    def fetch_config(self):
        try:
            res = self.supabase.table("bot_config").select("*").eq("id", 1).execute()
            if res.data:
                self.config["status"] = res.data[0].get("status", "PAUSED")
                self.config["account_type"] = res.data[0].get("account_type", "PRACTICE").strip().upper()
                self.config["entry_value"] = float(res.data[0].get("entry_value", 1.0))
            else:
                self.supabase.table("bot_config").insert({"id": 1, "status": "PAUSED"}).execute()
        except: pass

    def connect(self):
        self.log_to_db("🔌 Conectando...", "SYSTEM")
        try:
            if self.api: 
                try: self.api.api.close() 
                except: pass
            self.api = Exnova(EXNOVA_EMAIL, EXNOVA_PASSWORD)
            if self.api.connect()[0]:
                self.log_to_db("✅ Conectado!", "SUCCESS")
                self.api.change_balance(self.config["account_type"])
                return True
        except: pass
        return False

    def execute_trade(self, asset, direction):
        if not self.api: return
        amount = self.config["entry_value"]
        self.log_to_db(f"➡️ ABRINDO: {asset} | {direction} | ${amount}", "INFO")
        
        # 1. Cria Sinal (PENDING) - Escreve em AMBAS as colunas para garantir
        sig_id = None
        try:
            res = self.supabase.table("trade_signals").insert({
                "pair": asset,
                "direction": direction,
                "strategy": "Nano SMA9",
                "status": "PENDING", # Escreve aqui
                "result": "PENDING", # E aqui também
                "created_at": datetime.now().isoformat()
            }).execute()
            if res.data: sig_id = res.data[0]['id']
        except: pass

        # 2. Ordem
        status, id = False, None
        try: status, id = self.api.buy_digital_spot(asset, amount, direction, 1)
        except: pass
        if not status:
            try: status, id = self.api.buy(amount, asset, direction, 1)
            except: pass

        if status:
            self.log_to_db(f"✅ Ordem {id} aceita.", "INFO")
            self.active_trades.add(asset)
            time.sleep(60) 
            
            # 3. Check Win
            is_win, profit = False, 0.0
            try:
                win_v = self.api.check_win_digital_v2(id)
                if isinstance(win_v, tuple) and win_v[1] > 0: is_win, profit = True, float(win_v[1])
                elif isinstance(win_v, (int, float)) and win_v > 0: is_win, profit = True, float(win_v)
                elif self.api.check_win_v4(id)[0] == 'win': is_win, profit = True, float(self.api.check_win_v4(id)[1])
            except: pass

            res_str = 'WIN' if is_win else 'LOSS'
            if not is_win: profit = -float(amount)

            self.log_to_db(f"{'🏆' if is_win else '🔻'} {res_str}: ${profit:.2f}", "SUCCESS" if is_win else "ERROR")

            # 4. Atualiza DB (Tenta atualizar tanto 'status' quanto 'result')
            if sig_id:
                try: 
                    self.supabase.table("trade_signals").update({
                        "status": res_str, 
                        "result": res_str, 
                        "profit": profit
                    }).eq("id", sig_id).execute()
                except Exception as e:
                    self.log_to_db(f"Erro update DB: {e}", "WARNING")
            
            # Atualiza saldo
            try:
                bal = self.api.get_balance()
                self.supabase.table("bot_config").update({"current_balance": bal}).eq("id", 1).execute()
            except: pass
            
            self.active_trades.discard(asset)
        else:
            self.log_to_db("❌ Falha ordem.", "ERROR")
            if sig_id: self.supabase.table("trade_signals").delete().eq("id", sig_id).execute()

    def start(self):
        while True:
            try:
                if not self.connect():
                    time.sleep(10)
                    continue
                
                ASSETS = ["EURUSD-OTC", "GBPUSD-OTC", "USDJPY-OTC", "USDCHF-OTC", "AUDCAD-OTC"]
                
                while True:
                    self.fetch_config()
                    if self.config["status"] == "RESTARTING":
                        self.supabase.table("bot_config").update({"status": "RUNNING"}).eq("id", 1).execute()
                        break
                    
                    if not self.api.check_connect(): break
                    
                    if self.config["status"] == "RUNNING" and datetime.now().second <= 5:
                        for asset in ASSETS:
                            if asset in self.active_trades: continue
                            try:
                                candles = self.api.get_candles(asset, 60, 20, int(time.time()))
                                sig = TechnicalAnalysis.get_signal(candles)
                                if sig: self.execute_trade(asset, sig)
                            except: pass
                        time.sleep(50)
                    
                    time.sleep(1)
            except: time.sleep(5)

if __name__ == "__main__":
    SimpleBot().start()
