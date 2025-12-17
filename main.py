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
# SEGURANÇA: Chaves removidas do código. Use variáveis de ambiente.
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
EXNOVA_EMAIL = os.environ.get("EXNOVA_EMAIL", "")
EXNOVA_PASSWORD = os.environ.get("EXNOVA_PASSWORD", "")

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
logging.getLogger("urllib3").setLevel(logging.WARNING)

# --- ANÁLISE TÉCNICA (SMA 14 + Consistência Temporal + ATR + S&R) ---
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
        # Começa calculando TRs
        for i in range(1, len(candles)):
            current = candles[i]
            prev = candles[i-1]
            hl = current['max'] - current['min']
            hc = abs(current['max'] - prev['close'])
            lc = abs(current['min'] - prev['close'])
            tr_list.append(max(hl, hc, lc))
        
        # Simples média dos TRs (pode usar suavização em versões futuras)
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
            'color': color,
            'body': body,
            'upper_wick': upper_wick,
            'lower_wick': lower_wick,
            'close': close_p,
            'open': open_p,
            'max': high_p,
            'min': low_p
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
        # Aumentamos buffer para garantir calculo histórico correto
        if len(candles) < 40: return None, "Dados insuficientes"
        
        # 1. Indicadores Globais
        atr = TechnicalAnalysis.calculate_atr(candles, 14)
        support, resistance = TechnicalAnalysis.get_support_resistance(candles, window=20)
        last = TechnicalAnalysis.analyze_candle(candles[-1])
        
        # Filtro de Volatilidade (ATR Mínimo)
        # Se o ATR for muito baixo, mercado está "morto"
        if atr < 0.00003: return None, f"Baixa Volatilidade (ATR: {atr:.5f})"

        # Zona de Segurança Dinâmica (com piso mínimo)
        avg_body = sum([abs(c['close']-c['open']) for c in candles[-6:-1]]) / 5
        safe_zone = max(avg_body * 0.5, 0.00005) 

        # 2. Lógica de Consistência Temporal (CORRIGIDA)
        # Verifica se as últimas 7 velas estavam acima/abaixo da SMA DO MOMENTO DELAS
        consistency_count = 7
        trend_up_consistent = True
        trend_down_consistent = True

        for i in range(1, consistency_count + 1):
            idx = -i # -1, -2 ... -7
            
            # Recorta os candles como se estivéssemos no passado, no momento 'idx'
            # Se len=100, idx=-1. Queremos candles[:100]. SMA usa os últimos 14 desse slice.
            historical_slice = candles[:len(candles) + idx + 1] 
            
            sma_historical = TechnicalAnalysis.calculate_sma(historical_slice, 14)
            candle_at_moment = candles[idx]
            
            if candle_at_moment['close'] <= sma_historical:
                trend_up_consistent = False
            
            if candle_at_moment['close'] >= sma_historical:
                trend_down_consistent = False
            
            # Otimização: Se ambos já falharam, para o loop
            if not trend_up_consistent and not trend_down_consistent:
                break

        if not trend_up_consistent and not trend_down_consistent:
            return None, f"Lateralizado (Falha na consistência de {consistency_count} velas)"

        # 3. Filtro de Vela Anterior (Continuidade)
        prev = TechnicalAnalysis.analyze_candle(candles[-2])
        
        # --- LÓGICA CALL ---
        if trend_up_consistent:
            # Confirmação vela anterior também verde ou doji alta
            if prev['close'] < prev['open']: return None, "Vela anterior vermelha (contra tendência)"

            # FILTRO S&R
            if resistance and (resistance - last['close']) < safe_zone:
                return None, "Abortar: Muito perto da Resistência"

            if last['color'] == 'green':
                if last['upper_wick'] < (last['body'] * 0.6):
                    return 'call', f"Alta Forte (7 velas > SMA14 Histórica)"
                else:
                    return None, "Rejeição Alta (Pavio)"

        # --- LÓGICA PUT ---
        elif trend_down_consistent:
            # Confirmação vela anterior também vermelha ou doji baixa
            if prev['close'] > prev['open']: return None, "Vela anterior verde (contra tendência)"

            # FILTRO S&R
            if support and (last['close'] - support) < safe_zone:
                return None, "Abortar: Muito perto do Suporte"

            if last['color'] == 'red':
                if last['lower_wick'] < (last['body'] * 0.6):
                    return 'put', f"Baixa Forte (7 velas < SMA14 Histórica)"
                else:
                    return None, "Rejeição Baixa (Pavio)"
                    
        return None, "Sem sinal claro"

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
        # LOCK para evitar Race Condition
        self.trade_lock = threading.Lock()
        self.active_trades = set()
        self.active_account_type = None
        self.best_assets = []
        self.config = { "status": "PAUSED", "account_type": "PRACTICE", "entry_value": 1.0 }
        self.init_supabase()

    def init_supabase(self):
        # Validação simples para evitar erro se não tiver credenciais
        if not SUPABASE_URL or not SUPABASE_KEY:
            print("⚠️ Supabase Credentials não encontradas. Logs remotos desativados.")
            return

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
        except Exception as e: 
            print(f"Erro local de log: {e}")
            # Tenta reconectar em caso de falha silenciosa
            try: self.supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
            except: pass

    def update_balance_remote(self):
        if not self.api or not self.supabase: return
        try:
            balance = self.api.get_balance()
            self.supabase.table("bot_config").update({"current_balance": balance}).eq("id", 1).execute()
        except Exception as e:
            self.log_to_db(f"Erro update balance: {e}", "ERROR")

    def fetch_config(self):
        if not self.supabase: 
            self.init_supabase()
            return

        try:
            res = self.supabase.table("bot_config").select("*").eq("id", 1).execute()
            if res.data:
                data = res.data[0]
                self.config["status"] = data.get("status", "PAUSED")
                self.config["account_type"] = data.get("account_type", "PRACTICE").strip().upper()
                self.config["entry_value"] = float(data.get("entry_value", 1.0))
            else:
                self.supabase.table("bot_config").insert({"id": 1, "status": "PAUSED"}).execute()
        except Exception as e:
            self.log_to_db(f"Erro fetch config: {e}", "ERROR")

    def connect(self):
        self.log_to_db(f"🔌 Conectando...", "SYSTEM")
        try:
            if self.api: 
                try: self.api.api.close() 
                except: pass
            
            if not EXNOVA_EMAIL or not EXNOVA_PASSWORD:
                self.log_to_db("Credenciais Exnova não configuradas.", "ERROR")
                return False

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
        self.log_to_db(f"📊 Catalogando Top 3 (SMA 14 + S&R)...", "SYSTEM")
        results = []
        
        for asset in assets_list:
            try:
                # Aumentado para 150 candles para ter histórico suficiente nos testes
                candles = self.api.get_candles(asset, 60, 150, int(time.time()))
                if not candles or len(candles) < 100: continue
                
                wins, total = 0, 0
                # Começa do 40 para garantir que get_signal tenha buffer para SMA histórica
                for i in range(40, len(candles)-1):
                    # Passa o subset terminando em 'i'
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
                    results.append({
                        "pair": asset, "win_rate": wr, "wins": wins, "losses": total-wins, "best_strategy": "Nano SMA14+SR"
                    })
            except Exception as e:
                 self.log_to_db(f"Erro catalog {asset}: {e}", "WARNING")
            
            time.sleep(0.05)
        
        results.sort(key=lambda x: x['win_rate'], reverse=True)
        top_3 = results[:3]
        
        if top_3:
            pairs_str = ", ".join([f"{r['pair']} ({r['win_rate']:.0f}%)" for r in top_3])
            self.log_to_db(f"💎 Top 3 Ativos: {pairs_str}", "SUCCESS")
            try:
                if self.supabase:
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
                    result[0] = self.api.buy_digital_spot(asset, amount, direction, 1)
                else:
                    result[0] = self.api.buy(amount, asset, direction, 1)
            except Exception as e:
                self.log_to_db(f"Erro safe_buy: {e}", "ERROR")
        t = threading.Thread(target=target)
        t.daemon = True
        t.start()
        t.join(timeout=10.0)
        return result[0] if result[0] else (False, None)

    def execute_trade(self, asset, direction):
        if not self.api: return
        
        # LOCK: Evita duplicidade no mesmo ativo
        with self.trade_lock:
            if asset in self.active_trades: return
            self.active_trades.add(asset)

        amount = self.config["entry_value"]
        self.log_to_db(f"➡️ ABRINDO: {asset} | {direction.upper()} | ${amount}", "INFO")
        
        sig_id = None
        try:
            if self.supabase:
                res = self.supabase.table("trade_signals").insert({
                    "pair": asset,
                    "direction": direction,
                    "strategy": "Nano SMA14+SR",
                    "status": "PENDING", 
                    "result": "PENDING", 
                    "created_at": datetime.now().isoformat()
                }).execute()
                if res.data: sig_id = res.data[0]['id']
        except: pass

        status, id = self.safe_buy(asset, amount, direction, "digital")
        if not status: status, id = self.safe_buy(asset, amount, direction, "binary")

        if status:
            self.log_to_db(f"✅ Ordem {id} aceita.", "INFO")
            # Sleep fora do lock principal, mas ativo já está marcado
            time.sleep(60) 
            
            is_win, profit = False, 0.0
            try:
                # CORREÇÃO: Removido check_win_v4
                win_v = self.api.check_win_digital_v2(id)
                if isinstance(win_v, tuple) and win_v[1] > 0: 
                    is_win, profit = True, float(win_v[1])
                elif isinstance(win_v, (int, float)) and win_v > 0: 
                    is_win, profit = True, float(win_v)
                else:
                    # Fallback apenas para binária v3 se necessário
                    # check_win_v3(id) se fosse implementado
                    pass
            except Exception as e:
                self.log_to_db(f"Erro check_win: {e}", "ERROR")

            res_str = 'WIN' if is_win else 'LOSS'
            if not is_win: profit = -float(amount)

            self.log_to_db(f"{'🏆' if is_win else '🔻'} {res_str}: ${profit:.2f}", "SUCCESS" if is_win else "ERROR")

            if sig_id and self.supabase:
                try: 
                    self.supabase.table("trade_signals").update({
                        "status": res_str, 
                        "result": res_str, 
                        "profit": profit
                    }).eq("id", sig_id).execute()
                except Exception as e:
                    self.log_to_db(f"Erro update DB: {e}", "WARNING")
            
            self.update_balance_remote()
            
            # Libera o ativo para operar novamente
            with self.trade_lock:
                self.active_trades.discard(asset)
        else:
            self.log_to_db("❌ Falha ordem.", "ERROR")
            with self.trade_lock:
                self.active_trades.discard(asset)
            if sig_id and self.supabase: 
                try: self.supabase.table("trade_signals").delete().eq("id", sig_id).execute()
                except: pass

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
                        if self.supabase:
                            self.supabase.table("bot_config").update({"status": "RUNNING"}).eq("id", 1).execute()
                        break
                    
                    if not self.api.check_connect(): break
                    
                    if time.time() - last_catalog > 900:
                        self.best_assets = self.catalog_assets(ASSETS_POOL)
                        last_catalog = time.time()

                    if time.time() - last_scan > 5:
                        try:
                            primary = self.best_assets[0] if self.best_assets and len(self.best_assets) > 0 else "EURUSD-OTC"
                            candles = self.api.get_candles(primary, 60, 40, int(time.time()))
                            if candles:
                                price = candles[-1]['close']
                                sma = TechnicalAnalysis.calculate_sma(candles, 14)
                                self.log_to_db(f"ANALISE::{primary}::P:{price}::SMA14:{sma:.5f}", "SYSTEM")
                        except Exception as e:
                            pass # Log muito frequente pode poluir, manter pass aqui ou debug
                        last_scan = time.time()
                    
                    if time.time() - last_bal > 60:
                        self.update_balance_remote()
                        last_bal = time.time()

                    if self.config["status"] == "PAUSED":
                        time.sleep(2)
                        continue

                    if datetime.now().second >= 55:
                        current_assets = self.best_assets.copy()
                        random.shuffle(current_assets)
                        trade_executed = False
                        
                        for asset in current_assets:
                            # Verifica lock antes de pedir candle para economizar recurso
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
                            except Exception as e:
                                self.log_to_db(f"Erro loop asset {asset}: {e}", "WARNING")
                        
                        if trade_executed: time.sleep(50) 
                        else: time.sleep(4) 
                    
                    time.sleep(0.5)
            except Exception as e:
                self.log_to_db(f"Erro loop principal: {e}", "ERROR")
                time.sleep(5)

if __name__ == "__main__":
    SimpleBot().start()
