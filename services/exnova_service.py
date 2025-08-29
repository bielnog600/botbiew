import time
import logging
from exnovaapi.stable_api import Exnova

class ExnovaService:
    def __init__(self, email, password):
        self.email = email
        self.password = password
        self.api: Exnova = Exnova(email=self.email, password=self.password)
        self.connection_successful = False

    def connect(self):
        logging.info("A estabelecer ligação websocket com a Exnova...")
        check, reason = self.api.connect()
        if check:
            logging.info("Conectado com sucesso. A atualizar a lista de ativos...")
            # --- LÓGICA CORRIGIDA: ATUALIZA OS ATIVOS DEPOIS DE CONECTAR ---
            self.api.update_actives()
            self.connection_successful = True
            return True, None
        else:
            logging.error(f"Falha ao conectar: {reason}")
            self.connection_successful = False
            return False, reason

    def check_connection(self):
        return self.api.check_connect()

    def get_all_open_assets(self):
        try:
            init_data = self.api.get_all_init_v2()
            if not init_data:
                return []
            
            open_assets = []
            for option_type in ['binary', 'turbo']:
                if option_type in init_data and init_data.get(option_type):
                    for details in init_data[option_type].get('actives', {}).values():
                        if details.get('enabled') and not details.get('is_suspended'):
                            asset_name = details.get('name', '').split('.')[-1]
                            if asset_name:
                                open_assets.append(asset_name)
            return list(set(open_assets)) # Retorna lista sem duplicados
        except Exception as e:
            logging.error(f"Erro ao buscar ativos abertos: {e}")
            return []

    def get_historical_candles(self, asset, interval, count):
        return self.api.get_candles(asset, interval, count, time.time())

    def execute_trade(self, value, asset, direction, expiration_minutes):
        logging.info(f"A executar operação: {direction.upper()} {value} em {asset} por {expiration_minutes} min.")
        success, order_id_or_message = self.api.buy(value, asset, direction, expiration_minutes)
        return success, order_id_or_message

    def get_current_balance(self):
        return self.api.get_balance()
    
    def change_balance(self, balance_type):
        logging.info(f"A mudar de conta para: {balance_type}")
        self.api.change_balance(balance_type)
        logging.info(f"Conta mudada com sucesso para {balance_type}.")
    
    def quit(self):
        try:
            self.api.close()
            logging.info("Conexão da API Exnova encerrada.")
        except Exception as e:
            logging.error(f"Erro ao fechar a conexão da API: {e}")
