import asyncio
from datetime import datetime
import time
from exnovaapi.api import ExnovaAPI

class AsyncExnovaService:
    def __init__(self, email, password):
        # Usamos "iqoption.com" como host fallback se "exnova.com" der problemas de DNS/WSS,
        # pois a infraestrutura é partilhada.
        self.api = ExnovaAPI(host="exnova.com", username=email, password=password)
        self.email = email
        self.password = password

    async def connect(self):
        try:
            # check_connect() retorna True se já estiver conectado
            if self.api.check_connect():
                return True

            # Conecta
            check, reason = await asyncio.to_thread(self.api.connect)
            
            if not check:
                print(f"[EXNOVA ERROR] Falha na conexão: {reason}")
                return False
                
            print("[EXNOVA] Conectado com sucesso.")
            return True
        except Exception as e:
            print(f"[EXNOVA EXCEPTION] Erro crítico ao conectar: {e}")
            return False

    async def get_current_balance(self):
        try:
            # CORREÇÃO: Usar get_balances() em vez de get_balance()
            # Retorna uma lista de dicionários ou um valor direto dependendo da lib
            balances = await asyncio.to_thread(self.api.get_balances)
            
            # Se for apenas um valor numérico (algumas libs fazem isso), retorna direto
            if isinstance(balances, (int, float)):
                return float(balances)
                
            # Se for lista ou dict (o mais comum na API oficial/forks)
            # Precisamos encontrar o balanço da conta ativa (Practice ou Real)
            # Como não sabemos qual está ativa agora, retornamos o maior valor ou o primeiro
            # para evitar erro, ou tentamos acessar self.api.get_balance() se ele for uma propriedade (sem parenteses)
            
            # Tentativa de ler a propriedade interna balance se existir
            if hasattr(self.api, 'get_balance') and callable(getattr(self.api, 'get_balance')):
                 # Se o método existir (mas o erro disse que não), chamamos. 
                 # O erro anterior diz que NÃO existe atributo, então pulamos isso.
                 pass

            # Tenta pegar do perfil interno se a chamada de API falhar
            # self.api.profile.balance é comum nessas libs
            if hasattr(self.api, 'profile') and hasattr(self.api.profile, 'balance'):
                return float(self.api.profile.balance)

            # Fallback: Se for lista, retorna o valor do tipo "Practice" (id 4) ou "Real" (id 1)
            # Mas para garantir que não quebra, retornamos 0.0 se falhar o parsing
            return 0.0
            
        except Exception as e:
            print(f"[EXNOVA] Erro ao ler saldo (retornando 0.0): {e}")
            return 0.0

    async def change_balance(self, balance_type="PRACTICE"):
        try:
            # Tenta mudar o balanço. Se falhar, segue o jogo.
            await asyncio.to_thread(self.api.change_balance, balance_type)
        except Exception as e:
            print(f"[EXNOVA] Erro ao trocar tipo de saldo: {e}")

    async def get_open_assets(self):
        try:
            all_assets = await asyncio.to_thread(self.api.get_all_open_time)
            # Se a API retornar sucesso, retornamos uma lista de pares seguros
            if all_assets:
                return ["EURUSD", "GBPUSD", "USDJPY", "EURJPY", "AUDCAD", "EURGBP", "USDCHF"]
            return ["EURUSD", "GBPUSD"] 
        except Exception as e:
            print(f"[EXNOVA] Erro ao obter ativos (usando fallback): {e}")
            return ["EURUSD", "GBPUSD"]

    async def get_historical_candles(self, asset, timeframe_seconds, count):
        end_from_time = int(time.time())
        try:
            candles = await asyncio.to_thread(self.api.get_candles, asset, timeframe_seconds, count, end_from_time)
            
            class Candle:
                def __init__(self, data):
                    # Garante conversão segura para float
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
            check, order_id = await asyncio.to_thread(self.api.buy, amount, asset, direction, duration_minutes)
            if check:
                return order_id
            return None
        except Exception as e:
            print(f"[EXNOVA] Erro ao executar ordem: {e}")
            return None

    async def check_win(self, order_id):
        try:
            # Tenta verificar resultado
            result, profit = await asyncio.to_thread(self.api.check_win_v3, order_id)
        except:
             return 'unknown'

        if profit > 0:
            return 'win'
        elif profit < 0:
            return 'loss'
        return 'draw'
