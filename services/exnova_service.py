import asyncio
import time
from datetime import datetime
# Importamos a classe Wrapper 'Exnova' da stable_api
# Ela já gere o host correto e a reconexão automática
from exnovaapi.stable_api import Exnova

class AsyncExnovaService:
    def __init__(self, email, password):
        # Inicializa a classe Exnova (wrapper estável)
        # Ela já define internamente o host "ws.trade.exnova.com" ou "iqoption.com"
        # dependendo da versão, garantindo a conexão correta.
        self.api = Exnova(email=email, password=password)
        self.email = email
        self.password = password

    async def connect(self):
        try:
            # O método connect da stable_api retorna uma tupla (Sucesso, Razão/None)
            # Usamos to_thread para rodar a operação síncrona sem bloquear o bot
            check, reason = await asyncio.to_thread(self.api.connect)
            
            if check:
                print("[EXNOVA] Conectado com sucesso (Stable API).")
                return True
            else:
                print(f"[EXNOVA ERROR] Falha na conexão: {reason}")
                return False

        except Exception as e:
            print(f"[EXNOVA EXCEPTION] Erro crítico ao conectar: {e}")
            return False

    async def get_current_balance(self):
        try:
            # A stable_api tem um método get_balance() que trata da lógica de IDs
            bal = await asyncio.to_thread(self.api.get_balance)
            # Garante que retorna um float, mesmo que seja None ou string
            if bal is None:
                return 0.0
            return float(bal)
        except Exception as e:
            print(f"[EXNOVA] Erro ao ler saldo: {e}")
            return 0.0

    async def change_balance(self, balance_type="PRACTICE"):
        try:
            # A stable_api aceita "PRACTICE", "REAL", "TOURNAMENT"
            await asyncio.to_thread(self.api.change_balance, balance_type)
        except Exception as e:
            print(f"[EXNOVA] Erro ao trocar tipo de saldo: {e}")

    async def get_open_assets(self):
        try:
            # A stable_api carrega ativos na inicialização dentro de self.api.active_opcodes
            # Se a lista estiver vazia, tentamos forçar uma atualização chamando update_actives()
            # (Nota: update_actives é síncrono na stable_api)
            if not self.api.active_opcodes:
                await asyncio.to_thread(self.api.update_actives)

            if self.api.active_opcodes:
                # Retorna os nomes dos ativos (chaves do dicionário de ativos)
                return list(self.api.active_opcodes.keys())
            
            # Fallback seguro caso a lista dinâmica falhe
            return ["EURUSD", "GBPUSD", "USDJPY", "EURJPY", "AUDCAD", "EURGBP"]
        except Exception as e:
            print(f"[EXNOVA] Erro ao obter ativos: {e}")
            return ["EURUSD", "GBPUSD"]

    async def get_historical_candles(self, asset, timeframe_seconds, count):
        # A stable_api.get_candles espera (ativo, intervalo, quantidade, timestamp_fim)
        end_from_time = int(time.time())
        try:
            # Chama o método da stable_api
            candles = await asyncio.to_thread(self.api.get_candles, asset, timeframe_seconds, count, end_from_time)
            
            # Classe auxiliar para padronizar o retorno para o bot
            class Candle:
                def __init__(self, data):
                    # A stable_api retorna dicionários. Convertemos com segurança.
                    self.open = float(data.get('open', 0))
                    self.close = float(data.get('close', 0))
                    self.max = float(data.get('max', 0))
                    self.min = float(data.get('min', 0))
            
            return [Candle(c) for c in candles] if candles else []
        except Exception as e:
            print(f"[EXNOVA] Erro ao obter velas para {asset}: {e}")
            return []

    async def execute_trade(self, amount, asset, direction, duration_minutes):
        try:
            # Mapeia a direção do bot ("call"/"put") para o formato esperado ("call"/"put" ou "C"/"P")
            # A função buy da stable_api converte internamente se necessário
            action = direction.lower()
            
            # A função buy da stable_api tem a assinatura: buy(price, ACTIVES, ACTION, expirations)
            # E retorna: (resultado_api, order_id)
            result, order_id = await asyncio.to_thread(
                self.api.buy, 
                float(amount), 
                asset, 
                action, 
                int(duration_minutes)
            )
            
            # Verifica se retornou um ID válido (int)
            if order_id and isinstance(order_id, int):
                return order_id
            
            print(f"[EXNOVA] Erro na API ao executar trade: {order_id} (msg de erro)")
            return None
            
        except Exception as e:
            print(f"[EXNOVA] Exceção ao executar ordem: {e}")
            return None

    async def check_win(self, order_id):
        try:
            # A stable_api possui check_win_v3 que retorna (status, lucro)
            # O status pode ser 'win', 'loose' ou 'equal'
            status, profit = await asyncio.to_thread(self.api.check_win_v3, order_id)
            
            if status == 'equal':
                return 'draw' # Bot pode tratar como loss ou draw dependendo da lógica
            elif status == 'loose':
                return 'loss'
            elif status == 'win':
                return 'win'
            return 'unknown'
        except Exception as e:
             print(f"[EXNOVA] Erro ao checar resultado: {e}")
             return 'unknown'
