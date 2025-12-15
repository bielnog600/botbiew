import sys
import time
import logging
import json
import threading
import http.server
import socketserver
import os
from datetime import datetime

# --- IMPORTAÇÃO SEGURA DA BIBLIOTECA ---
try:
    from exnovaapi.stable_api import Exnova
except ImportError:
    try:
        from exnovaapi.stable_api import ExnovaAPI as Exnova
    except ImportError:
        print("[ERRO CRÍTICO] Biblioteca 'exnovaapi' não encontrada.")
        sys.exit(1)

# --- IMPORTAÇÕES DO PROJETO ---
try:
    from config import settings
    from core.trader import TechnicalAnalysis, MoneyManager
except ImportError as e:
    print(f"[ERRO DE IMPORTAÇÃO] Verifique os ficheiros config.py e core/trader.py: {e}")
    sys.exit(1)

# Configuração de Logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("websocket").setLevel(logging.WARNING)

# ==============================================================================
#                       MONKEY PATCHES (CORREÇÕES)
# ==============================================================================

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

# ==============================================================================
#                               BOT CLASS
# ==============================================================================

class SimpleBot:
    def __init__(self):
        self.api = None
        self.money_manager = MoneyManager()
        self.blacklist = set()
        self.active_trades = set()
        self.balance_type = settings.MODE if hasattr(settings, 'MODE') else "PRACTICE"
        
        self.amount = getattr(settings, 'AMOUNT', 1.0)
        self.martingale_factor = getattr(settings, 'MARTINGALE_FACTOR', 2.2)
        self.martingale_levels = getattr(settings, 'MARTINGALE_LEVELS', 2)

    def connect(self):
        print(f"\n🔌 Conectando à Exnova ({settings.EXNOVA_EMAIL})...")
        self.api = Exnova(settings.EXNOVA_EMAIL, settings.EXNOVA_PASSWORD)
        
        check, reason = self.api.connect()
        if not check:
            print(f"❌ Erro ao conectar: {reason}")
            return False
        
        print("✅ Conectado!")
        self.api.get_all_init_v2() 
        try: self.api.update_ACTIVES_OPCODE()
        except: pass
            
        self.api.change_balance(self.balance_type)
        try:
            balance = self.api.get_balance()
            print(f"💰 Saldo Atual: {balance} ({self.balance_type})")
        except:
            print("⚠️ Não foi possível ler o saldo inicial.")
        return True

    def get_candles_safe(self, asset):
        try:
            timestamp = int(time.time()) - 10
            candles = self.api.get_candles(asset, 60, 280, timestamp)
            return candles if candles else []
        except Exception as e:
            if "consts" in str(e):
                self.blacklist.add(asset)
            return []

    def safe_buy(self, asset, amount, direction, type="digital"):
        try:
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
                print(f"⚠️ Timeout ao enviar ordem para {asset}")
                return False, None
            
            return result[0] if result[0] else (False, None)
        except:
            return False, None

    def execute_trade(self, asset, direction):
        amount = self.money_manager.get_amount(asset, self.amount, self.martingale_factor)
        print(f"➡️ ABRINDO: {asset} | {direction.upper()} | ${amount}")
        
        status, id = self.safe_buy(asset, amount, direction, "digital")
        if not status:
             status, id = self.safe_buy(asset, amount, direction, "binary")
        
        if status:
            print(f"✅ Ordem {id} aceite. Aguardando...")
            self.active_trades.add(asset)
            time.sleep(65)
            
            win_dig = self.api.check_win_digital_v2(id)
            win_bin = self.api.check_win_v4(id) if isinstance(id, int) else None

            is_win = False
            profit = 0
            
            if isinstance(win_dig, tuple) and win_dig[1] > 0: is_win, profit = True, win_dig[1]
            elif isinstance(win_dig, (int, float)) and win_dig > 0: is_win, profit = True, win_dig
            elif isinstance(win_bin, tuple) and win_bin[0] == 'win': is_win, profit = True, win_bin[1]
                
            if is_win:
                print(f"🏆 WIN em {asset}! +${profit:.2f}")
                self.money_manager.register_result(asset, 'win', self.martingale_levels)
            else:
                print(f"🔻 LOSS em {asset}.")
                self.money_manager.register_result(asset, 'loss', self.martingale_levels)
            
            self.active_trades.discard(asset)
        else:
            print(f"❌ Falha ao abrir ordem em {asset}.")

    def start(self):
        if not self.connect(): return

        ASSETS = [
            "EURUSD-OTC", "GBPUSD-OTC", "USDJPY-OTC", "EURJPY-OTC", 
            "USDCHF-OTC", "AUDCAD-OTC", "NZDUSD-OTC", "EURGBP-OTC", 
            "AUDUSD-OTC", "USDMXN-OTC"
        ]

        print("\n🚀 Bot Iniciado! Monitorando...")
        
        while True:
            try:
                if not self.api.check_connect():
                    print("⚠️ Reconectando...")
                    if self.connect(): time.sleep(2)
                    else: time.sleep(5)
                    continue

                now = datetime.now()
                if now.second <= 5:
                    print(f"\n--- 🔎 Varredura {now.strftime('%H:%M:%S')} ---")
                    for asset in ASSETS:
                        if asset in self.blacklist or asset in self.active_trades: continue
                        
                        print(f"Analisando {asset}...", end=" ", flush=True)
                        candles = self.get_candles_safe(asset)
                        if not candles or len(candles) < 30: 
                            print("❌ Velas Vazias")
                            continue
                        
                        signal = TechnicalAnalysis.get_signal(candles)
                        
                        if signal:
                            print(f"\n🔔 SINAL: {asset} -> {signal.upper()}")
                            self.execute_trade(asset, signal)
                            time.sleep(1)
                    
                    print("\n⏳ Aguardando próximo minuto...")
                    time.sleep(50)
                time.sleep(1)

            except KeyboardInterrupt:
                print("\nParado.")
                break
            except Exception as e:
                print(f"Erro Loop: {e}")
                time.sleep(5)

# --- SERVIDOR WEB INTEGRADO ---
def run_dashboard():
    """Serve a pasta 'public' na porta 8000."""
    PORT = 8000
    DIRECTORY = "public"
    
    # Cria diretório public se não existir (segurança)
    if not os.path.exists(DIRECTORY):
        os.makedirs(DIRECTORY)
        print(f"[SERVER] Criando pasta {DIRECTORY}...")
        
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=DIRECTORY, **kwargs)
    
    # Permite reuso da porta para evitar erros em restarts rápidos
    socketserver.TCPServer.allow_reuse_address = True
    
    try:
        with socketserver.TCPServer(("", PORT), Handler) as httpd:
            print(f"🌐 Painel Web Online na porta {PORT}")
            httpd.serve_forever()
    except Exception as e:
        print(f"[SERVER ERROR] Falha ao iniciar servidor web: {e}")

if __name__ == "__main__":
    print("[INIT] Inicializando Sistema Híbrido (Bot + Web)...")
    
    # 1. Inicia o Servidor Web em Background (Thread)
    web_thread = threading.Thread(target=run_dashboard, daemon=True)
    web_thread.start()
    
    # 2. Inicia o Bot na Thread Principal
    try:
        bot = SimpleBot()
        bot.start()
    except KeyboardInterrupt:
        print("\n[END] Sistema encerrado.")
    except Exception as e:
        print(f"\n[CRITICAL ERROR] O Bot falhou: {e}")
        traceback.print_exc()
