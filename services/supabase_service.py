import asyncio
from supabase import create_client, Client
from typing import Optional, Dict
from core.data_models import TradeSignal

class SupabaseService:
    def __init__(self, url: str, key: str):
        self.client: Client = create_client(url, key)

    async def _execute_sync(self, func, *args, **kwargs):
        """
        Executa uma função síncrona (como as da biblioteca do Supabase)
        em uma thread separada para não bloquear o loop de eventos principal.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: func(*args, **kwargs).execute())

    async def get_bot_config(self) -> Dict:
        """Busca a configuração atual do bot de forma não-bloqueante."""
        try:
            response = await self._execute_sync(self.client.from_('bot_config').select('*').eq('id', 1).single)
            return response.data if response.data else {}
        except Exception as e:
            print(f"Erro ao buscar config: {e}")
            return {}

    async def update_config(self, data: Dict) -> bool:
        """Atualiza campos específicos na configuração do bot de forma não-bloqueante."""
        try:
            await self._execute_sync(self.client.from_('bot_config').update(data).eq('id', 1))
            return True
        except Exception as e:
            print(f"Erro ao atualizar config: {e}")
            return False
            
    async def update_current_balance(self, balance: float):
        """Atualiza apenas o saldo atual na configuração."""
        return await self.update_config({'current_balance': balance})

    async def insert_log(self, level: str, message: str):
        """Insere uma nova linha de log de forma não-bloqueante."""
        try:
            await self._execute_sync(self.client.from_('bot_logs').insert, [{'level': level, 'message': message}])
        except Exception as e:
            print(f"Erro ao inserir log: {e}")

    async def insert_trade_signal(self, signal: TradeSignal) -> Optional[int]:
        """Insere um novo sinal de trade e retorna o seu ID de forma não-bloqueante."""
        try:
            response = await self._execute_sync(self.client.from_('trade_signals').insert, signal.dict())
            if response.data:
                return response.data[0]['id']
            return None
        except Exception as e:
            print(f"Erro ao inserir sinal: {e}")
            return None

    async def update_trade_result(self, signal_id: int, result: str, martingale_level: int):
        """Atualiza o resultado de um sinal de trade de forma não-bloqueante."""
        try:
            update_data = {'result': result, 'martingale_level': martingale_level}
            await self._execute_sync(self.client.from_('trade_signals').update(update_data).eq('id', signal_id))
        except Exception as e:
            print(f"Erro ao atualizar resultado do sinal: {e}")
