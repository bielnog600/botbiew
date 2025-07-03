import asyncio
import time
from exnovaapi.stable_api import Exnova
from typing import List, Dict, Optional
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

    async def connect(self):
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

    async def get_current_balance(self) -> Optional[float]:
        """Retorna o saldo atual da conta."""
        loop = await self._get_loop()
        try:
            bal = await loop.run_in_executor(None, self.api.get_balance)
            return float(bal) if bal is not None else None
        except Exception as e:
            print(f"Erro ao obter saldo da API: {e}", flush=True)
            return None

    async def get_open_assets(self) -> List[str]:
        loop = await self._get_loop()
        open_times = await loop.run_in_executor(None, self.api.get_all_open_time)
        assets = []
        for t in ['binary', 'turbo']:
            if open_times and t in open_times:
                assets += [asset for asset, d in open_times[t].items() if d.get('open')]
        return list(set(assets))

    async def get_historical_candles(self, asset: str, interval: int, count: int) -> List[Candle]:
        loop = await self._get_loop()
        data = await loop.run_in_executor(None, self.api.get_candles, asset, interval, count, time.time())
        return [Candle(**c) for c in data] if data else []

    async def execute_trade(self, amount: float, asset: str, direction: str, expiration: int) -> Optional[str]:
        loop = await self._get_loop()
        status, order_id = await loop.run_in_executor(None, self.api.buy, amount, asset, direction, expiration)
        if order_id:
            return str(order_id)
        print(f"Falha ao executar ordem para {asset}: {order_id}", flush=True)
        return None

    async def check_win_v4(self, order_id: str) -> Optional[tuple]:
        loop = await self._get_loop()
        try:
            await asyncio.sleep(65)  # espera operação de 1min + buffer
            data = await loop.run_in_executor(None, self.api.check_win_v4, order_id)
            return data
        except Exception as e:
            print(f"Erro em check_win_v4({order_id}): {e}", flush=True)
            return None
