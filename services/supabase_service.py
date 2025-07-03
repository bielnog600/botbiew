import asyncio
from supabase import create_client, Client
from typing import Dict, Any, Optional
from core.data_models import TradeSignal
from config import settings

class SupabaseService:
    def __init__(self, url: str, key: str):
        self._url = url
        self._key = key
        self._loop = None
        print("Serviço Supabase inicializado.")

    def _create_client(self) -> Client:
        return create_client(self._url, self._key)

    async def _get_loop(self):
        if self._loop is None:
            self._loop = asyncio.get_running_loop()
        return self._loop

    async def get_bot_config(self) -> Dict[str, Any]:
        loop = await self._get_loop()
        resp = await loop.run_in_executor(
            None,
            lambda: self._create_client()
                .table('bot_config')
                .select('*')
                .eq('id', 1)
                .single()
                .execute()
        )
        return resp.data or {}

    async def update_current_balance(self, balance: float):
        loop = await self._get_loop()
        await loop.run_in_executor(
            None,
            lambda: self._create_client()
                .table('bot_config')
                .update({'current_balance': balance})
                .eq('id', 1)
                .execute()
        )

    async def insert_log(self, level: str, message: str):
        loop = await self._get_loop()
        await loop.run_in_executor(
            None,
            lambda: self._create_client()
                .table('bot_logs')
                .insert({'level': level.upper(), 'message': message})
                .execute()
        )

    async def insert_trade_signal(self, signal: TradeSignal) -> Optional[int]:
        loop = await self._get_loop()
        resp = await loop.run_in_executor(
            None,
            lambda: self._create_client()
                .table('trade_signals')
                .insert(signal.model_dump(exclude_none=True))
                .execute()
        )
        return resp.data[0]['id'] if resp.data else None

    async def update_trade_result(self, signal_id: int, result: str, martingale_level: int = 0) -> bool:
        loop = await self._get_loop()
        resp = await loop.run_in_executor(
            None,
            lambda: self._create_client()
                .table('trade_signals')
                .update({'result': result, 'martingale_level': martingale_level})
                .eq('id', signal_id)
                .execute()
        )
        return bool(resp.data)
