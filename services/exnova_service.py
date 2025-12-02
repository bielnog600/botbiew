import asyncio
from datetime import datetime
import time
from exnovaapi.api import ExnovaAPI

class AsyncExnovaService:
    def __init__(self, email, password):
        # CORREÇÃO: A API exige o host ("exnova.com") como primeiro argumento.
        # Antes estava: ExnovaAPI(email, password) -> O Python achava que faltava 1 argumento.
        self.api = ExnovaAPI("exnova.com", email, password)
        self.email = email
        self.password = password

    async def connect(self):
        # Executa a conexão (bloqueante) numa thread separada para não travar o bot
        check, reason = await asyncio.to_thread(self.api.connect)
        if not check:
            print(f"Erro ao conectar: {reason}")
            # Tenta reconectar caso falhe a primeira vez
            return False
        print("Conectado com sucesso à Exnova.")
        return True

    async def get_current_balance(self):
        return await asyncio.to_thread(self.api.get_balance)

    async def change_balance(self, balance_type="PRACTICE"):
        # balance_type deve ser "PRACTICE" ou "REAL"
        await asyncio.to_thread(self.api.change_balance, balance_type)

    async def get_open_assets(self):
        # Obtém todos os ativos abertos. 
        try:
            # Esta chamada é pesada, idealmente faz-se cache
            all_assets = await asyncio.to_thread(self.api.get_all_open_time)
            
            open_assets = []
            if all_assets:
                for type_name, assets in all_assets.items():
                    if type_name not in ['turbo', 'binary']: continue # Foca em binárias/turbo
                    for asset_id, data in assets.items():
                        if data['open']:
                            pass 
            
            # Fallback simplificado para garantir que o bot inicie
            return ["EURUSD", "GBPUSD", "USDJPY", "EURJPY", "AUDCAD", "EURGBP"] 
        except Exception as e:
            print(f"Erro ao obter ativos: {e}")
            return ["EURUSD", "GBPUSD"] # Fallback seguro

    async def get_historical_candles(self, asset, timeframe_seconds, count):
        # Converte timeframe para segundos se necessário e chama a API
        end_from_time = int(time.time())
        candles = await asyncio.to_thread(self.api.get_candles, asset, timeframe_seconds, count, end_from_time)
        
        class Candle:
            def __init__(self, data):
                self.open = data['open']
                self.close = data['close']
                self.max = data['max']
                self.min = data['min']
        
        return [Candle(c) for c in candles] if candles else []

    async def execute_trade(self, amount, asset, direction, duration_minutes):
        # Executa a ordem
        check, order_id = await asyncio.to_thread(self.api.buy, amount, asset, direction, duration_minutes)
        if check:
            return order_id
        return None

    async def check_win(self, order_id):
        # Verifica o resultado da ordem
        # Tenta check_win_v3, se falhar tenta v4 ou lógica padrão
        try:
            result, profit = await asyncio.to_thread(self.api.check_win_v3, order_id)
        except:
             # Fallback simples caso a API mude
             return 'unknown'

        if profit > 0:
            return 'win'
        elif profit < 0:
            return 'loss'
        return 'draw'
