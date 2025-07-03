# services/exnova_service.py
import asyncio
import time
from exnovaapi.stable_api import Exnova
from typing import List, Dict, Optional
from core.data_models import Candle

class AsyncExnovaService:
    def __init__(self, email: str, password: str, account_type: str = "PRACTICE"):
        self.api = Exnova(email, password)
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
        self._account_type = balance_type # Guarda o tipo de conta para a reconexão
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

    async def check_trade_result(self, order_id: str) -> Optional[str]:
        """
        Espera a operação expirar e depois verifica o resultado usando a função 'check_win'.
        """
        loop = await self._get_loop()
        try:
            # FIX: A lógica de espera agora está aqui, no serviço.
            await asyncio.sleep(65)
            
            print(f"A verificar o resultado final da ordem {order_id}...", flush=True)
            api_call = loop.run_in_executor(None, self.api.check_win, order_id)
            result_data = await asyncio.wait_for(api_call, timeout=15.0) 
            
            if isinstance(result_data, tuple) and len(result_data) > 0:
                result_string = result_data[0]
                if result_string == 'win': return 'WIN'
                if result_string == 'loose': return 'LOSS'
                return result_string.upper() if result_string else "UNKNOWN"
            return "UNKNOWN"

        except asyncio.TimeoutError:
            print(f"Aviso: Timeout ao verificar a ordem {order_id}.", flush=True)
            return "UNKNOWN"
        except Exception as e:
            print(f"Erro inesperado ao verificar a ordem {order_id}: {e}", flush=True)
            return "UNKNOWN"
