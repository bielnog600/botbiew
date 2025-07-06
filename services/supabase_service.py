from supabase import create_client, Client
from typing import Optional, Dict
from core.data_models import TradeSignal

class SupabaseService:
    def __init__(self, url: str, key: str):
        self.client: Client = create_client(url, key)

    async def get_bot_config(self) -> Dict:
        """Busca a configuração atual do bot."""
        try:
            # CORRIGIDO: A sintaxe da biblioteca mudou.
            response = self.client.from_('bot_config').select('*').eq('id', 1).single().execute()
            return response.data if response.data else {}
        except Exception as e:
            print(f"Erro ao buscar config: {e}")
            return {}

    async def update_config(self, data: Dict) -> bool:
        """Atualiza campos específicos na configuração do bot."""
        try:
            # CORRIGIDO: A sintaxe da biblioteca mudou.
            self.client.from_('bot_config').update(data).eq('id', 1).execute()
            return True
        except Exception as e:
            print(f"Erro ao atualizar config: {e}")
            return False
            
    async def update_current_balance(self, balance: float):
        """Atualiza apenas o saldo atual na configuração."""
        return await self.update_config({'current_balance': balance})

    async def insert_log(self, level: str, message: str):
        """Insere uma nova linha de log."""
        try:
            # CORRIGIDO: A sintaxe da biblioteca mudou.
            self.client.from_('bot_logs').insert({'level': level, 'message': message}).execute()
        except Exception as e:
            print(f"Erro ao inserir log: {e}")

    async def insert_trade_signal(self, signal: TradeSignal) -> Optional[int]:
        """Insere um novo sinal de trade e retorna o seu ID."""
        try:
            # CORRIGIDO: A sintaxe da biblioteca mudou.
            response = self.client.from_('trade_signals').insert(signal.dict()).execute()
            if response.data:
                return response.data[0]['id']
            return None
        except Exception as e:
            print(f"Erro ao inserir sinal: {e}")
            return None

    async def update_trade_result(self, signal_id: int, result: str, martingale_level: int):
        """Atualiza o resultado de um sinal de trade."""
        try:
            # CORRIGIDO: A sintaxe da biblioteca mudou.
            self.client.from_('trade_signals').update({
                'result': result,
                'martingale_level': martingale_level
            }).eq('id', signal_id).execute()
        except Exception as e:
            print(f"Erro ao atualizar resultado do sinal: {e}")
