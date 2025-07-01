# services/supabase_service.py
from supabase import create_client, Client
from typing import List, Dict, Any, Optional
from core.data_models import TradeSignal

class SupabaseService:
    """Wrapper para todas as interações com o Supabase."""
    def __init__(self, url: str, key: str):
        self.client: Client = create_client(url, key)
        print("Serviço Supabase inicializado.")

    async def get_bot_config(self) -> Dict[str, Any]:
        """Busca a configuração completa do bot."""
        try:
            response = await self.client.table('bot_config').select('*').eq('id', 1).single().execute()
            return response.data if response.data else {}
        except Exception as e:
            print(f"Erro ao buscar configuração do bot: {e}")
            return {'status': 'PAUSED'} # Assume pausado em caso de erro

    async def insert_log(self, level: str, message: str):
        """Insere uma nova entrada de log no banco de dados."""
        try:
            await self.client.table('bot_logs').insert({'level': level.upper(), 'message': message}).execute()
        except Exception as e:
            # Não queremos que uma falha de log pare o bot, então apenas imprimimos o erro
            print(f"Erro ao inserir log no Supabase: {e}")

    async def insert_trade_signal(self, signal: TradeSignal) -> Optional[int]:
        try:
            response = await self.client.table('trade_signals').insert(signal.model_dump()).execute()
            return response.data[0]['id'] if response.data else None
        except Exception as e:
            await self.insert_log('ERROR', f"Falha ao inserir sinal de trade: {e}")
            return None

    async def update_trade_result(self, signal_id: int, result: str):
        try:
            await self.client.table('trade_signals').update({'result': result}).eq('id', signal_id).execute()
        except Exception as e:
            await self.insert_log('ERROR', f"Falha ao atualizar resultado do trade {signal_id}: {e}")
