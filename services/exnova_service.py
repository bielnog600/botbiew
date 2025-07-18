import logging
import time
from typing import List, Optional, Dict
from exnovaapi.stable_api import Exnova

class ExnovaService:
    def __init__(self, email: str, password: str):
        self.api = Exnova(email, password)
        self.logger = logging.getLogger(__name__)
        self.api.profile = None

    def connect(self) -> bool:
        """Conecta-se à API da Exnova e aguarda o perfil ser carregado."""
        try:
            check, reason = self.api.connect()
            if not check:
                self.logger.error(f"Falha na conexão com a Exnova: {reason}")
                return False
            
            profile_data = self.api.profile
            if profile_data is None:
                self.api.get_profile_ansyc()
                
            max_wait_time = 60  # Espera até 60 segundos pelo perfil
            start_time = time.time()
            
            while time.time() - start_time < max_wait_time:
                if hasattr(self.api, 'profile') and self.api.profile is not None:
                    self.logger.info("Conexão e perfil carregados com sucesso.")
                    return True
                self.logger.info("Aguardando carregamento do perfil...")
                time.sleep(1)
            
            self.logger.error("Conexão estabelecida, mas o perfil do utilizador não foi carregado a tempo.")
            return False
        except Exception as e:
            self.logger.error(f"Erro crítico na conexão: {e}")
            return False

    def get_open_assets(self) -> List[str]:
        """Obtém a lista de ativos abertos para negociação."""
        try:
            all_assets = self.api.get_all_open_time()
            open_assets = []
            for market_type in ['binary', 'turbo']:
                if market_type in all_assets:
                    for asset, info in all_assets[market_type].items():
                        if info.get('open', False):
                            open_assets.append(asset)
            return list(set(open_assets))
        except Exception as e:
            self.logger.error(f"Erro ao obter ativos abertos: {e}")
            return []

    def get_historical_candles(self, asset: str, timeframe: int, count: int) -> Optional[List[Dict]]:
        """Busca o histórico de velas para um ativo."""
        try:
            return self.api.get_candles(asset, timeframe, count, time.time())
        except Exception as e:
            self.logger.error(f"Erro ao obter velas para {asset}: {e}")
            return None

    def get_current_balance(self) -> Optional[float]:
        """Obtém o saldo atual da conta selecionada."""
        try:
            return self.api.get_balance()
        except Exception as e:
            self.logger.error(f"Erro ao obter saldo: {e}")
            return None

    def change_balance(self, balance_type: str):
        """Muda entre a conta de prática e a conta real."""
        try:
            self.api.change_balance(balance_type.upper())
            self.logger.info(f"Conta alterada para: {balance_type.upper()}")
        except Exception as e:
            self.logger.warning(f"Ocorreu um erro ao mudar de conta para {balance_type} (pode ser ignorado se já estiver na conta certa): {e}")

    def execute_trade(self, amount: float, asset: str, direction: str, expiration_minutes: int) -> Optional[int]:
        """Executa uma operação de compra ou venda."""
        try:
            status, order_id = self.api.buy(amount, asset, direction, expiration_minutes)
            if status:
                self.logger.info(f"Ordem executada: {asset} | {direction.upper()} | Valor: {amount} | Exp: {expiration_minutes} min | ID: {order_id}")
                return order_id
            else:
                self.logger.error(f"Falha ao executar operação em {asset}. Ordem não aceita.")
                return None
        except Exception as e:
            self.logger.error(f"Erro ao executar operação em {asset}: {e}")
            return None

    def check_win(self, order_id: int) -> Optional[str]:
        """Verifica o resultado de uma operação específica pelo seu ID."""
        try:
            profit_or_loss = self.api.check_win_v3(order_id)
            if profit_or_loss is None:
                self.logger.warning(f"Não foi possível obter o resultado para a ordem {order_id}.")
                return None
            if profit_or_loss > 0:
                self.logger.info(f"Ordem {order_id} RESULTADO: WIN")
                return 'WIN'
            elif profit_or_loss < 0:
                self.logger.info(f"Ordem {order_id} RESULTADO: LOSS")
                return 'LOSS'
            else:
                self.logger.info(f"Ordem {order_id} RESULTADO: DRAW")
                return 'DRAW'
        except Exception as e:
            self.logger.error(f"Erro ao verificar o resultado da ordem {order_id}: {e}")
            return None
