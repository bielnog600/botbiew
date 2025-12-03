import asyncio
import time
from datetime import datetime
from exnovaapi.stable_api import Exnova

class AsyncExnovaService:
    def __init__(self, email, password):
        # Inicializa a API (Wrapper Estável)
        self.api = Exnova(email=email, password=password)
        self.email = email
        self.password = password

    async def connect(self):
        try:
            # Conecta de forma assíncrona para não bloquear o bot
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
        # Retorna lista estática para evitar erro de atributo inexistente na lib
        return ["EURUSD", "GBPUSD", "USDJPY", "EURJPY", "AUDCAD", "EURGBP", "USDCHF"]

    async def get_historical_candles(self, asset, timeframe_seconds, count):
        end_from_time = int(time.time())
        try:
            candles = await asyncio.to_thread(self.api.get_candles, asset, timeframe_seconds, count, end_from_time)
            
            # --- CORREÇÃO CRÍTICA ---
            # A classe Candle HERDA de dict. 
            # Isso permite que bibliotecas como Pandas convertam a lista de velas em DataFrame.
            class Candle(dict):
                def __init__(self, data):
                    # Normaliza os dados
                    safe_data = {
                        'open': float(data.get('open', 0)),
                        'close': float(data.get('close', 0)),
                        'high': float(data.get('max', 0)), # Renomeia max -> high
                        'low': float(data.get('min', 0)),  # Renomeia min -> low
                        'max': float(data.get('max', 0)),
                        'min': float(data.get('min', 0)),
                        'volume': float(data.get('volume', 0)),
                        'at': data.get('at', 0),
                        'from': data.get('from', 0),
                        'to': data.get('to', 0),
                        'id': data.get('id', 0)
                    }
                    # 1. Inicializa como dicionário (para o Pandas ler)
                    super().__init__(safe_data)
                    
                    # 2. Define atributos (para o bot ler: candle.close)
                    self.open = safe_data['open']
                    self.close = safe_data['close']
                    self.high = safe_data['high']
                    self.low = safe_data['low']
                    self.max = safe_data['max']
                    self.min = safe_data['min']
                    self.volume = safe_data['volume']
            
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
