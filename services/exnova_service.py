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

    async def _get_loop(self):
        if self._loop is None:
            self._loop = asyncio.get_running_loop()
        return self._loop

    async def connect(self) -> bool:
        loop = await self._get_loop()
        status, reason = await loop.run_in_executor(None, self.api.connect)
        return status

    async def change_balance(self, balance_type: str):
        self._account_type = balance_type
        loop = await self._get_loop()
        await loop.run_in_executor(None, self.api.change_balance, balance_type)

    async def get_current_balance(self) -> Optional[float]:
        loop = await self._get_loop()
        try:
            bal = await loop.run_in_executor(None, self.api.get_balance)
            return float(bal) if bal is not None else None
        except Exception:
            return None

    async def get_open_assets(self) -> List[str]:
        loop = await self._get_loop()
        open_times = await loop.run_in_executor(None, self.api.get_all_open_time)
        assets = []
        for t in ['binary','turbo']:
            if open_times and t in open_times:
                assets += [a for a,d in open_times[t].items() if d.get('open')]
        return list(set(assets))

    async def get_historical_candles(self, asset: str, interval: int, count: int) -> List[Candle]:
        loop = await self._get_loop()
        data = await loop.run_in_executor(None, self.api.get_candles, asset, interval, count, time.time())
        return [Candle(**c) for c in data] if data else []

    async def execute_trade(self, amount: float, asset: str, direction: str, expiration: int) -> Optional[str]:
        loop = await self._get_loop()
        status, order_id = await loop.run_in_executor(None, self.api.buy, amount, asset, direction, expiration)
        try:
            int(order_id)
            return str(order_id)
        except Exception:
            return None

    async def check_win_v4(self, order_id: str) -> Tuple[Optional[bool], Optional[float]]:
        """
        Retorna (status_bool, profit):
         - status_bool: True=win, False=loss, None=ainda não expirou
         - profit: float (positivo para win, negativo para loss)
        """
        loop = await self._get_loop()
        return await loop.run_in_executor(None, self.api.check_win_v4, order_id)
