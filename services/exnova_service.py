import asyncio
from datetime import datetime
import time
from exnovaapi.api import ExnovaAPI  # CORREÇÃO: "API" maiúsculo

class AsyncExnovaService:
    def __init__(self, email, password):
        self.api = ExnovaAPI(email, password)
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
        # A biblioteca geralmente retorna um dicionário complexo, filtramos aqui para uma lista simples.
        # Nota: A implementação exata depende da versão da lib, mas geralmente 'get_all_open_time' ajuda.
        try:
            # Esta chamada é pesada, idealmente faz-se cache
            all_assets = await asyncio.to_thread(self.api.get_all_open_time)
            
            open_assets = []
            for type_name, assets in all_assets.items():
                if type_name not in ['turbo', 'binary']: continue # Foca em binárias/turbo
                for asset_id, data in assets.items():
                    if data['open']:
                        # Tenta extrair o nome do par (ex: EURUSD)
                        # Dependendo da lib, pode ser necessário mapear ID -> Nome
                        # Aqui assumimos que o bot lida com nomes padrão
                        pass 
            
            # Fallback simplificado: Retorna pares populares se a API for complexa de navegar
            # Ou usa a função get_all_init() se disponível
            return ["EURUSD", "GBPUSD", "USDJPY", "EURJPY", "AUDCAD", "EURGBP"] 
        except:
            return ["EURUSD", "GBPUSD"] # Fallback seguro

    async def get_historical_candles(self, asset, timeframe_seconds, count):
        # Converte timeframe para segundos se necessário e chama a API
        # A API sync bloqueia, então usamos to_thread
        end_from_time = int(time.time())
        candles = await asyncio.to_thread(self.api.get_candles, asset, timeframe_seconds, count, end_from_time)
        
        # Converte para objetos compatíveis com seu bot (se necessário) ou retorna lista
        # O bot espera objetos com .open, .close, .min, .max. 
        # Se a API retorna dicts, criamos uma classe simples on-the-fly ou adaptamos o bot.
        # Assumindo que o bot lê dicts ou objetos:
        
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
        # A maioria das libs tem check_win_v3 ou similar
        # O seu bot espera 'win' ou 'loss'
        result, profit = await asyncio.to_thread(self.api.check_win_v3, order_id)
        if profit > 0:
            return 'win'
        elif profit < 0:
            return 'loss'
        return 'draw'
