import sys
import time
import logging
import json
import threading
import os
import random
from datetime import datetime, timedelta
# Certifique-se de instalar: pip install supabase exnovaapi
from supabase import create_client, Client

# --- IMPORTAÇÃO DA EXNOVA ---
try:
    from exnovaapi.stable_api import Exnova
except ImportError:
    print("[ERRO] Biblioteca 'exnovaapi' não instalada.")

# --- CONFIGURAÇÃO ---
# RESTAURANDO CHAVES PARA FUNCIONAR O LOG REMOTO
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://ioduahwknfsktujthfyc.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImlvZHVhaHdrbmZza3R1anRoZnljIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTEzMDc0NDcsImV4cCI6MjA2Njg4MzQ0N30.96f8wZO6SvABKFMWjIiw1pSugAB4Isldj7yxLcLJRSE")
EXNOVA_EMAIL = os.environ.get("EXNOVA_EMAIL", "seu_email@exemplo.com")
EXNOVA_PASSWORD = os.environ.get("EXNOVA_PASSWORD", "sua_senha")

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
logging.getLogger("urllib3").setLevel(logging.WARNING)

# --- ANÁLISE TÉCNICA ---
class TechnicalAnalysis:
    @staticmethod
    def calculate_sma(candles, period):
        if len(candles) < period: return 0
        slice_candles = candles[-period:]
        total_close = sum([c['close'] for c in slice_candles])
        return total_close / period

    @staticmethod
    def calculate_atr(candles, period=14):
        if len(candles) < period + 1: return 0
        tr_list = []
        for i in range(1, len(candles)):
            current = candles[i]
            prev = candles[i-1]
            hl = current['max'] - current['min']
            hc = abs(current['max'] - prev['close'])
            lc = abs(current['min'] - prev['close'])
            tr_list.append(max(hl, hc, lc))
        if len(tr_list) < period: return 0
        return sum(tr_list[-period:]) / period

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
            'color': color, 'body': body, 'upper_wick': upper_wick,
            'lower_wick': lower_wick, 'close': close_p, 'open': open_p,
            'max': high_p, 'min': low_p
        }

    @staticmethod
    def get_support_resistance(candles, window=20):
        if len(candles) <= window: return None, None
        subset = candles[-(window+1):-1]
        resistance = max(c['max'] for c in subset)
        support = min(c['min'] for c in subset)
        return support, resistance

    @staticmethod
    def get_signal(candles):
        if len(candles) < 40: return None, "Dados insuficientes"
        
        atr = TechnicalAnalysis.calculate_atr(candles, 14)
        support, resistance = TechnicalAnalysis.get_support_resistance(candles, window=20)
        last = TechnicalAnalysis.analyze_candle(candles[-1])
        
        # 2.1. ATR ADAPTATIVO
        min_atr_required = last['close'] * 0.00005
        if atr < min_atr_required: 
            return None, f"Baixa Volatilidade (ATR {atr:.5f} < {min_atr_required:.5f})"

        avg_body = sum([abs(c['close']-c['open']) for c in candles[-6:-1]]) / 5
        
        # 4.1. FILTRO MICRO-DOJI
        if last['body'] < avg_body * 0.4:
            return None, f"Filtro: Corpo pequeno/Indecisão ({last['body']:.5f})"

        # 2.2. SAFE ZONE CAPPED
        safe_zone = min(max(avg_body * 0.5, 0.00005), atr * 0.6)

        consistency_count = 7
        trend_up_consistent = True
        trend_down_consistent = True

        for i in range(1, consistency_count + 1):
            idx = -i
            historical_slice = candles[:len(candles) + idx + 1] 
            sma_historical = TechnicalAnalysis.calculate_sma(historical_slice, 14)
            candle_at_moment = candles[idx]
            
            if candle_at_moment['close'] <= sma_historical: trend_up_consistent = False
            if candle_at_moment['close'] >= sma_historical: trend_down_consistent = False
            if not trend_up_consistent and not trend_down_consistent: break

        if not trend_up_consistent and not trend_down_consistent:
            return None, f"Lateralizado (Sem tendência de {consistency_count} velas)"

        prev = TechnicalAnalysis.analyze_candle(candles[-2])
        
        # --- LÓGICA CALL ---
        if trend_up_consistent:
            if prev['close'] < prev['open']: return None, "Filtro: Vela anterior vermelha"
            if resistance and (resistance - last['close']) < safe_zone: return None, "Filtro: Perto da Resistência"

            if last['color'] == 'green':
                if last['upper_wick'] < (last['body'] * 0.6):
                    return 'call', f"Sinal COMPRA (7 velas > SMA14)"
                else:
                    return None, "Filtro: Pavio Superior Grande"

        # --- LÓGICA PUT ---
        elif trend_down_consistent:
            if prev['close'] > prev['open']: return None, "Filtro: Vela anterior verde"
            if support and (last['close'] - support) < safe_zone: return None, "Filtro: Perto do Suporte"

            if last['color'] == 'red':
                if last['lower_wick'] < (last['body'] * 0.6):
                    return 'put', f"Sinal VENDA (7 velas < SMA14)"
                else:
                    return None, "Filtro: Pavio Inferior Grande"
                    
        return None, "Neutro"

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
        self.trade_lock = threading.Lock()
        self.active_trades = set()
        self.active_account_type = None
        self.best_assets = []
        
        # Configuração inicial (será sobrescrita pelo fetch_config)
        self.config = { 
            "status": "PAUSED", 
            "account_type": "PRACTICE", 
            "entry_value": 1.0,
            "stop_win": 10.0,
            "stop_loss": 5.0,
            "stop_mode": "percentage", # 'percentage' ou 'value'
            "daily_initial_balance": 0.0
        }
        
        self.last_loss_time = 0
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
        if not self.api or not self.supabase: return
        try:
            balance = self.api.get_balance()
            self.supabase.table("bot_config").update({"current_balance": balance}).eq("id", 1).execute()
        except: pass

    def fetch_config(self):
        if not self.supabase: self.init_supabase(); return
        try:
            res = self.supabase.table("bot_config").select("*").eq("id", 1).execute()
            if res.data:
                data = res.data[0]
                self.config["status"] = data.get("status", "PAUSED")
                self.config["account_type"] = data.get("account_type", "PRACTICE").strip().upper()
                self.config["entry_value"] = float(data.get("entry_value", 1.0))
                
                # NOVOS CAMPOS DE GERENCIAMENTO
                self.config["stop_win"] = float(data.get("stop_win", 0))
                self.config["stop_loss"] = float(data.get("stop_loss", 0))
                self.config["stop_mode"] = data.get("stop_mode", "percentage") # percentage ou value
                self.config["daily_initial_balance"] = float(data.get("daily_initial_balance", 0))

            else:
                self.supabase.table("bot_config").insert({"id": 1, "status": "PAUSED"}).execute()
        except: pass

    def check_management(self):
        """
        Verifica se a meta ou stop loss foi atingido.
        Retorna True se pode operar, False se deve parar.
        """
        if not self.api: return False
        
        try:
            current_bal = self.api.get_balance()
            initial_bal = self.config.get("daily_initial_balance", 0)

            # Se for a primeira vez no dia (ou após reset), define o saldo inicial
            if initial_bal <= 0:
                initial_bal = current_bal
                self.config["daily_initial_balance"] = initial_bal
                if self.supabase:
                    self.supabase.table("bot_config").update({"daily_initial_balance": initial_bal}).eq("id", 1).execute()
                self.log_to_db(f"Saldo Inicial definido: ${initial_bal:.2f}", "SYSTEM")

            profit = current_bal - initial_bal
            
            stop_win = self.config.get("stop_win", 0)
            stop_loss = self.config.get("stop_loss", 0)
            mode = self.config.get("stop_mode", "percentage")

            target_win_val = 0
            target_loss_val = 0

            # Cálculo dos limites (Valor ou Porcentagem)
            if mode == "percentage":
                target_win_val = initial_bal * (stop_win / 100)
                target_loss_val = initial_bal * (stop_loss / 100)
                desc = "%"
            else:
                target_win_val = stop_win
                target_loss_val = stop_loss
                desc = "$"

            # Verifica Meta (Stop Win)
            if profit >= target_win_val and target_win_val > 0:
                self.log_to_db(f"🏆 META BATIDA! Lucro: ${profit:.2f} (Meta: {stop_win}{desc})", "SUCCESS")
                self.pause_bot_by_management()
                return False
            
            # Verifica Stop Loss
            if profit <= -target_loss_val and target_loss_val > 0:
                self.log_to_db(f"🛑 STOP LOSS ATINGIDO! Perda: ${profit:.2f} (Limit: {stop_loss}{desc})", "ERROR")
                self.pause_bot_by_management()
                return False

            return True

        except Exception as e:
            self.log_to_db(f"Erro no gerenciamento: {e}", "ERROR")
            return True # Em caso de erro, por segurança, permite continuar (ou poderia travar)

    def pause_bot_by_management(self):
        self.config["status"] = "PAUSED"
        if self.supabase:
            self.supabase.table("bot_config").update({"status": "PAUSED"}).eq("id", 1).execute()
        time.sleep(2) # Pausa dramática para logs processarem

    def connect(self):
        self.log_to_db(f"🔌 Conectando...", "SYSTEM")
        try:
            if self.api: 
                try:
                    self.api.api.close()
                except:
                    pass
            
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

    def catalog_assets(self, assets_list):
        self.log_to_db(f"📊 Catalogando Top 3...", "SYSTEM")
        results = []
        for asset in assets_list:
            try:
                candles = self.api.get_candles(asset, 60, 150, int(time.time()))
                if not candles or len(candles) < 100: continue
                wins, total = 0, 0
                for i in range(40, len(candles)-1):
                    subset = candles[i-40:i+1]
                    signal, _ = TechnicalAnalysis.get_signal(subset)
                    if signal:
                        total += 1
                        nxt = candles[i+1]
                        is_win = (signal == 'call' and nxt['close'] > nxt['open']) or \
                                 (signal == 'put' and nxt['close'] < nxt['open'])
                        if is_win: wins += 1
                if total >= 3: 
                    wr = (wins / total) * 100
                    results.append({"pair": asset, "win_rate": wr, "wins": wins, "losses": total-wins, "best_strategy": "Nano SMA14+SR"})
            except: pass
            time.sleep(0.05)
        
        results.sort(key=lambda x: x['win_rate'], reverse=True)
        top_3 = results[:3]
        if top_3:
            pairs_str = ", ".join([f"{r['pair']} ({r['win_rate']:.0f}%)" for r in top_3])
            self.log_to_db(f"💎 Melhores: {pairs_str}", "SUCCESS")
            try:
                if self.supabase:
                    self.supabase.table("cataloged_assets").delete().neq("pair", "XYZ").execute() 
                    self.supabase.table("cataloged_assets").insert(top_3).execute()
            except: pass
            return [r['pair'] for r in top_3]
        return [assets_list[0]]

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

    def execute_trade(self, asset, direction):
        if not self.api: return
        
        # VERIFICAÇÃO FINAL DE GERENCIAMENTO ANTES DE ENTRAR
        if not self.check_management(): return

        with self.trade_lock:
            if asset in self.active_trades: return
            self.active_trades.add(asset)

        amount = self.config["entry_value"]
        self.log_to_db(f"➡️ ABRINDO: {asset} | {direction.upper()} | ${amount}", "INFO")
        
        sig_id = None
        try:
            if self.supabase:
                res = self.supabase.table("trade_signals").insert({
                    "pair": asset, "direction": direction, "strategy": "Nano SMA14+SR",
                    "status": "PENDING", "result": "PENDING", "created_at": datetime.now().isoformat()
                }).execute()
                if res.data: sig_id = res.data[0]['id']
        except: pass

        status, id = self.safe_buy(asset, amount, direction, "digital")
        if not status: status, id = self.safe_buy(asset, amount, direction, "binary")

        if status:
            self.log_to_db(f"✅ Ordem {id} aceita.", "INFO")
            time.sleep(60) 
            is_win, profit = False, 0.0
            try:
                win_v = self.api.check_win_digital_v2(id)
                if isinstance(win_v, tuple) and win_v[1] > 0: is_win, profit = True, float(win_v[1])
                elif isinstance(win_v, (int, float)) and win_v > 0: is_win, profit = True, float(win_v)
            except: pass

            res_str = 'WIN' if is_win else 'LOSS'
            if not is_win: 
                profit = -float(amount)
                self.last_loss_time = time.time()
                self.log_to_db("🛑 Cooldown ativo: Pausa de 2 min.", "WARNING")
            
            self.log_to_db(f"{'🏆' if is_win else '🔻'} {res_str}: ${profit:.2f}", "SUCCESS" if is_win else "ERROR")

            if sig_id and self.supabase:
                try: self.supabase.table("trade_signals").update({"status": res_str, "result": res_str, "profit": profit}).eq("id", sig_id).execute()
                except: pass
            
            self.update_balance_remote()
            
            # VERIFICA GERENCIAMENTO PÓS-RESULTADO
            self.check_management()

            with self.trade_lock: self.active_trades.discard(asset)
        else:
            self.log_to_db("❌ Falha ordem.", "ERROR")
            with self.trade_lock: self.active_trades.discard(asset)
            if sig_id and self.supabase: 
                try: self.supabase.table("trade_signals").delete().eq("id", sig_id).execute()
                except: pass

    def start(self):
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

                while True:
                    self.fetch_config()
                    if self.config["status"] == "RESTARTING":
                        if self.supabase: self.supabase.table("bot_config").update({"status": "RUNNING"}).eq("id", 1).execute()
                        break
                    
                    if not self.api.check_connect(): break
                    if time.time() - last_catalog > 900:
                        self.best_assets = self.catalog_assets(ASSETS_POOL)
                        last_catalog = time.time()

                    # --- LOG DE ANÁLISE PERIÓDICA ---
                    if time.time() - last_scan > 10:
                        try:
                            # ATUALIZA SALDO NO BANCO PERIODICAMENTE
                            self.update_balance_remote()
                            
                            primary = self.best_assets[0] if self.best_assets else "EURUSD-OTC"
                            candles = self.api.get_candles(primary, 60, 40, int(time.time()))
                            if candles:
                                price = candles[-1]['close']
                                sma = TechnicalAnalysis.calculate_sma(candles, 14)
                                cd_msg = " [COOLDOWN ATIVO]" if (time.time() - self.last_loss_time < 120) else ""
                                self.log_to_db(f"ANALISE_DETALHADA::{primary}::Preço:{price:.5f}::SMA14:{sma:.5f}{cd_msg}", "SYSTEM")
                        except Exception as e: self.log_to_db(f"Erro monitoramento: {e}", "WARNING")
                        last_scan = time.time()
                    
                    if time.time() - last_bal > 60: self.update_balance_remote(); last_bal = time.time()

                    if self.config["status"] == "PAUSED": 
                        time.sleep(2)
                        continue
                    
                    # VERIFICAÇÃO DE GERENCIAMENTO NO LOOP PRINCIPAL
                    if not self.check_management():
                        time.sleep(5) # Se bateu meta/stop, espera
                        continue

                    # 2.3. Janela de Execução Estrita
                    now_sec = datetime.now().second
                    if 57 <= now_sec <= 58:
                        if time.time() - self.last_loss_time < 120:
                             time.sleep(2); continue

                        current_assets = self.best_assets.copy()
                        random.shuffle(current_assets)
                        trade_executed = False
                        
                        for asset in current_assets:
                            with self.trade_lock:
                                if asset in self.active_trades: continue
                            try:
                                candles = self.api.get_candles(asset, 60, 40, int(time.time()))
                                sig, reason = TechnicalAnalysis.get_signal(candles)
                                if sig: 
                                    self.log_to_db(f"🔔 SINAL EM {asset}: {sig.upper()} ({reason})", "INFO")
                                    self.execute_trade(asset, sig)
                                    trade_executed = True
                                    break 
                            except: pass
                        
                        if trade_executed: time.sleep(50) 
                        else: time.sleep(4) 
                    time.sleep(0.5)
            except Exception as e:
                self.log_to_db(f"Erro loop principal: {e}", "ERROR")
                time.sleep(5)

if __name__ == "__main__":
    SimpleBot().start()
