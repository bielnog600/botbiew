import logging
from exnovaapi.stable_api import Exnova as ExnovaAPI

class ExnovaService:
    def __init__(self, email, password):
        self.email = email
        self.password = password
        self.api = ExnovaAPI(self.email, self.password)
        self.api.connect()

    def connect(self):
        logging.info("A estabelecer ligação websocket com a Exnova...")
        check, reason = self.api.connect()
        if check:
            logging.info("Conectado com sucesso.")
        else:
            logging.error(f"Falha na conexão: {reason}")
        return check, reason

    def reconnect(self):
        self.connect()

    def get_profile(self):
        return self.api.get_profile_ansyc()

    def change_balance(self, balance_type='PRACTICE'):
        logging.info(f"A mudar de conta para: {balance_type}")
        self.api.change_balance(balance_type)
        logging.info(f"Conta mudada com sucesso para {balance_type}.")

    def get_current_balance(self):
        return self.api.get_balance()

    def get_historical_candles(self, pair, interval, count):
        end_time = self.api.get_server_timestamp()
        return self.api.get_candles(pair, interval, count, end_time)

    def execute_trade(self, amount, pair, direction, expiration_minutes):
        logging.info(f"A executar operação: {direction.upper()} {amount} em {pair} por {expiration_minutes} min.")
        status, order_id = self.api.buy(amount, pair, direction, expiration_minutes)
        if status:
            logging.info(f"Operação executada com sucesso. ID da Ordem: {order_id}")
            return order_id
        else:
            logging.error(f"Falha na execução da operação. Resposta: {order_id}")
            return None
            
    def get_all_open_assets(self):
        """
        Busca todos os ativos abertos para opções binárias e turbo.
        """
        open_assets = []
        try:
            init_data = self.api.get_all_init_v2()
            if not init_data:
                return []

            for option_type in ['binary', 'turbo']:
                if option_type in init_data and init_data[option_type].get('actives'):
                    for asset_details in init_data[option_type]['actives'].values():
                        asset_name = asset_details.get('name', '').split('.')[-1]
                        if not asset_name: continue
                        
                        if asset_details.get('enabled', False) and not asset_details.get('is_suspended', False):
                            if asset_name not in open_assets:
                                open_assets.append(asset_name)
            return open_assets
        except Exception as e:
            logging.error(f"Erro ao buscar ativos abertos: {e}")
            return []


    def quit(self):
        logging.info("A encerrar a conexão com a API...")
        try:
            self.api.close()
        except Exception as e:
            logging.error(f"Erro ao fechar a API: {e}")

