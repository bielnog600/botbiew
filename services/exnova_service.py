import logging
from exnovaapi.stable_api import Exnova

class ExnovaService:
    """
    Serviço para interagir com a API da Exnova de forma segura.
    Cada instância desta classe representa uma conexão independente.
    """
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
            self.api.update_actives()
            logging.info(f"{len(self.api.active_opcodes)} ativos carregados dinamicamente.")
            self.connection_successful = True
        else:
            logging.error(f"Falha ao conectar: {reason}")
            self.connection_successful = False
        return check, reason

    def is_connected(self):
        return self.connection_successful and self.api.check_connect()

    def get_all_open_assets(self):
        try:
            init_data = self.api.get_all_init_v2()
            open_assets = []
            if not init_data:
                return []
            
            for option_type in ['binary', 'turbo']:
                if option_type in init_data and init_data[option_type].get('actives'):
                    for asset_id, details in init_data[option_type]['actives'].items():
                        if details.get('enabled') and not details.get('is_suspended'):
                            asset_name = details['name'].split('.')[-1]
                            open_assets.append(asset_name)
            
            # Remove duplicados e retorna a lista
            return list(set(open_assets))
        except Exception as e:
            logging.error(f"Erro ao buscar ativos abertos: {e}")
            return []
            
    def get_historical_candles(self, pair_name, interval, count):
        return self.api.get_candles(pair_name, interval, count, self.api.get_server_timestamp())

    def execute_trade(self, value, pair, direction, exp_mins):
        return self.api.buy(value, pair, direction, exp_mins)

    def check_win(self, order_id):
        return self.api.check_win_v4(order_id)
        
    def get_current_balance(self):
        return self.api.get_balance()
    
    # --- NOVO: Função para fechar a conexão ---
    def close(self):
        self.api.close()
