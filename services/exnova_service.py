import asyncio
import time
from exnovaapi.stable_api import Exnova
from typing import List, Optional, Tuple
from core.data_models import Candle

class AsyncExnovaService:
    def __init__(self, email: str, password: str, account_type: str = "PRACTICE"):
        self.api = Exnova(email, password)
        self._account_type = account_type
        self._loop = None

    async def _get_loop(self) -> asyncio.AbstractEventLoop:
        if not self._loop:
            self._loop = asyncio.get_running_loop()
        return self._loop

    async def connect(self) -> bool:
        loop = await self._get_loop()
        status, reason = await loop.run_in_executor(None, self.api.connect)
        if status:
            print("Conexão com a Exnova estabelecida com sucesso.", flush=True)
            await self.change_balance(self._account_type)
        else:
            print(f"Falha na conexão com a Exnova: {reason}", flush=True)
        return status

    async def change_balance(self, balance_type: str):
        self._account_type = balance_type
        loop = await self._get_loop()
        await loop.run_in_executor(None, self.api.change_balance, balance_type)

    async def get_open_assets(self) -> List[str]:
        loop = await self._get_loop()
        open_times = await loop.run_in_executor(None, self.api.get_all_open_time)
        assets: List[str] = []
        for asset_type in ['binary', 'turbo']:
            if open_times and asset_type in open_times:
                assets += [
                    asset for asset, details in open_times[asset_type].items()
                    if details.get('open')
                ]
        return list(set(assets))

    async def get_historical_candles(
        self, asset: str, interval: int, count: int
    ) -> List[Candle]:
        loop = await self._get_loop()
        data = await loop.run_in_executor(
            None, self.api.get_candles, asset, interval, count, time.time()
        )
        return [Candle(**d) for d in data if d] if data else []

    async def execute_trade(
        self, amount: float, asset: str, direction: str, expiration: int
    ) -> Optional[str]:
        loop = await self._get_loop()
        status, order_id = await loop.run_in_executor(
            None, self.api.buy, amount, asset, direction, expiration
        )
        try:
            int(order_id)
            return str(order_id)
        except (ValueError, TypeError):
            print(f"Falha ao executar ordem para {asset}: {order_id}", flush=True)
            return None

    async def check_win_v4(
        self, order_id: str
    ) -> Optional[Tuple[bool, float]]:
        """
        Polling rápido: chama check_win_v4 e retorna (status_bool, profit),
        ou None em caso de erro.
        """
        loop = await self._get_loop()
        try:
            return await loop.run_in_executor(None, self.api.check_win_v4, order_id)
        except Exception as e:
            print(f"Erro inesperado em check_win_v4 para o order_id {order_id}: {e}", flush=True)
            return None
