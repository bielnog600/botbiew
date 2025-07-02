# services/exnova_service.py
import asyncio
import time
from exnovaapi.stable_api import Exnova
from typing import List, Dict, Optional
from core.data_models import Candle

class AsyncExnovaService:
    """Wrapper assíncrono para a API da Exnova, com lógica de reconexão e timeouts."""
    def __init__(self, email: str, password: str, account_type: str = "PRACTICE"):
        self._email = email
        self._password = password
        self._account_type = account_type
        self.api = Exnova(email, password)
        self._is_connected = False
        self._loop = None

    async def _get_loop(self):
        if self._loop is None: self._loop = asyncio.get_running_loop()
        return self._loop

    async def connect(self):
        loop = await self._get_loop()
        print(f"Conectando à Exnova...")
        status, reason = await loop.run_in_executor(None, self.api.connect)
        if status:
            self._is_connected = True
            print("Conexão com a Exnova estabelecida com sucesso.")
            await self.change_balance(self._account_type)
        else:
            self._is_connected = False
            print(f"Falha na conexão com a Exnova: {reason}")
        return self._is_connected

    async def change_balance(self, balance_type: str):
        loop = await self._get_loop()
        await loop.run_in_executor(None, self.api.change_balance, balance_type)

    async def get_current_balance(self) -> Optional[float]:
        loop = await self._get_loop()
        try:
            balance = await loop.run_in_executor(None, self.api.get_balance)
            return float(balance) if balance else None
        except Exception as e:
            print(f"Erro ao obter saldo da API: {e}")
            return None

    async def get_open_assets(self) -> List[str]:
        loop = await self._get_loop()
        open_times = await loop.run_in_executor(None, self.api.get_all_open_time)
        assets = []
        for asset_type in ['binary', 'turbo']:
            if open_times and asset_type in open_times:
                assets.extend([asset for asset, details in open_times[asset_type].items() if details.get('open')])
        return list(set(assets))

    async def get_historical_candles(self, asset: str, interval: int, count: int) -> List[Candle]:
        loop = await self._get_loop()
        candles_data = await loop.run_in_executor(None, self.api.get_candles, asset, interval, count, time.time())
        if candles_data is None: return []
        return [Candle(**data) for data in candles_data if data]

    async def execute_trade(self, amount: float, asset: str, direction: str, expiration: int) -> Optional[str]:
        loop = await self._get_loop()
        status, order_id = await loop.run_in_executor(None, self.api.buy, amount, asset, direction, expiration)
        if status: return str(order_id)
        print(f"Falha ao executar ordem para {asset}: {order_id}")
        return None

    async def check_trade_result(self, order_id: str) -> Optional[str]:
        """
        Verifica o resultado de uma operação com um timeout de segurança.
        Isto impede que o bot "congele" se a API não responder.
        """
        loop = await self._get_loop()
        try:
            # FIX: Envolve a chamada da API num 'wait_for' com um timeout de 10 segundos.
            api_call = loop.run_in_executor(None, self.api.check_win_v4, order_id)
            result, _ = await asyncio.wait_for(api_call, timeout=10.0)
            
            return result.upper() if result else None
        except asyncio.TimeoutError:
            print(f"Aviso: Timeout ao verificar a ordem {order_id}. A API não respondeu a tempo.")
            return None
        except Exception as e:
            print(f"Erro inesperado ao verificar a ordem {order_id}: {e}")
            return None
