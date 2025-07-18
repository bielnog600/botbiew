import logging
import time
from typing import List, Optional, Dict
from exnovaapi.stable_api import Exnova

class ExnovaService:
    def __init__(self, email: str, password: str):
        self.email = email # Guardar o email para depuração
        self.password = password # Guardar a password
        self.api = Exnova(self.email, self.password)
        self.logger = logging.getLogger(__name__)
        self.api.profile = None

    def connect(self) -> bool:
        """
        Conecta-se à API da Exnova com logging de depuração avançado
        para inspecionar todas as mensagens recebidas.
        """
        self.logger.info("A tentar ligar à Exnova em MODO DE DEPURAÇÃO...")
        self.logger.info(f"A usar o email: {self.email}") # Verificar se o email está correto

        # --- INÍCIO DA SECÇÃO DE DEPURAÇÃO ---
        # Esta função irá imprimir todas as mensagens que a Exnova nos envia.
        def print_message(message):
            self.logger.info(f"MENSAGEM RECEBIDA DA EXNOVA: {message}")
        
        # Atribuir a nossa função de logging ao message_callback da API
        self.api.message_callback = print_message
        # --- FIM DA SECÇÃO DE DEPURAÇÃO ---

        try:
            check, reason = self.api.connect()
            
            if not check:
                self.logger.error(f"Falha na ligação à Exnova: {reason}")
                return False

            # Vamos continuar a esperar pelo perfil como antes, mas agora
            # a função print_message irá mostrar-nos tudo o que acontece.
            for i in range(15):
                if getattr(self.api, 'profile', None) is not None:
                    self.logger.info("Ligação e perfil carregados com sucesso.")
                    self.logger.info(f"Saldo: {self.get_current_balance()}")
                    # Remover o callback de depuração após o sucesso
                    self.api.message_callback = None 
                    return True
                self.logger.info(f"A aguardar pelo perfil... ({i+1}/15)")
                time.sleep(1)
            
            self.logger.error("Ligação estabelecida, mas o perfil do utilizador não foi carregado a tempo.")
            self.logger.error("VERIFIQUE AS MENSAGENS 'MENSAGEM RECEBIDA DA EXNOVA' ACIMA PARA ENCONTRAR ERROS DE LOGIN OU 2FA.")
            # Remover o callback de depuração após a falha
            self.api.message_callback = None
            return False

        except Exception as e:
            self.logger.error(f"Ocorreu um erro crítico durante o processo de ligação: {e}", exc_info=True)
            return False

    # --- O resto dos métodos (get_open_assets, execute_trade, etc.) permanecem os mesmos ---
    # --- Cole o resto do seu código da classe aqui ---
    def get_open_assets(self) -> List[str]:
        """Obtém a lista de ativos abertos para negociação."""
        self.logger.debug("A obter ativos abertos...")
        try:
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
            end_time = time.time()
            candles = self.api.get_candles(asset, timeframe, count, end_time)
            if not candles:
                self.logger.warning(f"Não foram retornados dados de velas para {asset}.")
                return None
            return candles
        except Exception as e:
            self.logger.error(f"Erro ao obter velas para {asset}: {e}", exc_info=True)
            return None

    def get_current_balance(self) -> Optional[float]:
        """Obtém o saldo atual da conta selecionada."""
        try:
            return self.api.get_balance()
        except Exception as e:
            self.logger.error(f"Erro ao obter saldo: {e}", exc_info=True)
            return None

    def change_balance(self, balance_type: str):
        """Muda entre a conta de PRÁTICA e a REAL."""
        self.logger.info(f"A mudar de conta para: {balance_type.upper()}")
        try:
            self.api.change_balance(balance_type.upper())
            self.logger.info(f"Conta mudada com sucesso para {balance_type.upper()}.")
        except Exception as e:
            self.logger.warning(f"Ocorreu um erro ao mudar de conta (isto pode ser normal): {e}")

    def execute_trade(self, amount: float, asset: str, direction: str, expiration_minutes: int) -> Optional[int]:
        """Executa uma operação de compra ou venda."""
        self.logger.info(f"A executar operação: {direction.upper()} {amount} em {asset} por {expiration_minutes} min.")
        try:
            status, order_id = self.api.buy(amount, asset, direction.lower(), expiration_minutes)
            if status:
                self.logger.info(f"Operação executada com sucesso. ID da Ordem: {order_id}")
                return order_id
            else:
                self.logger.error(f"Falha na execução da operação para {asset}. Motivo: A corretora rejeitou a operação. ID da Ordem: {order_id}")
                return None
        except Exception as e:
            self.logger.error(f"Ocorreu um erro durante a execução da operação para {asset}: {e}", exc_info=True)
            return None

    def check_win(self, order_id: int) -> Optional[str]:
        """Verifica o resultado de uma operação específica pelo seu ID."""
        self.logger.info(f"A verificar resultado para a Ordem ID: {order_id}...")
        try:
            for i in range(3):
                result = self.api.check_win_v3(order_id)
                if result is not None:
                    break
                self.logger.warning(f"Resultado para a ordem {order_id} ainda não disponível. A tentar novamente em 2 segundos... ({i+1}/3)")
                time.sleep(2)

            if result is None:
                self.logger.error(f"Não foi possível obter o resultado para a ordem {order_id} após várias tentativas.")
                return 'UNKNOWN'

            if result > 0:
                self.logger.info(f"Resultado da Ordem {order_id}: WIN (Lucro: {result})")
                return 'WIN'
            elif result < 0:
                self.logger.info(f"Resultado da Ordem {order_id}: LOSS (Prejuízo: {result})")
                return 'LOSS'
            else:
                self.logger.info(f"Resultado da Ordem {order_id}: DRAW (P/L: 0)")
                return 'DRAW'
        except Exception as e:
            self.logger.error(f"Ocorreu um erro ao verificar o resultado para a ordem {order_id}: {e}", exc_info=True)
            return None
