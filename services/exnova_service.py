# services/exnova_service.py
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
        if self._loop is None: self._loop = asyncio.get_running_loop()
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
        loop = await self._get_loop()
        try:
            balance = await loop.run_in_executor(None, self.api.get_balance)
            return float(balance) if balance else None
        except Exception as e:
            print(f"Erro ao obter saldo da API: {e}", flush=True)
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
        return [Candle(**data) for data in candles_data if data] if candles_data else []

    async def execute_trade(self, amount: float, asset: str, direction: str, expiration: int) -> Optional[str]:
        loop = await self._get_loop()
        status, order_id = await loop.run_in_executor(None, self.api.buy, amount, asset, direction, expiration)
        if order_id:
            return str(order_id)
        print(f"Falha ao executar ordem para {asset}: {order_id}", flush=True)
        return None

    async def check_trade_result(self, order_id: str, expiration: int = 1) -> Optional[str]:
        """
        Polling contínuo até o trade expirar (expiration em minutos) + 15 s de margem.
        Retorna 'WIN' ou 'LOSS' assim que a API indicar status=True.
        Retorna None se estourar o prazo.
        """
        loop = await self._get_loop()
        # calcula deadline em UNIX time
        deadline = time.time() + expiration * 60 + 15

        while time.time() < deadline:
            # chama a versão certa do check_win
            if self._account_type.lower() == 'digital':
                status, profit = await loop.run_in_executor(
                    None, self.api.check_win_digital_v2, order_id
                )
            else:
                status, profit = await loop.run_in_executor(
                    None, self.api.check_win_v4, order_id
                )

            if status:
                # devolve WIN/LOSS com base no lucro
                return 'WIN' if profit > 0 else 'LOSS'

            # aguarda 0.5 s antes de tentar de novo
            await asyncio.sleep(0.5)

    # nunca obteve status=True antes do prazo
        return None


