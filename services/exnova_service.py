import logging
import time
from typing import List, Optional, Dict

# A usar a sua biblioteca local exnovaapi
from exnovaapi.stable_api import Exnova

class ExnovaService:
    """
    Versão corrigida e simplificada, baseada na lógica do seu 'botsock.py'.
    """
    def __init__(self, email: str, password: str):
        self.logger = logging.getLogger(__name__)
        self.api = Exnova(email, password)

    def connect(self) -> bool:
        """
        Este método agora APENAS estabelece a ligação websocket.
        Retorna True se a ligação for bem-sucedida, False caso contrário.
        """
        self.logger.info("A estabelecer ligação websocket com a Exnova...")
        check, reason = self.api.connect()
        if not check:
            self.logger.error(f"Falha ao ligar o websocket: {reason}")
            return False
        
        self.logger.info("Websocket conectado com sucesso.")
        return True

    def get_profile(self) -> Optional[Dict]:
        """Pede e retorna os dados do perfil do utilizador."""
        self.logger.info("A pedir dados do perfil...")
        # Usamos o nome do método com o erro de digitação, tal como no seu script funcional.
        if hasattr(self.api, 'get_profile_ansyc'):
            return self.api.get_profile_ansyc()
        else:
            self.logger.error("O método 'get_profile_ansyc' não foi encontrado na sua biblioteca exnovaapi.")
            return None

    # --- O resto dos métodos permanece igual ---

    def get_open_assets(self) -> List[str]:
        self.logger.debug("A obter ativos abertos...")
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
            self.logger.error(f"Erro ao obter ativos abertos: {e}", exc_info=True)
            return []

    def get_historical_candles(self, asset: str, timeframe: int, count: int) -> Optional[List[Dict]]:
        self.logger.debug(f"A obter {count} velas para {asset}...")
        try:
            return self.api.get_candles(asset, timeframe, count, time.time())
        except Exception as e:
            self.logger.error(f"Erro ao obter velas para {asset}: {e}", exc_info=True)
            return None

    def get_current_balance(self) -> Optional[float]:
        try:
            return self.api.get_balance()
        except Exception as e:
            self.logger.error(f"Erro ao obter saldo: {e}", exc_info=True)
            return None

    def change_balance(self, balance_type: str):
        self.logger.info(f"A mudar de conta para: {balance_type.upper()}")
        try:
            self.api.change_balance(balance_type.upper())
            self.logger.info(f"Conta mudada com sucesso para {balance_type.upper()}.")
        except Exception as e:
            self.logger.warning(f"Ocorreu um erro ao mudar de conta (pode ser normal): {e}")

    def execute_trade(self, amount: float, asset: str, direction: str, expiration_minutes: int) -> Optional[int]:
        self.logger.info(f"A executar operação: {direction.upper()} {amount} em {asset} por {expiration_minutes} min.")
        try:
            status, order_id = self.api.buy(amount, asset, direction.lower(), expiration_minutes)
            if status:
                self.logger.info(f"Operação executada com sucesso. ID da Ordem: {order_id}")
                return order_id
            else:
                self.logger.error(f"Falha na execução da operação. Resposta: {order_id}")
                return None
        except Exception as e:
            self.logger.error(f"Erro durante a execução da operação: {e}", exc_info=True)
            return None

    def check_win(self, order_id: int) -> Optional[str]:
        self.logger.info(f"A verificar resultado para a Ordem ID: {order_id}...")
        try:
            profit_or_loss = self.api.check_win_v3(order_id)
            if profit_or_loss is None:
                return 'UNKNOWN'
            if profit_or_loss > 0:
                return 'WIN'
            elif profit_or_loss < 0:
                return 'LOSS'
            else:
                return 'DRAW'
        except Exception as e:
            self.logger.error(f"Erro ao verificar o resultado da ordem {order_id}: {e}", exc_info=True)
            return None
