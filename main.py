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
    print("[ERRO] Biblioteca 'exnovaapi' não instalada. O Coolify instalará via requirements.txt")
    # Em ambiente local sem a lib, o script para aqui. No Coolify, vai funcionar.
    # Se estiver a testar localmente, certifique-se que fez: pip install exnovaapi

# --- CONFIGURAÇÃO SUPABASE & AMBIENTE ---
# Estas variáveis devem ser definidas no Coolify (Environment Variables)
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://ioduahwknfsktujthfyc.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImlvZHVhaHdrbmZza3R1anRoZnljIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTEzMDc0NDcsImV4cCI6MjA2Njg4MzQ0N30.96f8wZO6SvABKFMWjIiw1pSugAB4Isldj7yxLcLJRSE")
EXNOVA_EMAIL = os.environ.get("EXNOVA_EMAIL", "seu_email@exemplo.com")
EXNOVA_PASSWORD = os.environ.get("EXNOVA_PASSWORD", "sua_senha")

# Inicializa cliente Supabase
try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    print(f"[CRÍTICO] Falha ao iniciar Supabase: {e}")
    sys.exit(1)

# Configuração de Logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
logging.getLogger("urllib3").setLevel(logging.WARNING)

# ==============================================================================
#                        CLASSES AUXILIARES (EMBUTIDAS)
# ==============================================================================
# Incluídas aqui para garantir que o bot roda sem depender de ficheiros externos 'core/trader.py'

class MoneyManager:
    def get_amount(self, asset, base_amount, martingale_factor):
        # Lógica simples: retorna o valor base configurado
        return float(base_amount)

    def register_result(self, asset, result, levels):
        pass 

class TechnicalAnalysis:
    @staticmethod
    def get_signal(candles):
        """
        Estratégia Simples de Exemplo (MHI / Padrão de Cores)
        Adapte esta função com a sua estratégia real.
        """
        if len(candles) < 3: return None
        
        # Simulação simples baseada na última vela para demonstração
        last_candle = candles[-1]
        open_price = last_candle['open']
        close_price = last_candle['close']
        
        # Exemplo: Se vela verde, Put. Se vermelha, Call. (Apenas exemplo)
        if close_price > open_price:
            return 'put' if random.random() > 0.6 else None
        else:
            return 'call' if random.random() > 0.6 else None

# ==============================================================================
#                        MONKEY PATCHES (OTC)
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
#                           BOT PRINCIPAL
# ==============================================================================

class SimpleBot:
    def __init__(self):
        self.api = None
        self.money_manager = MoneyManager()
        self.blacklist = set()
        self.active_trades = set()
        
        # Configurações Iniciais (serão sobrescritas pelo Supabase)
        self.config = {
            "status": "PAUSED",
            "account_type": "PRACTICE",
            "entry_value": 1.0,
            "martingale_factor": 2.0,
            "martingale_levels": 1
        }

    def log_to_db(self, message, level="INFO"):
        """Envia logs para o Supabase para o Frontend exibir"""
        print(f"[{level}] {message}")
        try:
            supabase.table("logs").insert({
                "message": message,
                "level": level,
                "created_at": datetime.now().isoformat()
            }).execute()
        except Exception as e:
            print(f"Erro ao logar na DB: {e}")

    def fetch_config(self):
        """Lê as configurações do Painel (Frontend)"""
        try:
            response = supabase.table("bot_config").select("*").eq("id", 1).execute()
            if response.data:
                data = response.data[0]
                self.config["status"] = data.get("status", "PAUSED")
                self.config["account_type"] = data.get("account_type", "PRACTICE")
                self.config["entry_value"] = float(data.get("entry_value", 1.0))
            else:
                # Se não existir config, cria uma padrão
                try:
                    supabase.table("bot_config").insert({"id": 1, "status": "PAUSED"}).execute()
                except: pass
        except Exception as e:
            print(f"Erro ao ler config: {e}")

    def connect(self):
        self.log_to_db(f"🔌 Conectando à Exnova ({EXNOVA_EMAIL})...", "SYSTEM")
        
        try:
            self.api = Exnova(EXNOVA_EMAIL, EXNOVA_PASSWORD)
            check, reason = self.api.connect()
        except Exception as e:
            self.log_to_db(f"❌ Erro crítico na biblioteca API: {e}", "ERROR")
            return False
        
        if not check:
            self.log_to_db(f"❌ Erro ao conectar: {reason}", "ERROR")
            # Se for erro de credenciais, avisa
            if "password" in str(reason).lower() or "email" in str(reason).lower():
                self.log_to_db("Verifique as variáveis EXNOVA_EMAIL e EXNOVA_PASSWORD no Coolify.", "WARNING")
            return False
        
        self.log_to_db("✅ Conectado com sucesso à Exnova!", "SUCCESS")
        
        try:
            self.api.get_all_init_v2() 
            self.api.update_ACTIVES_OPCODE()
        except: pass
            
        # Define o tipo de conta (Real ou Demo) baseado no painel
        self.api.change_balance(self.config["account_type"])
        return True

    def get_candles_safe(self, asset):
        try:
            timestamp = int(time.time()) - 10
            # Pega 60 velas de 1 minuto (size 60)
            candles = self.api.get_candles(asset, 60, 60, timestamp)
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
                        # Digital Spot expira em ~1 min (depende do ativo)
                        result[0] = self.api.buy_digital_spot(asset, amount, direction, 1)
                    else:
                        # Binárias clássicas
                        result[0] = self.api.buy(amount, asset, direction, 1)
                except: pass

            t = threading.Thread(target=target)
            t.daemon = True
            t.start()
            t.join(timeout=10.0)
            
            if t.is_alive():
                self.log_to_db(f"⚠️ Timeout envio ordem: {asset}", "WARNING")
                return False, None
            
            return result[0] if result[0] else (False, None)
        except:
            return False, None

    def execute_trade(self, asset, direction):
        amount = self.config["entry_value"]
        
        # 1. Registar no Supabase como PENDING (para aparecer no histórico)
        self.log_to_db(f"➡️ ABRINDO: {asset} | {direction.upper()} | ${amount}", "INFO")
        
        signal_id = None
        try:
            signal_record = supabase.table("trade_signals").insert({
                "pair": asset,
                "direction": direction,
                "strategy": "Técnica",
                "result": "PENDING",
                "martingale_level": 0,
                "created_at": datetime.now().isoformat()
            }).execute()
            if signal_record.data:
                signal_id = signal_record.data[0]['id']
        except Exception as e:
            print(f"Erro ao salvar sinal: {e}")

        # 2. Executar na Corretora
        status, id = self.safe_buy(asset, amount, direction, "digital")
        
        # Fallback para Binárias se Digital falhar
        if not status:
             status, id = self.safe_buy(asset, amount, direction, "binary")
        
        if status:
            self.log_to_db(f"✅ Ordem {id} aceita. Aguardando resultado...", "INFO")
            self.active_trades.add(asset)
            
            # Aguarda o tempo da vela (aprox. 60s)
            time.sleep(60) 
            
            # 3. Checar Resultado
            win_dig = self.api.check_win_digital_v2(id)
            win_bin = self.api.check_win_v4(id) if isinstance(id, int) else None

            is_win = False
            profit = 0
            
            if isinstance(win_dig, tuple) and win_dig[1] > 0: is_win, profit = True, win_dig[1]
            elif isinstance(win_dig, (int, float)) and win_dig > 0: is_win, profit = True, win_dig
            elif isinstance(win_bin, tuple) and win_bin[0] == 'win': is_win, profit = True, win_bin[1]
                
            # 4. Atualizar Supabase com Resultado Final
            result_str = 'WIN' if is_win else 'LOSS'
            
            if is_win:
                self.log_to_db(f"🏆 WIN em {asset}! +${profit:.2f}", "SUCCESS")
            else:
                self.log_to_db(f"🔻 LOSS em {asset}.", "ERROR")
            
            # Atualiza o status do sinal na tabela
            if signal_id:
                try:
                    supabase.table("trade_signals").update({"result": result_str}).eq("id", signal_id).execute()
                except: pass

            # Atualizar Saldo na Config (para o Front ver o saldo real)
            try:
                curr_balance = self.api.get_balance()
                supabase.table("bot_config").update({"current_balance": curr_balance}).eq("id", 1).execute()
            except: pass

            self.active_trades.discard(asset)
        else:
            self.log_to_db(f"❌ Falha ao abrir ordem em {asset} (Mercado Fechado?)", "ERROR")
            # Remove o sinal pendente pois não foi aberto
            if signal_id:
                try:
                    supabase.table("trade_signals").delete().eq("id", signal_id).execute()
                except: pass

    def start(self):
        # Tenta conectar. Se falhar as credenciais, o loop não inicia.
        if not self.connect(): 
            return

        ASSETS = [
            "EURUSD-OTC", "GBPUSD-OTC", "USDJPY-OTC", "EURJPY-OTC", 
            "USDCHF-OTC", "AUDCAD-OTC", "NZDUSD-OTC", "EURGBP-OTC", 
            "AUDUSD-OTC", "USDMXN-OTC"
        ]

        self.log_to_db("🚀 Bot Iniciado! Aguardando comandos do painel...", "SUCCESS")
        
        last_scanner_update = 0

        while True:
            try:
                # 1. Sincronizar Configuração do Supabase (Frontend)
                self.fetch_config()
                
                # 2. Enviar "Batimento Cardíaco" e dados do Scanner para o Frontend
                if time.time() - last_scanner_update > 5:
                    # Tenta ler o preço real de um ativo para mostrar no painel
                    try:
                        candles = self.api.get_candles("EURUSD-OTC", 60, 1, int(time.time()))
                        real_price = candles[-1]['close'] if candles else 0.0
                    except:
                        real_price = 0.0 # Falha na leitura
                        
                    # Formato especial que o Frontend lê: ANALISE_DETALHADA::PAR::Preço:VALOR::RSI:VALOR
                    self.log_to_db(f"ANALISE_DETALHADA::EUR/USD-OTC::Preço:{real_price}::RSI:--", "SYSTEM")
                    last_scanner_update = time.time()

                # 3. Verificar se está PAUSADO pelo Frontend
                if self.config["status"] == "PAUSED":
                    time.sleep(2)
                    continue

                # 4. Verificar Conexão com Corretora
                if not self.api.check_connect():
                    self.log_to_db("⚠️ Conexão perdida com Exnova. Reconectando...", "WARNING")
                    if self.connect(): time.sleep(2)
                    else: time.sleep(10)
                    continue

                # 5. Estratégia e Operação
                now = datetime.now()
                # Verifica entrada apenas no início da vela (segundo 0-5)
                if now.second <= 5:
                    print(f"\n--- 🔎 Varredura {now.strftime('%H:%M:%S')} ---")
                    for asset in ASSETS:
                        if asset in self.blacklist or asset in self.active_trades: continue
                        
                        candles = self.get_candles_safe(asset)
                        if not candles or len(candles) < 30: continue
                        
                        signal = TechnicalAnalysis.get_signal(candles)
                        
                        if signal:
                            self.log_to_db(f"🔔 SINAL DETETADO: {asset} -> {signal.upper()}", "INFO")
                            self.execute_trade(asset, signal)
                            time.sleep(1) # Delay para evitar duplicados
                    
                    time.sleep(50) # Espera resto do minuto para não spammar
                
                time.sleep(1)

            except KeyboardInterrupt:
                print("\nParado manualmente.")
                break
            except Exception as e:
                print(f"Erro Loop Principal: {e}")
                time.sleep(5)

if __name__ == "__main__":
    bot = SimpleBot()
    bot.start()
