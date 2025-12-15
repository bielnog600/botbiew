import sys
import time
import logging
import json
import threading
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
#                       CORREÇÕES (MONKEY PATCHES)
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
        except: pass
        return True

    def get_candles_safe(self, asset):
        try:
            # -10s para garantir vela fechada
            timestamp = int(time.time()) - 10
            candles = self.api.get_candles(asset, 60, 280, timestamp)
            return candles if candles else []
        except Exception as e:
            if "consts" in str(e):
                self.blacklist.add(asset)
            return []

    def safe_buy(self, asset, amount, direction, type="digital"):
        """Compra com timeout de 10s."""
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
                print(f"⚠️ Timeout na ordem {asset}")
                return False, None
            
            return result[0] if result[0] else (False, None)
        except Exception:
            return False, None

    def execute_trade(self, asset, direction, is_martingale=False):
        """Executa trade e gere Martingale recursivamente."""
        
        # 1. Calcula Valor
        amount = self.money_manager.get_amount(asset, self.amount, self.martingale_factor)
        step = self.money_manager.get_current_step(asset)
        
        trade_type = "ENTRADA" if step == 0 else f"GALE {step}"
        print(f"➡️ {trade_type}: {asset} | {direction.upper()} | ${amount}")
        
        # 2. Envia Ordem
        status, id = self.safe_buy(asset, amount, direction, "digital")
        if not status:
             status, id = self.safe_buy(asset, amount, direction, "binary")
        
        if status:
            print(f"✅ Ordem {id} aberta. Aguardando...")
            self.active_trades.add(asset)
            
            # Espera Vela Fechar (62s para garantir)
            time.sleep(62)
            
            # 3. Verifica Resultado
            win, profit = False, 0
            
            try:
                res = self.api.check_win_digital_v2(id)
                if isinstance(res, tuple) and res[1] > 0: win, profit = True, res[1]
                elif isinstance(res, (int, float)) and res > 0: win, profit = True, res
            except: pass
            
            if not win:
                try:
                    res = self.api.check_win_v4(id)
                    if isinstance(res, tuple) and res[0] == 'win': win, profit = True, res[1]
                except: pass

            # 4. Processa Resultado e Decide Próximo Passo
            if win:
                print(f"🏆 WIN em {asset}! +${profit:.2f}")
                self.money_manager.register_result(asset, 'win', self.martingale_levels)
                self.active_trades.discard(asset)
            else:
                print(f"🔻 LOSS em {asset}.")
                # Regista loss e verifica se deve fazer Gale
                should_gale = self.money_manager.register_result(asset, 'loss', self.martingale_levels)
                
                if should_gale:
                    print(f"🔄 Preparando Martingale Imediato para {asset}...")
                    # Recursividade: Chama a si mesma para entrar na próxima vela IMEDIATAMENTE
                    self.execute_trade(asset, direction, is_martingale=True)
                else:
                    print(f"⛔ Stop Loss no par {asset}. Voltando a analisar.")
                    self.active_trades.discard(asset)
        else:
            print(f"❌ Falha na ordem {asset}. Cancelando Gale.")
            self.money_manager.register_result(asset, 'win', self.martingale_levels) # Reset para não travar
            self.active_trades.discard(asset)

    def start(self):
        if not self.connect(): return

        ASSETS = [
            "EURUSD-OTC", "GBPUSD-OTC", "USDJPY-OTC", "EURJPY-OTC", 
            "USDCHF-OTC", "AUDCAD-OTC", "NZDUSD-OTC", "EURGBP-OTC", 
            "AUDUSD-OTC", "USDMXN-OTC"
        ]

        print("\n🚀 Bot Iniciado! Aguardando o início do minuto...")
        
        while True:
            try:
                if not self.api.check_connect():
                    print("⚠️ Reconectando...")
                    if self.connect(): time.sleep(2)
                    else: time.sleep(5)
                    continue

                now = datetime.now()
                # Executa nos primeiros 5 segundos do minuto
                if now.second <= 5:
                    print(f"\n--- 🔎 Varredura {now.strftime('%H:%M:%S')} ---")
                    for asset in ASSETS:
                        # Se já houver trade ativo (incluindo gale em andamento), pula
                        if asset in self.blacklist or asset in self.active_trades: continue
                        
                        print(f"Analisando {asset}...", end=" ", flush=True)

                        candles = self.get_candles_safe(asset)
                        if not candles or len(candles) < 30: 
                            print("❌ Velas Vazias")
                            continue
                        
                        signal = TechnicalAnalysis.get_signal(candles)
                        
                        if signal:
                            print(f"\n🔔 SINAL: {asset} -> {signal.upper()}")
                            # Inicia a cadeia de trades (Entrada -> Win ou Gale -> Gale...)
                            # Como é síncrono e recursivo, o bot vai ficar "preso" aqui cuidando
                            # deste par até terminar o ciclo de vitórias ou gales.
                            # Para operar múltiplos pares simultâneos com Gale, precisaríamos de Threads.
                            # Nesta versão simples, ele foca num par até resolver.
                            self.execute_trade(asset, signal)
                            
                            # Após terminar o trade (seja win ou stop gale), volta ao loop
                            break # Sai do for para esperar o próximo minuto e não pegar sinais atrasados
                    
                    print("\n⏳ Aguardando próximo minuto...")
                    time.sleep(50)
                
                time.sleep(1)

            except KeyboardInterrupt:
                print("\nParado.")
                break
            except Exception as e:
                print(f"Erro Loop: {e}")
                time.sleep(5)

if __name__ == "__main__":
    bot = SimpleBot()
    bot.start()
