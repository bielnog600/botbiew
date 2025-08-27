import logging
from supabase import create_client, Client

class SupabaseService:
    def __init__(self, url: str, key: str):
        try:
            self.supabase: Client = create_client(url, key)
            logging.info("Conexão com o Supabase estabelecida com sucesso.")
        except Exception as e:
            logging.error(f"Erro ao conectar com o Supabase: {e}")
            self.supabase = None

    def get_bot_config(self):
        if not self.supabase: return None
        try:
            response = self.supabase.table('bot_config').select('*').eq('id', 1).single().execute()
            return response.data
        except Exception as e:
            logging.error(f"Erro ao buscar configuração do bot: {e}")
            return None

    def update_config(self, data: dict):
        if not self.supabase: return
        try:
            self.supabase.table('bot_config').update(data).eq('id', 1).execute()
        except Exception as e:
            logging.error(f"Erro ao atualizar configuração: {e}")

    def insert_log(self, level: str, message: str):
        if not self.supabase: return
        try:
            self.supabase.table('bot_logs').insert({'level': level, 'message': message}).execute()
        except Exception as e:
            print(f"Falha ao inserir log no Supabase: {e}")

    def insert_trade_signal(self, signal_dict: dict):
        if not self.supabase: return None
        try:
            signal_dict['result'] = 'PENDENTE'
            response = self.supabase.table('trade_signals').insert(signal_dict).execute()
            return response.data[0]['id']
        except Exception as e:
            logging.error(f"Erro ao inserir sinal de trade: {e}")
            return None

    def update_trade_result(self, signal_id: int, result: str, martingale_level: int):
        if not self.supabase: return
        try:
            self.supabase.table('trade_signals').update({'result': result, 'martingale_level': martingale_level}).eq('id', signal_id).execute()
        except Exception as e:
            logging.error(f"Erro ao atualizar resultado do trade: {e}")

    def update_current_balance(self, balance: float):
        self.update_config({'current_balance': balance})

    def upsert_cataloged_asset(self, asset_data: dict):
        if not self.supabase: return
        try:
            self.supabase.table('cataloged_assets').upsert(asset_data, on_conflict='pair').execute()
        except Exception as e:
            logging.error(f"Erro ao salvar ativo catalogado ({asset_data.get('pair')}): {e}")

    def get_cataloged_assets(self, min_win_rate: float):
        if not self.supabase: return []
        try:
            response = self.supabase.table('cataloged_assets').select('*').gte('win_rate', min_win_rate).order('win_rate', desc=True).execute()
            return response.data
        except Exception as e:
            logging.error(f"Erro ao buscar ativos catalogados: {e}")
            return []
