import logging
import time
from typing import List, Optional, Dict
# --- MUDANÇA IMPORTANTE: A usar a biblioteca iqoptionapi ---
from iqoptionapi.stable_api import IQ_Option

class ExnovaService:
    def __init__(self, email: str, password: str):
        self.logger = logging.getLogger(__name__)
        self.logger.info("A inicializar o serviço com a biblioteca IQOptionAPI.")
        # --- A API agora é uma instância de IQ_Option ---
        self.api = IQ_Option(email, password)
        # O perfil será preenchido pela própria biblioteca durante a ligação.
        self.api.profile = None

    def connect(self) -> bool:
        """
        Conecta-se usando a biblioteca iqoptionapi, que é mais estável.
        Esta biblioteca lida com o carregamento do perfil de forma mais fiável.
        """
        self.logger.info("A tentar ligar à Exnova/IQOption API...")
        try:
            # O método connect() desta biblioteca é bloqueante e trata de tudo.
            # Retorna (True, None) em caso de sucesso ou (False, 'razão') em caso de falha.
            check, reason = self.api.connect()
            
            if not check:
                self.logger.error(f"Falha na ligação: {reason}")
                self.logger.error("Verifique as suas credenciais (email/password) e se a 2FA está desativada.")
                return False

            self.logger.info("SUCESSO! Ligação estabelecida e perfil carregado.")
            self.logger.info(f"Saldo inicial: {self.get_current_balance()}")
            return True

        except Exception as e:
            self.logger.error(f"Ocorreu um erro crítico durante o processo de ligação: {e}", exc_info=True)
            return False

    def get_open_assets(self) -> List[str]:
        """Obtém a lista de ativos abertos para negociação."""
        self.logger.debug("A obter ativos abertos...")
        try:
            # O método é o mesmo da biblioteca anterior.
            all_assets = self.api.get_all_open_time()
            open_assets = []
            for market_type in ['binary', 'turbo']:
                if market_type in all_assets:
                    for asset, info in all_assets[market_type].items():
                        if info.get('open', False):
                            open_assets.append(asset)
            unique_assets = list(set(open_assets))
            self.logger.debug(f"Encontrados {len(unique_assets)} ativos abertos.")
            return unique_assets
        except Exception as e:
            self.logger.error(f"Erro ao obter ativos abertos: {e}", exc_info=True)
            return []

    def get_historical_candles(self, asset: str, timeframe: int, count: int) -> Optional[List[Dict]]:
        """Busca o histórico de velas para um ativo."""
        self.logger.debug(f"A obter {count} velas para {asset} com timeframe de {timeframe}s.")
        try:
            # O método get_candles é padrão e funciona da mesma forma.
            end_time = time.time()
            self.api.start_candles_stream(asset, timeframe, count)
            candles = self.api.get_realtime_candles(asset, timeframe)
            self.api.stop_candles_stream(asset, timeframe)
            # A biblioteca retorna um dicionário de velas, precisamos convertê-lo para uma lista
            candles_list = [candles[key] for key in sorted(candles.keys())]
            return candles_list[-count:] # Garantir que retornamos o número certo de velas
        except Exception as e:
            self.logger.error(f"Erro ao obter velas para {asset}: {e}", exc_info=True)
            return None

    def get_current_balance(self) -> Optional[float]:
        """Obtém o saldo atual da conta selecionada."""
        try:
            # O método é o mesmo.
            return self.api.get_balance()
        except Exception as e:
            self.logger.error(f"Erro ao obter saldo: {e}", exc_info=True)
            return None

    def change_balance(self, balance_type: str):
        """Muda entre a conta de PRÁTICA e a REAL."""
        self.logger.info(f"A mudar de conta para: {balance_type.upper()}")
        try:
            # O método é o mesmo.
            self.api.change_balance(balance_type.upper())
            self.logger.info(f"Conta mudada com sucesso para {balance_type.upper()}.")
        except Exception as e:
            self.logger.warning(f"Ocorreu um erro ao mudar de conta (isto pode ser normal): {e}")

    def execute_trade(self, amount: float, asset: str, direction: str, expiration_minutes: int) -> Optional[int]:
        """Executa uma operação de compra ou venda."""
        self.logger.info(f"A executar operação: {direction.upper()} {amount} em {asset} por {expiration_minutes} min.")
        try:
            # O método buy é padrão.
            status, order_id = self.api.buy(amount, asset, direction.lower(), expiration_minutes)
            if status:
                self.logger.info(f"Operação executada com sucesso. ID da Ordem: {order_id}")
                return order_id
            else:
                self.logger.error(f"Falha na execução da operação para {asset}. A corretora rejeitou a operação. Resposta: {order_id}")
                return None
        except Exception as e:
            self.logger.error(f"Ocorreu um erro durante a execução da operação para {asset}: {e}", exc_info=True)
            return None

    def check_win(self, order_id: int) -> Optional[str]:
        """Verifica o resultado de uma operação específica pelo seu ID."""
        self.logger.info(f"A verificar resultado para a Ordem ID: {order_id}...")
        try:
            # Usamos check_win_v4, que é mais comum nesta biblioteca.
            # Ele retorna (lucro > 0, lucro < 0 ou 0)
            profit_or_loss = self.api.check_win_v4(order_id)
            
            if profit_or_loss is None:
                self.logger.warning(f"Não foi possível obter o resultado para a ordem {order_id}.")
                return 'UNKNOWN'

            if profit_or_loss > 0:
                self.logger.info(f"Resultado da Ordem {order_id}: WIN (Lucro: {profit_or_loss})")
                return 'WIN'
            elif profit_or_loss < 0:
                self.logger.info(f"Resultado da Ordem {order_id}: LOSS (Prejuízo: {profit_or_loss})")
                return 'LOSS'
            else:
                self.logger.info(f"Resultado da Ordem {order_id}: DRAW (P/L: 0)")
                return 'DRAW'
        except Exception as e:
            self.logger.error(f"Ocorreu um erro ao verificar o resultado para a ordem {order_id}: {e}", exc_info=True)
            return None
