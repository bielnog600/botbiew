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
        # Lista estática para garantir funcionamento
        return ["EURUSD", "GBPUSD", "USDJPY", "EURJPY", "AUDCAD", "EURGBP", "USDCHF"]

    async def get_historical_candles(self, asset, timeframe_seconds, count):
        end_from_time = int(time.time())
        try:
            candles = await asyncio.to_thread(self.api.get_candles, asset, timeframe_seconds, count, end_from_time)
            
            # --- CORREÇÃO DEFINITIVA (Dict + __getattr__) ---
            class Candle(dict):
                def __init__(self, data):
                    # Garante que 'high' e 'low' existem para o Pandas
                    high = float(data.get('max', data.get('high', 0)))
                    low = float(data.get('min', data.get('low', 0)))
                    
                    safe_data = {
                        'open': float(data.get('open', 0)),
                        'close': float(data.get('close', 0)),
                        'high': high,
                        'low': low,
                        'max': high, # Compatibilidade
                        'min': low,  # Compatibilidade
                        'volume': float(data.get('volume', 0)),
                        'at': data.get('at', 0),
                        'from': data.get('from', 0),
                        'to': data.get('to', 0),
                        'id': data.get('id', 0)
                    }
                    super().__init__(safe_data)

                # Permite acesso via ponto (candle.open) redirecionando para o dict
                def __getattr__(self, item):
                    try:
                        return self[item]
                    except KeyError:
                        raise AttributeError(f"'Candle' object has no attribute '{item}'")

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
