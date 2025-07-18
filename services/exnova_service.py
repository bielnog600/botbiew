import logging
import time
from typing import List, Optional, Dict
from exnovaapi.stable_api import Exnova

class ExnovaService:
    def __init__(self, email: str, password: str):
        self.api = Exnova(email, password)
        self.logger = logging.getLogger(__name__)
        self.api.profile = None

    def load_profile(self) -> bool:
        """
        Carrega o perfil do utilizador de forma síncrona e segura, como sugerido.
        """
        try:
            self.api.profile = None
            self.api.get_profile_ansyc() # Envia a requisição para obter o perfil

            start_time = time.time()
            timeout = 15  # segundos

            while self.api.profile is None:
                if time.time() - start_time > timeout:
                    self.logger.error("Timeout ao carregar o perfil do utilizador.")
                    return False
                time.sleep(0.1)

            # Verifica se o perfil veio corretamente
            if "msg" not in self.api.profile or not self.api.profile["msg"]:
                self.logger.error("Perfil do utilizador carregado, mas vazio ou inválido.")
                return False
            
            return True
        except Exception as e:
            self.logger.error(f"Erro ao carregar perfil: {e}")
            return False

    def connect(self) -> bool:
        """Conecta-se à API da Exnova e usa o novo método para carregar o perfil."""
        try:
            check, reason = self.api.connect()
            if not check:
                self.logger.error(f"Falha na conexão com a Exnova: {reason}")
                return False
            
            # Usa o novo método robusto para carregar o perfil
            if self.load_profile():
                self.logger.info("Conexão e perfil carregados com sucesso.")
                return True
            else:
                return False
        except Exception as e:
            self.logger.error(f"Erro crítico na conexão: {e}")
            return False

    def get_open_assets(self) -> List[str]:
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
        try:
            return self.api.get_candles(asset, timeframe, count, time.time())
        except Exception as e:
            self.logger.error(f"Erro ao obter velas para {asset}: {e}")
            return None

    def get_current_balance(self) -> Optional[float]:
        try:
            return self.api.get_balance()
        except Exception as e:
            self.logger.error(f"Erro ao obter saldo: {e}")
            return None

    def change_balance(self, balance_type: str):
        try:
            self.api.change_balance(balance_type.upper())
        except Exception as e:
            self.logger.warning(f"Ocorreu um erro esperado ao mudar de conta para {balance_type} (pode ser ignorado): {e}")

    def execute_trade(self, amount: float, asset: str, direction: str, expiration_minutes: int) -> Optional[int]:
        try:
            status, order_id = self.api.buy(amount, asset, direction, expiration_minutes)
            return order_id if status else None
        except Exception as e:
            self.logger.error(f"Erro ao executar operação em {asset}: {e}")
            return None

    def check_win(self, order_id: int) -> Optional[str]:
        try:
            profit_or_loss = self.api.check_win_v3(order_id)[1]
            if profit_or_loss is None:
                self.logger.warning(f"Não foi possível obter o resultado para a ordem {order_id}.")
                return None
            if profit_or_loss > 0: return 'WIN'
            elif profit_or_loss < 0: return 'LOSS'
            else: return 'DRAW'
        except Exception as e:
            self.logger.error(f"Erro ao verificar o resultado da ordem {order_id}: {e}")
            return None
