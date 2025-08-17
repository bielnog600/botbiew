import logging
import time
from exnovaapi.stable_api import Exnova 

class ExnovaService:
    def __init__(self, email, password):
        self.logger = logging.getLogger(__name__)
        self.api = Exnova(email, password)

    def connect(self):
        self.logger.info("A estabelecer ligação websocket com a Exnova...")
        check, reason = self.api.connect()
        if check:
            self.logger.info("Conectado com sucesso.")
            return True, None
        else:
            self.logger.error(f"Falha na conexão: {reason}")
            return False, reason

    def reconnect(self):
        self.logger.warning("A tentar reconectar à Exnova...")
        self.api.connect()

    def quit(self):
        """Encerra a conexão com a API de forma segura."""
        self.logger.info("A encerrar a conexão com a API...")
        if hasattr(self.api, 'close'):
            self.api.close()

    def get_profile(self):
        return self.api.get_profile_ansyc()

    def change_balance(self, balance_type):
        self.logger.info(f"A mudar de conta para: {balance_type}")
        self.api.change_balance(balance_type)
        self.logger.info(f"Conta mudada com sucesso para {balance_type}.")

    def get_open_assets(self):
        open_assets_data = self.api.get_all_open_time()
        open_assets_list = []
        for asset_type in open_assets_data:
            for asset in open_assets_data[asset_type]:
                if open_assets_data[asset_type][asset].get("open", False):
                    open_assets_list.append(asset)
        return list(set(open_assets_list))

    def get_historical_candles(self, asset, timeframe, count):
        endtime = time.time()
        return self.api.get_candles(asset, timeframe, count, endtime)

    def get_current_balance(self):
        return self.api.get_balance()

    def execute_trade(self, amount, asset, direction, timeframe):
        self.logger.info(f"A executar operação: {direction.upper()} {amount} em {asset} por {timeframe} min.")
        check, order_id = self.api.buy(amount, asset, direction, timeframe)
        if check:
            self.logger.info(f"Operação executada com sucesso. ID da Ordem: {order_id}")
            return order_id
        else:
            self.logger.error(f"Falha na execução da operação. Resposta: {order_id}")
            return None
            
    def check_win(self, order_id):
        return self.api.check_win_v4(order_id)
