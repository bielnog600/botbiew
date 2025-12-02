import asyncio
import time
from datetime import datetime
from exnovaapi.stable_api import Exnova

class AsyncExnovaService:
    def __init__(self, email, password):
        self.api = Exnova(email=email, password=password)
        self.email = email
        self.password = password

    async def connect(self):
        try:
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
            bal = await asyncio.to_thread(self.api.get_balance)
            return float(bal) if bal is not None else 0.0
        except Exception as e:
            print(f"[EXNOVA] Erro ao ler saldo: {e}")
            return 0.0

    async def change_balance(self, balance_type="PRACTICE"):
        try:
            await asyncio.to_thread(self.api.change_balance, balance_type)
        except Exception:
            pass

    async def get_open_assets(self):
        # CORREÇÃO: Retorna lista estática para evitar erro de atributo inexistente na lib
        return ["EURUSD", "GBPUSD", "USDJPY", "EURJPY", "AUDCAD", "EURGBP", "USDCHF"]

    async def get_historical_candles(self, asset, timeframe_seconds, count):
        end_from_time = int(time.time())
        try:
            candles = await asyncio.to_thread(self.api.get_candles, asset, timeframe_seconds, count, end_from_time)
            
            # CORREÇÃO: Herdar de dict para ser iterável (resolve o erro da análise técnica)
            class Candle(dict):
                def __init__(self, data):
                    super().__init__(data) # Inicializa como dict
                    # Define atributos para acesso via ponto (usado pelo bot)
                    self.open = float(data.get('open', 0))
                    self.close = float(data.get('close', 0))
                    self.max = float(data.get('max', 0))
                    self.min = float(data.get('min', 0))
                    # Alias úteis
                    self.high = self.max
                    self.low = self.min
            
            return [Candle(c) for c in candles] if candles else []
        except Exception as e:
            print(f"[EXNOVA] Erro ao obter velas para {asset}: {e}")
            return []

    async def execute_trade(self, amount, asset, direction, duration_minutes):
        try:
            action = direction.lower()
            result, order_id = await asyncio.to_thread(
                self.api.buy, 
                float(amount), 
                asset, 
                action, 
                int(duration_minutes)
            )
            
            if order_id and isinstance(order_id, int):
                return order_id
            
            print(f"[EXNOVA] Erro ao executar trade: {order_id}")
            return None
            
        except Exception as e:
            print(f"[EXNOVA] Exceção ao executar ordem: {e}")
            return None

    async def check_win(self, order_id):
        try:
            status, profit = await asyncio.to_thread(self.api.check_win_v3, order_id)
            if status == 'equal': return 'draw'
            elif status == 'loose': return 'loss'
            elif status == 'win': return 'win'
            return 'unknown'
        except Exception:
             return 'unknown'
