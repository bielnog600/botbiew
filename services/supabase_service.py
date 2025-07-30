import logging
from typing import Dict, Any, List, Optional
# A importação foi alterada para usar o cliente assíncrono (aio)
from supabase.aio import create_client, AsyncClient
from core.data_models import TradeSignal

# Configura o logger para a biblioteca da Supabase para evitar spam de logs
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

class SupabaseService:
    """
    Serviço para interagir com a base de dados Supabase.
    """
    def __init__(self, url: str, key: str):
        """
        Inicializa a conexão com o Supabase.
        :param url: URL do projeto Supabase.
        :param key: Chave de API (anon key) do Supabase.
        """
        try:
            # O cliente agora é um AsyncClient, o que torna as chamadas 'await' válidas
            self.client: AsyncClient = create_client(url, key)
            logging.info("Conexão com o Supabase estabelecida com sucesso.")
        except Exception as e:
            logging.error(f"Falha ao conectar com o Supabase: {e}")
            self.client = None

    async def get_bot_config(self) -> Dict[str, Any]:
        """
        Busca a configuração principal do bot na tabela 'bot_config'.
        Assume que a configuração está no registo com id = 1.
        """
        if not self.client:
            return {}
        try:
            response = await self.client.from_('bot_config').select("*").eq('id', 1).single().execute()
            if response.data:
                return response.data
            return {}
        except Exception as e:
            logging.error(f"Erro ao buscar configuração do bot: {e}")
            return {}

    async def update_config(self, updates: Dict[str, Any]) -> bool:
        """
        Atualiza campos específicos na configuração do bot.
        """
        if not self.client:
            return False
        try:
            await self.client.from_('bot_config').update(updates).eq('id', 1).execute()
            return True
        except Exception as e:
            logging.error(f"Erro ao atualizar configuração: {e}")
            return False

    async def insert_log(self, level: str, message: str) -> None:
        """
        Insere um novo registo de log na tabela 'bot_logs'.
        """
        if not self.client:
            return
        try:
            await self.client.from_('bot_logs').insert({
                "level": level,
                "message": message
            }).execute()
        except Exception as e:
            # Não logar o erro de log para evitar loops infinitos
            print(f"ERRO CRÍTICO: Falha ao inserir log no Supabase: {e}")

    async def insert_trade_signal(self, signal: TradeSignal) -> Optional[int]:
        """
        Insere um novo sinal de trade na tabela 'trade_signals'.
        Retorna o ID do registo inserido.
        """
        if not self.client:
            return None
        try:
            response = await self.client.from_('trade_signals').insert(signal.to_dict()).execute()
            if response.data:
                return response.data[0]['id']
            return None
        except Exception as e:
            logging.error(f"Erro ao inserir sinal de trade: {e}")
            return None

    async def update_trade_result(self, signal_id: int, result: str, mg_level: int) -> bool:
        """
        Atualiza o resultado de um trade e o nível de martingale.
        """
        if not self.client:
            return False
        try:
            await self.client.from_('trade_signals').update({
                "result": result,
                "martingale_level": mg_level
            }).eq('id', signal_id).execute()
            return True
        except Exception as e:
            logging.error(f"Erro ao atualizar resultado do trade: {e}")
            return False
            
    async def update_current_balance(self, new_balance: float) -> bool:
        """
        Atualiza o saldo atual na tabela de configuração.
        """
        return await self.update_config({'current_balance': new_balance})

    async def upsert_cataloged_assets(self, assets_data: List[Dict[str, Any]]) -> bool:
        """
        Insere ou atualiza os dados dos ativos catalogados na tabela 'cataloged_assets'.
        Usa o 'pair' como chave para o upsert.
        """
        if not self.client or not assets_data:
            return False
        try:
            await self.client.from_('cataloged_assets').upsert(assets_data, on_conflict='pair').execute()
            logging.info(f"{len(assets_data)} ativos catalogados foram guardados/atualizados.")
            return True
        except Exception as e:
            logging.error(f"Erro ao fazer upsert dos ativos catalogados: {e}")
            return False
