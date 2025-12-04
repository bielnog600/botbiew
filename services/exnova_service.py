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
        except Exception:
            return 0.0

    async def change_balance(self, balance_type="PRACTICE"):
        try:
            await asyncio.to_thread(self.api.change_balance, balance_type)
        except Exception:
            pass

    async def get_open_assets(self):
        return ["EURUSD", "GBPUSD", "USDJPY", "EURJPY", "AUDCAD", "EURGBP", "USDCHF"]

    async def get_historical_candles(self, asset, timeframe_seconds, count):
        end_from_time = int(time.time())
        try:
            candles = await asyncio.to_thread(self.api.get_candles, asset, timeframe_seconds, count, end_from_time)
            
            # --- CORREÇÃO DEFINITIVA (Candle como Subclasse de Dict) ---
            class Candle(dict):
                def __init__(self, data):
                    # Garante conversão para float
                    safe_data = {
                        'open': float(data.get('open', 0)),
                        'close': float(data.get('close', 0)),
                        'high': float(data.get('max', data.get('high', 0))),
                        'low': float(data.get('min', data.get('low', 0))),
                        'max': float(data.get('max', data.get('high', 0))),
                        'min': float(data.get('min', data.get('low', 0))),
                        'volume': float(data.get('volume', 0)),
                        'at': data.get('at', 0),
                        'from': data.get('from', 0),
                        'to': data.get('to', 0),
                        'id': data.get('id', 0)
                    }
                    # Inicializa o dicionário (Crucial para o Pandas)
                    super().__init__(safe_data)
                    # Define atributos para acesso via ponto (Crucial para o Bot)
                    self.__dict__.update(safe_data)

                # Fallback para garantir acesso a atributos dinâmicos
                def __getattr__(self, name):
                    try:
                        return self[name]
                    except KeyError:
                        raise AttributeError(name)

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
            return None
        except Exception:
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
