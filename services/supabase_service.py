import logging
from typing import Dict, Any, List, Optional
# Voltamos a usar o cliente síncrono original
from supabase import create_client, Client
from core.data_models import TradeSignal

# Configura o logger para a biblioteca da Supabase para evitar spam de logs
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

class SupabaseService:
    """
    Serviço para interagir com a base de dados Supabase (versão síncrona).
    """
    def __init__(self, url: str, key: str):
        """
        Inicializa a conexão com o Supabase.
        """
        try:
            # Usamos o cliente síncrono padrão
            self.client: Client = create_client(url, key)
            logging.info("Conexão com o Supabase estabelecida com sucesso.")
        except Exception as e:
            logging.error(f"Falha ao conectar com o Supabase: {e}")
            self.client = None

    # As funções já não são 'async'
    def get_bot_config(self) -> Dict[str, Any]:
        """
        Busca a configuração principal do bot.
        """
        if not self.client:
            return {}
        try:
            # A chamada '.execute()' é bloqueante (síncrona)
            response = self.client.from_('bot_config').select("*").eq('id', 1).single().execute()
            if response.data:
                return response.data
            return {}
        except Exception as e:
            logging.error(f"Erro ao buscar configuração do bot: {e}")
            return {}

    def update_config(self, updates: Dict[str, Any]) -> bool:
        """
        Atualiza campos específicos na configuração do bot.
        """
        if not self.client:
            return False
        try:
            self.client.from_('bot_config').update(updates).eq('id', 1).execute()
            return True
        except Exception as e:
            logging.error(f"Erro ao atualizar configuração: {e}")
            return False

    def insert_log(self, level: str, message: str) -> None:
        """
        Insere um novo registo de log.
        """
        if not self.client:
            return
        try:
            self.client.from_('bot_logs').insert({
                "level": level,
                "message": message
            }).execute()
        except Exception as e:
            print(f"ERRO CRÍTICO: Falha ao inserir log no Supabase: {e}")

    def insert_trade_signal(self, signal: TradeSignal) -> Optional[int]:
        """
        Insere um novo sinal de trade.
        """
        if not self.client:
            return None
        try:
            response = self.client.from_('trade_signals').insert(signal.to_dict()).execute()
            if response.data:
                return response.data[0]['id']
            return None
        except Exception as e:
            logging.error(f"Erro ao inserir sinal de trade: {e}")
            return None

    def update_trade_result(self, signal_id: int, result: str, mg_level: int) -> bool:
        """
        Atualiza o resultado de um trade.
        """
        if not self.client:
            return False
        try:
            self.client.from_('trade_signals').update({
                "result": result,
                "martingale_level": mg_level
            }).eq('id', signal_id).execute()
            return True
        except Exception as e:
            logging.error(f"Erro ao atualizar resultado do trade: {e}")
            return False
            
    def update_current_balance(self, new_balance: float) -> bool:
        """
        Atualiza o saldo atual na configuração.
        """
        return self.update_config({'current_balance': new_balance})

    def upsert_cataloged_assets(self, assets_data: List[Dict[str, Any]]) -> bool:
        """
        Insere ou atualiza os dados dos ativos catalogados.
        """
        if not self.client or not assets_data:
            return False
        try:
            self.client.from_('cataloged_assets').upsert(assets_data, on_conflict='pair').execute()
            logging.info(f"{len(assets_data)} ativos catalogados foram guardados/atualizados.")
            return True
        except Exception as e:
            logging.error(f"Erro ao fazer upsert dos ativos catalogados: {e}")
            return False
