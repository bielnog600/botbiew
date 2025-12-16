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

# --- ANÁLISE TÉCNICA (SMA 9 + Rejeição) ---
class TechnicalAnalysis:
    @staticmethod
    def calculate_sma(candles, period):
        if len(candles) < period: return 0
        slice_candles = candles[-period:]
        total_close = sum([c['close'] for c in slice_candles])
        return total_close / period

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
        
        return {
            'color': color,
            'body': body,
            'upper_wick': upper_wick,
            'lower_wick': lower_wick,
            'close': close_p
        }

    @staticmethod
    def get_signal(candles):
        if len(candles) < 15: return None, "Dados insuficientes"
        
        sma_9 = TechnicalAnalysis.calculate_sma(candles, 9)
        last = TechnicalAnalysis.analyze_candle(candles[-1])
        
        if last['body'] < 0.000001: return None, "Sem volume"

        # TENDÊNCIA DE ALTA
        if last['close'] > sma_9:
            if last['color'] == 'green':
                if last['upper_wick'] < (last['body'] * 0.6):
                    return 'call', f"Alta (P > SMA9)"

        # TENDÊNCIA DE BAIXA
        elif last['close'] < sma_9:
            if last['color'] == 'red':
                if last['lower_wick'] < (last['body'] * 0.6):
                    return 'put', f"Baixa (P < SMA9)"
                    
        return None, "Sem tendência"

# --- CORREÇÕES OTC ---
try:
    def update_consts():
        import exnovaapi.constants as OP_code
        OTC_MAP = {
            "EURUSD-OTC": 76, "EURGBP-OTC": 77, "USDCHF-OTC": 78, "EURJPY-OTC": 79,
            "NZDUSD-OTC": 80, "GBPUSD-OTC": 81, "GBPJPY-OTC": 84, "USDJPY-OTC": 85,
            "AUDCAD-OTC": 86, "AUDUSD-OTC": 2111, "USDCAD-OTC": 2112, "AUDJPY-OTC": 2113,
            "GBPCAD-OTC": 2114, "GBPCHF-OTC": 2115, "GBPAUD-OTC": 2116, "EURCAD-OTC": 2117,
            "CHFJPY-OTC": 2118, "CADCHF-OTC": 2119, "EURAUD-OTC": 2120, "USDNOK-OTC": 2121,
            "EURNZD-OTC": 2122, "USDSEK-OTC": 2123, "USDTRY-OTC": 2124, "AUDCHF-OTC": 2129,
            "AUDNZD-OTC": 2130, "EURCHF-OTC": 2131, "GBPNZD-OTC": 2132, "CADJPY-OTC": 2136,
            "NZDCAD-OTC": 2137, "NZDJPY-OTC": 2138
        }
        OP_code.ACTIVES.update(OTC_MAP)
    update_consts()
except: pass

class SimpleBot:
    def __init__(self):
        self.api = None
        self.supabase = None
        self.active_trades = set()
        self.active_account_type = None
        self.best_assets = [] 
        self.config = { "status": "PAUSED", "account_type": "PRACTICE", "entry_value": 1.0 }
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
                "message": message, "level": level, "created_at": datetime.now().isoformat()
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
            res = self.supabase.table("bot_config").select("*").eq("id", 1).execute()
            if res.data:
                data = res.data[0]
                self.config["status"] = data.get("status", "PAUSED")
                self.config["account_type"] = data.get("account_type", "PRACTICE").strip().upper()
                self.config["entry_value"] = float(data.get("entry_value", 1.0))
            else:
                self.supabase.table("bot_config").insert({"id": 1, "status": "PAUSED"}).execute()
        except: pass

    def connect(self):
        self.log_to_db(f"🔌 Conectando...", "SYSTEM")
        try:
            if self.api: 
                try: self.api.api.close() 
                except: pass
            self.api = Exnova(EXNOVA_EMAIL, EXNOVA_PASSWORD)
            if self.api.connect()[0]:
                self.log_to_db("✅ Conectado!", "SUCCESS")
                self.active_account_type = self.config["account_type"]
                self.api.change_balance(self.active_account_type)
                self.update_balance_remote()
                return True
        except: pass
        return False

    def catalog_assets(self, assets_list):
        self.log_to_db(f"📊 Catalogando Top 3...", "SYSTEM")
        results = []
        
        for asset in assets_list:
            try:
                candles = self.api.get_candles(asset, 60, 100, int(time.time()))
                if not candles or len(candles) < 100: continue
                
                wins, total = 0, 0
                for i in range(15, len(candles)-1):
                    subset = candles[i-15:i+1]
                    signal, _ = TechnicalAnalysis.get_signal(subset)
                    
                    if signal:
                        total += 1
                        nxt = candles[i+1]
                        is_win = (signal == 'call' and nxt['close'] > nxt['open']) or \
                                 (signal == 'put' and nxt['close'] < nxt['open'])
                        if is_win: wins += 1
                
                if total >= 3: 
                    wr = (wins / total) * 100
                    results.append({
                        "pair": asset, "win_rate": wr, "wins": wins, "losses": total-wins, "best_strategy": "Nano SMA9"
                    })
            except: pass
            time.sleep(0.05)
        
        results.sort(key=lambda x: x['win_rate'], reverse=True)
        top_3 = results[:3]
        
        if top_3:
            pairs_str = ", ".join([f"{r['pair']} ({r['win_rate']:.0f}%)" for r in top_3])
            self.log_to_db(f"💎 Top 3 Ativos: {pairs_str}", "SUCCESS")
            try:
                self.supabase.table("cataloged_assets").delete().neq("pair", "XYZ").execute() 
                self.supabase.table("cataloged_assets").insert(top_3).execute()
            except: pass
            return [r['pair'] for r in top_3]
        
        self.log_to_db("⚠️ Catalogação fraca, usando padrão.", "WARNING")
        return [assets_list[0]]

    def safe_buy(self, asset, amount, direction, type="digital"):
        result = [None]
        def target():
            try:
                if type == "digital":
                    # O '1' aqui define o tempo de expiração da ordem em minutos.
                    # Se quiser M5, mude para 5.
                    result[0] = self.api.buy_digital_spot(asset, amount, direction, 1)
                else:
                    result[0] = self.api.buy(amount, asset, direction, 1)
            except: pass
        t = threading.Thread(target=target)
        t.daemon = True
        t.start()
        t.join(timeout=10.0)
        return result[0] if result[0] else (False, None)

    def execute_trade(self, asset, direction):
        if not self.api: return
        amount = self.config["entry_value"]
        self.log_to_db(f"➡️ ABRINDO: {asset} | {direction} | ${amount}", "INFO")
        
        sig_id = None
        try:
            res = self.supabase.table("trade_signals").insert({
                "pair": asset,
                "direction": direction,
                "strategy": "Nano SMA9",
                "status": "PENDING", 
                "result": "PENDING", 
                "created_at": datetime.now().isoformat()
            }).execute()
            if res.data: sig_id = res.data[0]['id']
        except: pass

        status, id = self.safe_buy(asset, amount, direction, "digital")
        if not status: status, id = self.safe_buy(asset, amount, direction, "binary")

        if status:
            self.log_to_db(f"✅ Ordem {id} aceita. Aguardando...", "INFO")
            self.active_trades.add(asset)
            
            # Bloqueio intencional (simula foco humano na operação durante 60s)
            time.sleep(60) 
            
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

            if sig_id:
                try: 
                    self.supabase.table("trade_signals").update({
                        "status": res_str, 
                        "result": res_str, 
                        "profit": profit
                    }).eq("id", sig_id).execute()
                except Exception as e:
                    self.log_to_db(f"Erro update DB: {e}", "WARNING")
            else:
                try:
                    rec = self.supabase.table("trade_signals").select("id").eq("pair", asset).eq("status", "PENDING").order("created_at", desc=True).limit(1).execute()
                    if rec.data: self.supabase.table("trade_signals").update({"status": res_str, "result": res_str, "profit": profit}).eq("id", rec.data[0]['id']).execute()
                except: pass
            
            self.update_balance_remote()
            self.active_trades.discard(asset)
        else:
            self.log_to_db("❌ Falha ordem.", "ERROR")
            if sig_id: self.supabase.table("trade_signals").delete().eq("id", sig_id).execute()

    def start(self):
        while True:
            try:
                self.fetch_config()
                if not self.connect():
                    time.sleep(10)
                    continue
                
                ASSETS_POOL = [
                    "EURUSD-OTC", "EURGBP-OTC", "USDCHF-OTC", "EURJPY-OTC",
                    "NZDUSD-OTC", "GBPUSD-OTC", "GBPJPY-OTC", "USDJPY-OTC",
                    "AUDCAD-OTC", "AUDUSD-OTC", "USDCAD-OTC", "AUDJPY-OTC",
                    "GBPCAD-OTC", "GBPCHF-OTC", "GBPAUD-OTC", "EURCAD-OTC",
                    "CHFJPY-OTC", "CADCHF-OTC", "EURAUD-OTC", "USDNOK-OTC",
                    "EURNZD-OTC", "USDSEK-OTC", "USDTRY-OTC", "AUDCHF-OTC",
                    "AUDNZD-OTC", "EURCHF-OTC", "GBPNZD-OTC", "CADJPY-OTC",
                    "NZDCAD-OTC", "NZDJPY-OTC"
                ]
                
                self.best_assets = self.catalog_assets(ASSETS_POOL)
                
                last_scan = 0
                last_bal = 0
                last_catalog = time.time()

                while True:
                    self.fetch_config()
                    if self.config["status"] == "RESTARTING":
                        self.supabase.table("bot_config").update({"status": "RUNNING"}).eq("id", 1).execute()
                        break
                    
                    if not self.api.check_connect(): break
                    
                    if time.time() - last_catalog > 900:
                        self.best_assets = self.catalog_assets(ASSETS_POOL)
                        last_catalog = time.time()

                    if time.time() - last_scan > 5:
                        try:
                            # CORREÇÃO: Garante que primary existe
                            primary = self.best_assets[0] if self.best_assets and len(self.best_assets) > 0 else "EURUSD-OTC"
                            candles = self.api.get_candles(primary, 60, 20, int(time.time()))
                            if candles:
                                price = candles[-1]['close']
                                sma = TechnicalAnalysis.calculate_sma(candles, 9)
                                self.log_to_db(f"ANALISE_DETALHADA::{primary}::Preço:{price}::SMA9:{sma:.5f}", "SYSTEM")
                        except: pass
                        last_scan = time.time()
                    
                    if time.time() - last_bal > 60:
                        self.update_balance_remote()
                        last_bal = time.time()

                    if self.config["status"] == "PAUSED":
                        time.sleep(2)
                        continue

                    # --- VERIFICAÇÃO DO SEGUNDO DE ENTRADA ---
                    # Aqui você define os segundos para entrar na operação.
                    # Exemplo: <= 5 significa que ele tenta entrar nos primeiros 5 segundos da vela (00:00:00 a 00:00:05).
                    # Se quiser antecipar (ex: entrar aos 58s da vela anterior), mude para:
                    # if datetime.now().second >= 58:
                    
                    if datetime.now().second <= 55: 
                        
                        # Baralha a ordem para não parecer robô
                        current_assets = self.best_assets.copy()
                        random.shuffle(current_assets)
                        
                        trade_executed = False
                        
                        for asset in current_assets:
                            if asset in self.active_trades: continue
                            
                            time.sleep(random.uniform(0.5, 1.5))
                            
                            try:
                                candles = self.api.get_candles(asset, 60, 20, int(time.time()))
                                sig, reason = TechnicalAnalysis.get_signal(candles)
                                if sig: 
                                    self.log_to_db(f"🔔 SINAL EM {asset}: {sig.upper()} ({reason})", "INFO")
                                    self.execute_trade(asset, sig)
                                    trade_executed = True
                                    break 
                            except: pass
                        
                        if trade_executed:
                            time.sleep(50) 
                        else:
                            time.sleep(40)
                    
                    time.sleep(1)
            except: time.sleep(5)

if __name__ == "__main__":
    SimpleBot().start()
