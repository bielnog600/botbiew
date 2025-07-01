# services/exnova_service.py
import asyncio
from exnovaapi.stable_api import Exnova
from typing import List, Dict, Optional
from core.data_models import Candle

# Simulação de uma classe assíncrona da API
# A API real `exnovaapi` é síncrona, então usamos `run_in_executor` para não bloquear o loop de eventos.
class AsyncExnovaService:
    """
    Wrapper assíncrono para a API da Exnova, com lógica de reconexão.
    """
    def __init__(self, email: str, password: str, account_type: str = "PRACTICE"):
        self._email = email
        self._password = password
        self._account_type = account_type
        self.api = Exnova(email, password)
        self._is_connected = False
        self._loop = asyncio.get_event_loop()

    async def connect(self):
        # Executa a conexão síncrona em um thread separado
        print("Conectando à Exnova...")
        status, reason = await self._loop.run_in_executor(None, self.api.connect)
        if status:
            self._is_connected = True
            print("Conexão com a Exnova estabelecida com sucesso.")
            await self.change_balance(self._account_type)
        else:
            self._is_connected = False
            print(f"Falha na conexão com a Exnova: {reason}")
        return self._is_connected

    async def change_balance(self, balance_type: str):
        await self._loop.run_in_executor(None, self.api.change_balance, balance_type)
        print(f"Balança alterada para: {balance_type}")

    async def get_open_assets(self) -> List[str]:
        open_times = await self._loop.run_in_executor(None, self.api.get_all_open_time)
        assets = []
        for asset_type in ['binary', 'turbo']:
            if asset_type in open_times:
                assets.extend([asset for asset, details in open_times[asset_type].items() if details.get('open')])
        return list(set([asset.split('-')[0] for asset in assets])) # Retorna nomes limpos e únicos

    async def get_historical_candles(self, asset: str, interval: int, count: int) -> List[Candle]:
        # A API real pode precisar de um endtime
        candles_data = await self._loop.run_in_executor(None, self.api.get_candles, asset, interval, count, time.time())
        return [Candle(**data) for data in candles_data]

    async def execute_trade(self, amount: float, asset: str, direction: str, expiration: int) -> Optional[str]:
        status, order_id = await self._loop.run_in_executor(None, self.api.buy, amount, asset, direction, expiration)
        if status:
            return order_id
        print(f"Falha ao executar ordem para {asset}: {order_id}")
        return None

    async def check_trade_result(self, order_id: str) -> Optional[str]:
        result, _ = await self._loop.run_in_executor(None, self.api.check_win_v4, order_id)
        return result.upper() if result else None
