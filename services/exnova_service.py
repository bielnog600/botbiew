import asyncio
import time
import pandas as pd
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

    async def is_connected(self):
        try:
            if hasattr(self.api, 'check_connect'):
                return self.api.check_connect()
            return True 
        except Exception:
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
        # Lista estática para evitar erros de carregamento
        return ["EURUSD", "GBPUSD", "USDJPY", "EURJPY", "AUDCAD", "EURGBP", "USDCHF"]

    async def get_historical_candles(self, asset, timeframe_seconds, count):
        end_from_time = int(time.time())
        try:
            candles = await asyncio.to_thread(self.api.get_candles, asset, timeframe_seconds, count, end_from_time)
            
            if not candles:
                return []

            # --- CORREÇÃO BALA DE PRATA: Pandas Series ---
            # O Pandas Series funciona como Dicionário E como Objeto.
            # É o formato nativo que a análise técnica espera.
            formatted_candles = []
            for c in candles:
                data = {
                    'open': float(c.get('open', 0)),
                    'close': float(c.get('close', 0)),
                    'high': float(c.get('max', c.get('high', 0))), # Garante 'high'
                    'low': float(c.get('min', c.get('low', 0))),   # Garante 'low'
                    'max': float(c.get('max', 0)),
                    'min': float(c.get('min', 0)),
                    'volume': float(c.get('volume', 0)),
                    'at': c.get('at', 0),
                    'id': c.get('id', 0)
                }
                # Cria uma Series do Pandas para cada vela
                formatted_candles.append(pd.Series(data))
            
            return formatted_candles

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
