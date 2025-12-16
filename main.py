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

# --- ANÁLISE TÉCNICA AVANÇADA ---
class TechnicalAnalysis:
    @staticmethod
    def calculate_sma(candles, period):
        if len(candles) < period: return 0
        slice_candles = candles[-period:]
        total_close = sum([c['close'] for c in slice_candles])
        return total_close / period

    @staticmethod
    def analyze_candle(candle):
        """Retorna propriedades da vela: cor, tamanho corpo, pavios"""
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
        """
        Estratégia: Nano Tendência (SMA 9) + Força de Vela
        """
        if len(candles) < 10: return None
        
        sma_9 = TechnicalAnalysis.calculate_sma(candles, 9)
        last = TechnicalAnalysis.analyze_candle(candles[-1])
        
        # Filtro de Volatilidade Mínima (evita Dojis e mercado parado)
        if last['body'] < 0.000005: return None

        # --- LÓGICA CALL (Tendência de Alta) ---
        if last['close'] > sma_9:
            # 1. Vela anterior Verde (Força a favor)
            if last['color'] == 'green':
                # 2. Confluência: Pavio superior não pode ser muito grande (Rejeição)
                # O pavio superior deve ser menor que 40% do corpo (indica que não houve muita força vendedora no topo)
                if last['upper_wick'] < (last['body'] * 0.5):
                    return 'call'

        # --- LÓGICA PUT (Tendência de Baixa) ---
        elif last['close'] < sma_9:
            # 1. Vela anterior Vermelha (Força a favor)
            if last['color'] == 'red':
                # 2. Confluência: Pavio inferior não pode ser muito grande (Rejeição)
                # O pavio inferior deve ser menor que 40% do corpo
                if last['lower_wick'] < (last['body'] * 0.5):
                    return 'put'
                    
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
        self.active_trades = set()
        self.active_account_type = None
        self.best_asset = None # Ativo do momento
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
                self.config["account_type"] = data.get("account_type", "PRACTICE").strip().upper()
                self.config["entry_value"] = float(data.get("entry_value", 1.0))
            else:
                self.supabase.table("bot_config").insert({"id": 1, "status": "PAUSED"}).execute()
        except: pass

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
            self.update_balance_remote()
            return True
        except Exception as e:
            self.log_to_db(f"❌ Erro crítico connect: {e}", "ERROR")
            return False

    # --- CATALOGAÇÃO INTELIGENTE ---
    def catalog_assets(self, assets_list):
        self.log_to_db("📊 Iniciando catalogação de ativos (100 velas)...", "SYSTEM")
        best_winrate = -1
        best_pair = None
        
        for asset in assets_list:
            try:
                # Pega 100 velas
                candles = self.api.get_candles(asset, 60, 100, int(time.time()))
                if not candles or len(candles) < 100: continue
                
                wins = 0
                total = 0
                
                # Backtest simples nas ultimas 100 velas
                # Começa na vela 10 (precisa de 9 para SMA)
                for i in range(10, len(candles)-1):
                    # Fatia de análise (simula o passado)
                    subset = candles[i-10:i+1]
                    signal = TechnicalAnalysis.get_signal(subset)
                    
                    if signal:
                        total += 1
                        # Verifica resultado na vela seguinte
                        next_candle = candles[i+1]
                        is_win = False
                        if signal == 'call' and next_candle['close'] > next_candle['open']: is_win = True
                        elif signal == 'put' and next_candle['close'] < next_candle['open']: is_win = True
                        
                        if is_win: wins += 1
                
                if total > 0:
                    wr = (wins / total) * 100
                    # self.log_to_db(f"Backtest {asset}: {wr:.1f}% ({wins}/{total})", "INFO") # Opcional: logar tudo
                    
                    # Critério de escolha: Maior Winrate com Minimo de 5 entradas no histórico
                    if wr > best_winrate and total >= 5:
                        best_winrate = wr
                        best_pair = asset
            
            except: pass
            time.sleep(0.1) # Evitar flood api
            
        if best_pair:
            self.log_to_db(f"💎 Melhor par encontrado: {best_pair} com {best_winrate:.1f}% de assertividade.", "SUCCESS")
            # Salva na tabela de catálogo do Supabase (para o front ver)
            try:
                # Limpa catálogo antigo e insere o novo campeão
                self.supabase.table("cataloged_assets").delete().neq("pair", "XYZ").execute() 
                self.supabase.table("cataloged_assets").insert({
                    "pair": best_pair,
                    "win_rate": best_winrate,
                    "wins": 0, "losses": 0, # Placeholder
                    "best_strategy": "Nano SMA9"
                }).execute()
            except: pass
            
            return best_pair
        
        self.log_to_db("⚠️ Nenhum par bom encontrado na catalogação.", "WARNING")
        return assets_list[0] # Retorna o primeiro por padrão

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
        return result[0] if result[0] else (False, None)

    def execute_trade(self, asset, direction):
        if not self.api: return
        amount = self.config["entry_value"]
        self.log_to_db(f"➡️ ABRINDO: {asset} | {direction.upper()} | ${amount}", "INFO")
        
        sig_id = None
        try:
            sig = self.supabase.table("trade_signals").insert({
                "pair": asset,
                "direction": direction,
                "strategy": "Nano SMA9",
                "status": "PENDING",
                "result": "PENDING",
                "created_at": datetime.now().isoformat()
            }).execute()
            if sig.data: sig_id = sig.data[0]['id']
        except: pass

        status, id = self.safe_buy(asset, amount, direction, "digital")
        if not status: status, id = self.safe_buy(asset, amount, direction, "binary")

        if status:
            self.log_to_db(f"✅ Ordem {id} aceite.", "INFO")
            self.active_trades.add(asset)
            time.sleep(60) 
            
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

            if sig_id:
                try: 
                    self.supabase.table("trade_signals").update({
                        "status": result_str, "result": result_str, "profit": profit
                    }).eq("id", sig_id).execute()
                except: pass
            else:
                 # Fallback
                 try:
                    recent = self.supabase.table("trade_signals").select("id").eq("pair", asset).eq("status", "PENDING").order("created_at", desc=True).limit(1).execute()
                    if recent.data:
                        self.supabase.table("trade_signals").update({"status": result_str, "profit": profit}).eq("id", recent.data[0]['id']).execute()
                 except: pass

            self.update_balance_remote()
            self.active_trades.discard(asset)
        else:
            self.log_to_db("❌ Falha na ordem.", "ERROR")
            if sig_id:
                try: self.supabase.table("trade_signals").delete().eq("id", sig_id).execute()
                except: pass

    def start(self):
        while True:
            try:
                # 1. Config & Connect
                self.fetch_config()
                if not self.connect():
                    time.sleep(10)
                    continue
                
                ASSETS_POOL = ["EURUSD-OTC", "GBPUSD-OTC", "USDJPY-OTC", "USDCHF-OTC", "AUDCAD-OTC", "EURJPY-OTC", "NZDUSD-OTC"]
                
                # 2. Catalogação Inicial
                self.best_asset = self.catalog_assets(ASSETS_POOL)
                
                last_scan = 0
                last_bal = 0
                last_catalog = time.time()

                while True:
                    self.fetch_config()
                    
                    if self.config["status"] == "RESTARTING":
                        self.log_to_db("🔄 Reiniciando...", "WARNING")
                        self.supabase.table("bot_config").update({"status": "RUNNING"}).eq("id", 1).execute()
                        break 

                    if not self.api.check_connect():
                        self.log_to_db("⚠️ Reconectando API...", "WARNING")
                        break 

                    # Re-cataloga a cada 15 minutos para garantir que estamos no melhor par
                    if time.time() - last_catalog > 900:
                        self.best_asset = self.catalog_assets(ASSETS_POOL)
                        last_catalog = time.time()

                    if time.time() - last_scan > 5:
                        try:
                            # Heartbeat com o par atual
                            candles = self.api.get_candles(self.best_asset, 60, 25, int(time.time()))
                            if candles:
                                price = candles[-1]['close']
                                # Mostra SMA9 no painel como info extra no lugar do RSI
                                sma = TechnicalAnalysis.calculate_sma(candles, 9)
                                self.log_to_db(f"ANALISE_DETALHADA::{self.best_asset}::Preço:{price}::SMA9:{sma:.5f}", "SYSTEM")
                        except: pass
                        last_scan = time.time()

                    if time.time() - last_bal > 60:
                        self.update_balance_remote()
                        last_bal = time.time()

                    if self.config["status"] == "PAUSED":
                        time.sleep(2)
                        continue

                    # OPERAÇÃO NO MELHOR ATIVO
                    if datetime.now().second <= 5:
                        # Analisa apenas o melhor par catalogado
                        asset = self.best_asset
                        if asset not in self.active_trades:
                            try:
                                candles = self.api.get_candles(asset, 60, 30, int(time.time()))
                                signal = TechnicalAnalysis.get_signal(candles)
                                if signal:
                                    self.log_to_db(f"🔔 SINAL EM {asset}: {signal.upper()}", "INFO")
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
