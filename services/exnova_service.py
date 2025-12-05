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
            # Tenta conectar usando a stable_api
            # O método connect retorna (True/False, Mensagem)
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
        """Verifica se a conexão WebSocket está ativa."""
        try:
            # Se a stable_api tiver método de check, usa-o.
            if hasattr(self.api, 'check_connect'):
                return self.api.check_connect()
            
            # Se não, assumimos True se não houver erro óbvio
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
        # Retorna lista estática para garantir funcionamento imediato 
        # e evitar erros de atributos dinâmicos não carregados.
        return ["EURUSD", "GBPUSD", "USDJPY", "EURJPY", "AUDCAD", "EURGBP", "USDCHF"]

    async def get_historical_candles(self, asset, timeframe_seconds, count):
        end_from_time = int(time.time())
        try:
            candles = await asyncio.to_thread(self.api.get_candles, asset, timeframe_seconds, count, end_from_time)
            
            # --- CORREÇÃO HÍBRIDA (Dict + Objeto) ---
            # Resolve o erro "Candle is not iterable" e "arg must be a list..."
            class Candle(dict):
                def __init__(self, data):
                    # Normaliza dados (garante float e chaves padrão financeiras)
                    safe_data = {
                        'open': float(data.get('open', 0)),
                        'close': float(data.get('close', 0)),
                        'high': float(data.get('max', 0)), # Vital para Pandas (high)
                        'low': float(data.get('min', 0)),  # Vital para Pandas (low)
                        'max': float(data.get('max', 0)),
                        'min': float(data.get('min', 0)),
                        'volume': float(data.get('volume', 0)),
                        'at': data.get('at', 0),
                        'from': data.get('from', 0),
                        'to': data.get('to', 0),
                        'id': data.get('id', 0)
                    }
                    
                    # 1. Inicializa como Dicionário (para análise técnica/Pandas)
                    super().__init__(safe_data)
                    
                    # 2. Inicializa como Objeto (para o Bot acessar via ponto ex: candle.close)
                    self.__dict__.update(safe_data)

            # Converte a lista crua em objetos Candle compatíveis
            return [Candle(c) for c in candles] if candles else []
            
        except Exception as e:
            print(f"[EXNOVA] Erro ao obter velas para {asset}: {e}")
            return []

    async def execute_trade(self, amount, asset, direction, duration_minutes):
        try:
            action = direction.lower()
            
            # Executa a ordem na thread separada (método bloqueante na lib)
            result, order_id = await asyncio.to_thread(
                self.api.buy, 
                float(amount), 
                asset, 
                action, 
                int(duration_minutes)
            )
            
            # Verifica se o ID retornado é válido (inteiro)
            if order_id and isinstance(order_id, int):
                return order_id
            
            # Se não for int, geralmente é msg de erro ou None
            return None
            
        except Exception:
            return None

    async def check_win(self, order_id):
        try:
            # Verifica o resultado da operação
            status, profit = await asyncio.to_thread(self.api.check_win_v3, order_id)
            
            if status == 'equal':
                return 'draw'
            elif status == 'loose':
                return 'loss'
            elif status == 'win':
                return 'win'
            
            return 'unknown'
        except Exception:
             return 'unknown'
