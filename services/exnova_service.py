import logging
import time
from exnovaapi.stable_api import IQ_Option # Alterado para corresponder à nova biblioteca

class ExnovaService:
    """
    Serviço para interagir com a API da IQ Option (usada pela Exnova).
    """
    def __init__(self, email, password):
        self.logger = logging.getLogger(__name__)
        # --- CORREÇÃO: Usa a classe correta da nova biblioteca ---
        self.api = IQ_Option(email, password)
        self.api.connect() # Conecta-se imediatamente

    def connect(self):
        """
        Verifica se a conexão com a API está ativa.
        """
        self.logger.info("A verificar a conexão com a API...")
        if self.api.check_connect():
            self.logger.info("Conectado com sucesso.")
            return True, None
        else:
            self.logger.error("Falha na conexão. A tentar reconectar...")
            # A biblioteca original já tem uma lógica de reconexão, vamos confiar nela.
            check, reason = self.api.connect()
            if check:
                self.logger.info("Reconexão bem-sucedida.")
            else:
                self.logger.error(f"Falha ao reconectar: {reason}")
            return check, reason

    def reconnect(self):
        """Tenta reconectar-se à API."""
        self.logger.warning("A tentar reconectar à Exnova...")
        self.api.connect()

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
            
    def check_win(self, order_id):
        """Verifica o resultado de uma operação."""
        return self.api.check_win_v4(order_id)
