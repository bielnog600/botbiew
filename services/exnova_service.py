import asyncio
from datetime import datetime
import time
from exnovaapi.api import ExnovaAPI

class AsyncExnovaService:
    def __init__(self, email, password):
        # Usamos host e argumentos nomeados para garantir a correta atribuição
        # "exnova.com" é o host padrão
        self.api = ExnovaAPI(host="exnova.com", username=email, password=password)
        self.email = email
        self.password = password

    async def connect(self):
        try:
            # CORREÇÃO: Removemos self.api.check_connect() pois não existe nesta versão da lib.
            # Chamamos connect() diretamente. Ele retorna (True, None) se sucesso ou (False, "erro") se falha.
            check, reason = await asyncio.to_thread(self.api.connect)
            
            if check:
                print("[EXNOVA] Conectado com sucesso.")
                return True
            else:
                print(f"[EXNOVA ERROR] Falha na conexão: {reason}")
                return False

        except Exception as e:
            print(f"[EXNOVA EXCEPTION] Erro crítico ao conectar: {e}")
            return False

    async def get_current_balance(self):
        try:
            # Tenta obter saldo de várias formas para garantir compatibilidade com diferentes versões da lib
            
            # 1. Tenta get_balance() direto (algumas versões)
            if hasattr(self.api, 'get_balance') and callable(self.api.get_balance):
                bal = await asyncio.to_thread(self.api.get_balance)
                return float(bal)
            
            # 2. Tenta acessar via profile.balance (comum em forks da iqoptionapi)
            if hasattr(self.api, 'profile') and hasattr(self.api.profile, 'balance'):
                return float(self.api.profile.balance)

            # 3. Tenta get_balances() (plural) que retorna lista de contas
            if hasattr(self.api, 'get_balances'):
                balances = await asyncio.to_thread(self.api.get_balances)
                # Se retornar lista/dict, não temos como saber qual é a ativa facilmente sem mais lógica
                # Retornamos 0.0 por segurança para o bot continuar rodando
                return 0.0

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
            # get_all_open_time retorna um dicionário complexo
            all_assets = await asyncio.to_thread(self.api.get_all_open_time)
            
            # Se a API retornar sucesso (dicionário não vazio), retornamos uma lista fixa de pares seguros.
            # Parsing da estrutura completa em tempo real é propenso a erros se a API mudar.
            if all_assets:
                return ["EURUSD", "GBPUSD", "USDJPY", "EURJPY", "AUDCAD", "EURGBP", "USDCHF"]
            
            # Fallback
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
                    # Garante conversão segura para float e usa .get para evitar KeyError
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
            # Tenta verificar resultado usando v3
            result, profit = await asyncio.to_thread(self.api.check_win_v3, order_id)
        except:
             return 'unknown'

        if profit > 0:
            return 'win'
        elif profit < 0:
            return 'loss'
        return 'draw'
