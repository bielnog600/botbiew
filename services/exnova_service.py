import logging
import time
from exnovaapi.stable_api import Exnova

class ExnovaService:
    """
    Serviço simplificado para interagir com a API da Exnova.
    Esta classe serve como uma ponte entre o bot e a biblioteca da API.
    """
    def __init__(self, email, password):
        """
        Inicializa a API da Exnova.
        """
        self.api = Exnova(email, password)
        self.logger = logging.getLogger(__name__)

    def connect(self):
        """
        Conecta-se à API da Exnova.
        Retorna (True, None) em caso de sucesso.
        Retorna (False, "motivo") em caso de falha.
        """
        self.logger.info("A estabelecer ligação websocket com a Exnova...")
        check, reason = self.api.connect()
        if check:
            self.logger.info("Conectado com sucesso à Exnova.")
            return True, None
        else:
            self.logger.error(f"Falha ao conectar à Exnova: {reason}")
            return False, reason

    def reconnect(self):
        """Tenta reconectar-se à API."""
        self.logger.warning("A tentar reconectar à Exnova...")
        self.connect()

    def get_profile(self):
        """Busca o perfil do utilizador."""
        return self.api.get_profile_ansyc()

    def change_balance(self, balance_type):
        """Muda o tipo de conta (REAL ou PRACTICE)."""
        self.logger.info(f"A mudar de conta para: {balance_type}")
        self.api.change_balance(balance_type)
        self.logger.info(f"Conta mudada com sucesso para {balance_type}.")

    def get_open_assets(self):
        """Busca a lista de ativos abertos para negociação."""
        open_assets_data = self.api.get_all_open_time()
        open_assets_list = []
        for type in open_assets_data:
            for asset in open_assets_data[type]:
                if open_assets_data[type][asset].get("open", False):
                    open_assets_list.append(asset)
        return list(set(open_assets_list))

    def get_historical_candles(self, asset, timeframe, count):
        """Busca o histórico de velas para um ativo."""
        endtime = time.time()
        return self.api.get_candles(asset, timeframe, count, endtime)

    def get_current_balance(self):
        """Busca o saldo atual da conta."""
        return self.api.get_balance()

    def execute_trade(self, amount, asset, direction, timeframe):
        """Executa uma operação de compra."""
        self.logger.info(f"A executar operação: {direction.upper()} {amount} em {asset} por {timeframe} min.")
        check, order_id = self.api.buy(amount, asset, direction, timeframe)
        if check:
            self.logger.info(f"Operação executada com sucesso. ID da Ordem: {order_id}")
            return order_id
        else:
            self.logger.error(f"Falha na execução da operação. Resposta: {order_id}")
            return None
