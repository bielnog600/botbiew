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
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://ioduahwknfsktujthfyc.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImlvZHVhaHdrbmZza3R1anRoZnljIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTEzMDc0NDcsImV4cCI6MjA2Njg4MzQ0N30.96f8wZO6SvABKFMWjIiw1pSugAB4Isldj7yxLcLJRSE")
EXNOVA_EMAIL = os.environ.get("EXNOVA_EMAIL", "seu_email@exemplo.com")
EXNOVA_PASSWORD = os.environ.get("EXNOVA_PASSWORD", "sua_senha")

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
logging.getLogger("urllib3").setLevel(logging.WARNING)

# --- ANÁLISE TÉCNICA (ESTRATÉGIA V2 REFINADA + FLOW OTIMIZADO) ---
class TechnicalAnalysis:
    
    @staticmethod
    def calculate_sma(candles, period):
        """Calcula a SMA (Média Móvel Simples)."""
        if len(candles) < period:
            return 0
        return sum(c['close'] for c in candles[-period:]) / period

    @staticmethod
    def calculate_ema(candles, period):
        """Calcula a EMA (Média Móvel Exponencial)."""
        if len(candles) < period: return 0
        
        prices = [c['close'] for c in candles]
        ema = sum(prices[:period]) / period
        k = 2 / (period + 1)
        
        for price in prices[period:]:
            ema = (price * k) + (ema * (1 - k))
            
        return ema

    @staticmethod
    def calculate_ema_series(values, period):
        """Calcula uma série de valores EMA."""
        if len(values) < period:
            return []

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
        
        return {
            'color': color, 'body': body, 'upper_wick': upper_wick,
            'lower_wick': lower_wick, 'close': close_p, 'open': open_p, 
            'max': high_p, 'min': low_p
        }
    
    @staticmethod
    def flow_filter(candles):
        """
        Filtro de Fluxo (MACD-like simplificado).
        """
        if len(candles) < 50: return None 

        candles = candles[-80:]

        buffer_series = []
        for i in range(35, len(candles) + 1):
            slice_c = candles[:i]
            fast = TechnicalAnalysis.calculate_sma(slice_c, 3)
            slow = TechnicalAnalysis.calculate_sma(slice_c, 34)
            buffer_series.append(fast - slow)

        signal_series = TechnicalAnalysis.calculate_ema_series(buffer_series, 6)

        if len(signal_series) < 2 or len(buffer_series) < 2:
            return None

        buffer_now = buffer_series[-1]
        signal_now = signal_series[-1]

        if buffer_now > signal_now:
            return "BULL"
        elif buffer_now < signal_now:
            return "BEAR"

        return None

    @staticmethod
    def engulf_filter(candles, direction):
        """
        Verifica confirmação de força (Engolfo adaptado para OTC).
        """
        last = TechnicalAnalysis.analyze_candle(candles[-1])
        prev = TechnicalAnalysis.analyze_candle(candles[-2])

        # Engolfo flexível (60% do corpo anterior)
        if direction == "call":
            return (
                last['color'] == 'green' and
                prev['color'] == 'red' and
                last['body'] >= prev['body'] * 0.6
            )

        if direction == "put":
            return (
                last['color'] == 'red' and
                prev['color'] == 'green' and
                last['body'] >= prev['body'] * 0.6
            )

        return False

    @staticmethod
    def get_signal(candles):
        """
        Estratégia V2 Otimizada: EMA 9 + EMA 21 + Confirmação
        AGRESSIVO: Relaxa filtros dependendo do horário
        """
        if len(candles) < 60: return None, "Dados insuficientes"

        # --- FILTRO DINÂMICO POR HORÁRIO ---
        current_hour = datetime.now().hour
        engulf_required = True
        if current_hour >= 14:
             engulf_required = False

        # 1. CÁLCULO DE INDICADORES
        ema9 = TechnicalAnalysis.calculate_ema(candles, 9)
        ema21 = TechnicalAnalysis.calculate_ema(candles, 21)
        ema21_prev = TechnicalAnalysis.calculate_ema(candles[:-1], 21)
        
        confirm_candle = TechnicalAnalysis.analyze_candle(candles[-1])
        reject_candle = TechnicalAnalysis.analyze_candle(candles[-2])
        
        avg_body = sum([abs(c['close']-c['open']) for c in candles[-7:-2]]) / 5
        
        # 2. FILTROS GLOBAIS
        spread = abs(ema9 - ema21)
        min_spread = avg_body * 0.1
        if spread < min_spread: return None, f"Filtro: EMAs coladas"

        ema21_slope = ema21 - ema21_prev
        min_slope = avg_body * 0.02 
        
        # --- LÓGICA CALL (COMPRA) ---
        if ema9 > ema21 and ema21_slope > min_slope:
            touched_ema = reject_candle['min'] <= (ema21 + (avg_body * 0.1))
            held_support = reject_candle['close'] >= (ema21 - (avg_body * 0.3))
            
            if touched_ema and held_support:
                if reject_candle['lower_wick'] < (reject_candle['body'] * 0.4):
                    return None, "Rejeição fraca (Pavio)"
                
                if confirm_candle['color'] == 'green':
                    has_strength = (
                        confirm_candle['body'] >= (reject_candle['body'] * 0.6) and
                        confirm_candle['body'] >= (avg_body * 0.8)
                    )
                    clean_top = confirm_candle['upper_wick'] < (confirm_candle['body'] * 0.5)
                    
                    if has_strength and clean_top:
                        # Filtros Finais
                        flow = TechnicalAnalysis.flow_filter(candles)
                        if flow != "BULL": return None, "Filtro Fluxo contra"
                        
                        # Fallback horário: Permite entrada sem engolfo perfeito
                        if not engulf_required:
                             return 'call', "V2 CALL (Sem engolfo - fallback horário)"

                        if not TechnicalAnalysis.engulf_filter(candles, "call"): 
                             return None, "Sem força (Engolfo)"

                        return 'call', "V2 CALL (Rejeição + Força + Fluxo)"
                    else:
                        return None, "Confirmação fraca"
                else:
                    return None, "Sem confirmação verde"

        # --- LÓGICA PUT (VENDA) ---
        elif ema9 < ema21 and ema21_slope < -min_slope:
            touched_ema = reject_candle['max'] >= (ema21 - (avg_body * 0.1))
            held_resistance = reject_candle['close'] <= (ema21 + (avg_body * 0.3))
            
            if touched_ema and held_resistance:
                if reject_candle['upper_wick'] < (reject_candle['body'] * 0.4):
                    return None, "Rejeição fraca (Pavio)"
                
                if confirm_candle['color'] == 'red':
                    has_strength = (
                        confirm_candle['body'] >= (reject_candle['body'] * 0.6) and
                        confirm_candle['body'] >= (avg_body * 0.8)
                    )
                    clean_bottom = confirm_candle['lower_wick'] < (confirm_candle['body'] * 0.5)
                    
                    if has_strength and clean_bottom:
                        flow = TechnicalAnalysis.flow_filter(candles)
                        if flow != "BEAR": return None, "Filtro Fluxo contra"
                        
                        # Fallback horário: Permite entrada sem engolfo perfeito
                        if not engulf_required:
                             return 'put', "V2 PUT (Sem engolfo - fallback horário)"

                        if not TechnicalAnalysis.engulf_filter(candles, "put"): 
                             return None, "Sem força (Engolfo)"

                        return 'put', "V2 PUT (Rejeição + Força + Fluxo)"
                    else:
                        return None, "Confirmação fraca"
                else:
                    return None, "Sem confirmação vermelha"
                    
        return None, "Sem configuração V2"

class SimpleBot:
    def __init__(self):
        self.api = None
        self.supabase = None
        self.trade_lock = threading.Lock()
        self.active_trades = set()
        self.active_account_type = None
        self.best_assets = []
        
        self.config = { 
            "status": "PAUSED", "account_type": "PRACTICE", "entry_value": 1.0,
            "stop_win": 10.0, "stop_loss": 5.0, "stop_mode": "percentage", "daily_initial_balance": 0.0,
            "timer_enabled": False, "timer_start": "00:00", "timer_end": "00:00"
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
                self.config["stop_win"] = float(data.get("stop_win", 0))
                self.config["stop_loss"] = float(data.get("stop_loss", 0))
                self.config["stop_mode"] = data.get("stop_mode", "percentage")
                self.config["daily_initial_balance"] = float(data.get("daily_initial_balance", 0))
                self.config["timer_enabled"] = data.get("timer_enabled", False)
                self.config["timer_start"] = data.get("timer_start", "00:00")
                self.config["timer_end"] = data.get("timer_end", "00:00")
            else:
                self.supabase.table("bot_config").insert({"id": 1, "status": "PAUSED"}).execute()
        except: pass

    def check_schedule(self):
        if not self.config.get("timer_enabled", False):
            return 

        now_str = datetime.now().strftime("%H:%M")
        start_str = self.config.get("timer_start", "00:00")
        end_str = self.config.get("timer_end", "00:00")
        
        is_inside = False
        if start_str < end_str:
            is_inside = start_str <= now_str < end_str
        else:
            is_inside = now_str >= start_str or now_str < end_str
            
        current_status = self.config["status"]
        
        if is_inside and current_status == "PAUSED":
            self.log_to_db(f"⏰ Agendador: Iniciando operações ({start_str}-{end_str})", "SYSTEM")
            self.config["status"] = "RUNNING"
            if self.supabase:
                self.supabase.table("bot_config").update({"status": "RUNNING"}).eq("id", 1).execute()
        
        elif not is_inside and current_status == "RUNNING":
            self.log_to_db(f"⏰ Agendador: Pausando operações (Fim do horário)", "SYSTEM")
            self.config["status"] = "PAUSED"
            if self.supabase:
                self.supabase.table("bot_config").update({"status": "PAUSED"}).eq("id", 1).execute()

    def check_management(self):
        if not self.api: return False
        try:
            current_bal = self.api.get_balance()
            initial_bal = self.config.get("daily_initial_balance", 0)

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

            target_win_val = initial_bal * (stop_win / 100) if mode == "percentage" else stop_win
            target_loss_val = initial_bal * (stop_loss / 100) if mode == "percentage" else stop_loss
            
            desc = "%" if mode == "percentage" else "$"

            if profit >= target_win_val and target_win_val > 0:
                self.log_to_db(f"🏆 META BATIDA! Lucro: ${profit:.2f}", "SUCCESS")
                self.pause_bot_by_management()
                return False
            
            if profit <= -target_loss_val and target_loss_val > 0:
                self.log_to_db(f"🛑 STOP LOSS ATINGIDO! Perda: ${profit:.2f}", "ERROR")
                self.pause_bot_by_management()
                return False

            return True
        except Exception as e:
            self.log_to_db(f"Erro no gerenciamento: {e}", "ERROR")
            return True

    def pause_bot_by_management(self):
        self.config["status"] = "PAUSED"
        if self.supabase:
            self.supabase.table("bot_config").update({"status": "PAUSED"}).eq("id", 1).execute()
        time.sleep(2)

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
        self.log_to_db(f"📊 Catalogando Top 3 (Estratégia V2)...", "SYSTEM")
        results = []
        for asset in assets_list:
            try:
                # AUMENTADO PARA 200 CANDLES
                candles = self.api.get_candles(asset, 60, 200, int(time.time()))
                if not candles or len(candles) < 100: continue
                wins, total = 0, 0
                for i in range(60, len(candles)-1): # Buffer 60
                    subset = candles[i-60:i+1]
                    signal, _ = TechnicalAnalysis.get_signal(subset)
                    if signal:
                        total += 1
                        nxt = candles[i+1]
                        is_win = (signal == 'call' and nxt['close'] > nxt['open']) or \
                                 (signal == 'put' and nxt['close'] < nxt['open'])
                        if is_win: wins += 1
                
                # SCORE COM PESO EM QUANTIDADE
                if total >= 2: 
                    wr = (wins / total) * 100
                    score = (wr * 0.7) + (total * 5)
                    results.append({
                        "pair": asset, 
                        "win_rate": wr, 
                        "wins": wins, 
                        "losses": total-wins, 
                        "best_strategy": "EMA V2+Flow",
                        "score": score
                    })
            except: pass
            time.sleep(0.05)
        
        # ORDENA POR SCORE
        results.sort(key=lambda x: x['score'], reverse=True)
        
        # Filtro Rigoroso 60%
        valid_results = [r for r in results if r['win_rate'] >= 60]
        
        if valid_results:
            top_3 = valid_results[:3]
            pairs_str = ", ".join([f"{r['pair']} ({r['win_rate']:.0f}%)" for r in top_3])
            self.log_to_db(f"💎 Melhores (Score): {pairs_str}", "SUCCESS")
            try:
                if self.supabase:
                    self.supabase.table("cataloged_assets").delete().neq("pair", "XYZ").execute() 
                    self.supabase.table("cataloged_assets").insert(top_3).execute()
            except: pass
            return [r['pair'] for r in top_3]
        
        # FALLBACK AGRESSIVO
        if results:
             top_1 = results[:1]
             self.log_to_db(f"⚠️ Fallback agressivo: {top_1[0]['pair']} (WR: {top_1[0]['win_rate']:.1f}%)", "WARNING")
             try:
                if self.supabase:
                    self.supabase.table("cataloged_assets").delete().neq("pair", "XYZ").execute() 
                    self.supabase.table("cataloged_assets").insert(top_1).execute()
             except: pass
             return [top_1[0]['pair']]
        
        self.log_to_db("⚠️ Sem ativos viáveis (nem para fallback).", "WARNING")
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

    def execute_trade(self, asset, direction):
        if not self.api: return
        
        try: balance_before = self.api.get_balance()
        except: return

        if not self.check_management(): return

        with self.trade_lock:
            if asset in self.active_trades: return
            self.active_trades.add(asset)

        amount = self.config["entry_value"]
        self.log_to_db(f"➡️ ABRINDO (V2): {asset} | {direction.upper()} | ${amount}", "INFO")
        
        sig_id = None
        try:
            if self.supabase:
                res = self.supabase.table("trade_signals").insert({
                    "pair": asset, "direction": direction, "strategy": f"EMA V2",
                    "status": "PENDING", "result": "PENDING", "created_at": datetime.now().isoformat(), "profit": 0
                }).execute()
                if res.data: sig_id = res.data[0]['id']
        except: pass

        status, id = self.safe_buy(asset, amount, direction, "digital")
        if not status: status, id = self.safe_buy(asset, amount, direction, "binary")

        if status:
            self.log_to_db(f"✅ Ordem {id} aceita. Aguardando (64s)...", "INFO")
            time.sleep(64)
            
            profit = 0.0
            res_str = "PENDING"
            
            try:
                balance_after = self.api.get_balance()
                delta = balance_after - balance_before
                if delta > 0: res_str, profit = 'WIN', delta
                elif delta < 0: res_str, profit = 'LOSS', delta
                else: res_str, profit = 'DOJI', 0.0
            except: res_str = 'UNKNOWN'

            # COOLDOWN REDUZIDO (60s)
            if res_str == 'LOSS': 
                self.last_loss_time = time.time()
                self.log_to_db(f"🛑 Cooldown ativo: Pausa de 60s.", "WARNING")

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

                    self.check_schedule()

                    if time.time() - last_scan > 10:
                        try:
                            self.update_balance_remote()
                            targets = self.best_assets[:3] if self.best_assets else ["EURUSD-OTC"]
                            
                            # Log com sufixo AGGRESSIVE
                            self.log_to_db(f"MODE_ATIVO::EMA_V2_FLOW_AGGRESSIVE", "SYSTEM")

                            for asset in targets:
                                try:
                                    candles = self.api.get_candles(asset, 60, 100, int(time.time()))
                                    if candles:
                                        price = candles[-1]['close']
                                        ema21 = TechnicalAnalysis.calculate_ema(candles, 21)
                                        # COOLDOWN CHECK 60s
                                        cd_msg = " [COOLDOWN]" if (time.time() - self.last_loss_time < 60) else ""
                                        self.log_to_db(f"ANALISE_DETALHADA::{asset}::Preço:{price:.5f}::EMA21:{ema21:.5f}{cd_msg}", "SYSTEM")
                                        time.sleep(0.2)
                                except: pass
                        except Exception as e: self.log_to_db(f"Erro monitoramento: {e}", "WARNING")
                        last_scan = time.time()
                    
                    if time.time() - last_bal > 60: self.update_balance_remote(); last_bal = time.time()

                    if self.config["status"] == "PAUSED": time.sleep(2); continue
                    if not self.check_management(): time.sleep(5); continue

                    now_sec = datetime.now().second
                    # JANELA DE EXECUÇÃO AMPLIADA 55-59
                    if 55 <= now_sec <= 59:
                        # COOLDOWN CHECK 60s
                        if time.time() - self.last_loss_time < 60: time.sleep(2); continue
                        if not self.best_assets:
                            self.log_to_db("⛔ Sem ativos válidos (nem fallback).", "WARNING")
                            time.sleep(2); continue

                        current_assets = self.best_assets.copy()
                        random.shuffle(current_assets)
                        trade_executed = False
                        
                        for asset in current_assets:
                            with self.trade_lock:
                                if asset in self.active_trades: continue
                            try:
                                self.log_to_db(f"SCAN_ENTRADA::{asset}", "SYSTEM")
                                candles = self.api.get_candles(asset, 60, 100, int(time.time()))
                                
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
