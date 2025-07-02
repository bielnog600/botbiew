# services/supabase_service.py
import asyncio
from supabase import create_client, Client
from typing import List, Dict, Any, Optional
from core.data_models import TradeSignal

class SupabaseService:
    def __init__(self, url: str, key: str):
        self._url = url
        self._key = key
        self._loop = None
        print("Serviço Supabase inicializado.")

    def _create_client(self) -> Client:
        return create_client(self._url, self._key)

    async def _get_loop(self):
        if self._loop is None: self._loop = asyncio.get_running_loop()
        return self._loop

    async def get_bot_config(self) -> Dict[str, Any]:
        try:
            loop = await self._get_loop()
            response = await loop.run_in_executor(None, lambda: self._create_client().table('bot_config').select('*').eq('id', 1).single().execute())
            return response.data if response.data else {}
        except Exception as e:
            print(f"Erro ao buscar configuração do bot: {e}", flush=True)
            return {'status': 'PAUSED'}

    async def update_current_balance(self, balance: float):
        try:
            loop = await self._get_loop()
            await loop.run_in_executor(None, lambda: self._create_client().table('bot_config').update({'current_balance': balance}).eq('id', 1).execute())
        except Exception as e:
            print(f"Erro ao atualizar saldo no Supabase: {e}", flush=True)

    async def insert_log(self, level: str, message: str):
        try:
            loop = await self._get_loop()
            await loop.run_in_executor(None, lambda: self._create_client().table('bot_logs').insert({'level': level.upper(), 'message': message}).execute())
        except Exception as e:
            print(f"Erro ao inserir log no Supabase: {e}", flush=True)

    async def insert_trade_signal(self, signal: TradeSignal) -> Optional[int]:
        try:
            loop = await self._get_loop()
            response = await loop.run_in_executor(None, lambda: self._create_client().table('trade_signals').insert(signal.model_dump(exclude_none=True)).execute())
            return response.data[0]['id'] if response.data else None
        except Exception as e:
            await self.insert_log('ERROR', f"Falha CRÍTICA ao inserir sinal de trade: {e}")
            return None

    # FIX: Adicionado o parâmetro 'martingale_level' à definição da função.
    async def update_trade_result(self, signal_id: int, result: str, martingale_level: int = 0) -> bool:
        """
        Atualiza o resultado de um trade e o nível de martingale.
        Retorna True em caso de sucesso, False em caso de falha.
        """
        try:
            loop = await self._get_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self._create_client().table('trade_signals').update({
                    'result': result,
                    'martingale_level': martingale_level
                }).eq('id', signal_id).execute()
            )
            return bool(response.data)
        except Exception as e:
            await self.insert_log('ERROR', f"Falha ao atualizar resultado do trade {signal_id}: {e}")
            return False
