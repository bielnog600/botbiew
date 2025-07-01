# services/supabase_service.py
import asyncio
from supabase import create_client, Client
from typing import List, Dict, Any, Optional
from core.data_models import TradeSignal

class SupabaseService:
    """
    Wrapper para todas as interações com o Supabase,
    adaptado para um ambiente assíncrono.
    """
    def __init__(self, url: str, key: str):
        self.client: Client = create_client(url, key)
        self._loop = None
        print("Serviço Supabase inicializado.")

    async def _get_loop(self):
        """Obtém o loop de eventos em execução de forma segura."""
        if self._loop is None:
            self._loop = asyncio.get_running_loop()
        return self._loop

    async def get_bot_config(self) -> Dict[str, Any]:
        """Busca a configuração completa do bot de forma assíncrona."""
        try:
            loop = await self._get_loop()
            # FIX: Executa a chamada síncrona do Supabase num thread separado.
            response = await loop.run_in_executor(
                None,
                lambda: self.client.table('bot_config').select('*').eq('id', 1).single().execute()
            )
            return response.data if response.data else {}
        except Exception as e:
            print(f"Erro ao buscar configuração do bot: {e}")
            return {'status': 'PAUSED'}

    async def insert_log(self, level: str, message: str):
        """Insere uma nova entrada de log no banco de dados de forma assíncrona."""
        try:
            loop = await self._get_loop()
            # FIX: Executa a chamada síncrona do Supabase num thread separado.
            await loop.run_in_executor(
                None,
                lambda: self.client.table('bot_logs').insert({'level': level.upper(), 'message': message}).execute()
            )
        except Exception as e:
            print(f"Erro ao inserir log no Supabase: {e}")

    async def insert_trade_signal(self, signal: TradeSignal) -> Optional[int]:
        """Insere um novo sinal de trade de forma assíncrona."""
        try:
            loop = await self._get_loop()
            # FIX: Executa a chamada síncrona do Supabase num thread separado.
            response = await loop.run_in_executor(
                None,
                lambda: self.client.table('trade_signals').insert(signal.model_dump()).execute()
            )
            return response.data[0]['id'] if response.data else None
        except Exception as e:
            await self.insert_log('ERROR', f"Falha ao inserir sinal de trade: {e}")
            return None

    async def update_trade_result(self, signal_id: int, result: str):
        """Atualiza o resultado de um trade de forma assíncrona."""
        try:
            loop = await self._get_loop()
            # FIX: Executa a chamada síncrona do Supabase num thread separado.
            await loop.run_in_executor(
                None,
                lambda: self.client.table('trade_signals').update({'result': result}).eq('id', signal_id).execute()
            )
        except Exception as e:
            await self.insert_log('ERROR', f"Falha ao atualizar resultado do trade {signal_id}: {e}")

