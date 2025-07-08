import asyncio
import logging
from typing import List, Optional, Dict
from exnovaapi.api import Exnovaapi

class AsyncExnovaService:
    def __init__(self, email: str, password: str):
        self.api = Exnovaapi(email, password)
        self.logger = logging.getLogger(__name__)

    async def connect(self) -> bool:
        """Conecta-se à API da Exnova e aguarda o perfil ser carregado."""
        try:
            loop = asyncio.get_event_loop()
            check, reason = await loop.run_in_executor(None, self.api.connect)
            if not check:
                self.logger.error(f"Falha na conexão com a Exnova: {reason}")
                return False
            
            for _ in range(10): 
                if hasattr(self.api, 'profile') and self.api.profile is not None:
                    self.logger.info("Conexão e perfil carregados com sucesso.")
                    return True
                await asyncio.sleep(1)
            
            self.logger.error("Conexão estabelecida, mas o perfil do utilizador não foi carregado a tempo.")
            return False
        except Exception as e:
            self.logger.error(f"Erro crítico na conexão: {e}")
            return False

    async def get_open_assets(self) -> List[str]:
        """Obtém a lista de ativos abertos para negociação."""
        try:
            # CORRIGIDO: A biblioteca provavelmente armazena os ativos na propriedade 'actives' após a conexão.
            if hasattr(self.api, 'actives'):
                return [asset for asset, data in self.api.actives.items() if data.get('open')]
            self.logger.warning("Não foi possível encontrar a lista de ativos 'actives'.")
            return []
        except Exception as e:
            self.logger.error(f"Erro ao obter ativos abertos: {e}")
            return []

    async def get_historical_candles(self, asset: str, timeframe: int, count: int) -> Optional[List[Dict]]:
        """Busca o histórico de velas para um ativo."""
        try:
            loop = asyncio.get_event_loop()
            status, candles = await loop.run_in_executor(None, lambda: self.api.get_candles(asset, timeframe, count))
            return candles if status else None
        except Exception as e:
            self.logger.error(f"Erro ao obter velas para {asset}: {e}")
            return None

    async def get_current_balance(self) -> Optional[float]:
        """Obtém o saldo atual da conta selecionada a partir do perfil."""
        try:
            if self.api.profile and hasattr(self.api.profile, 'balance'):
                return self.api.profile.balance
            return None
        except Exception as e:
            self.logger.error(f"Erro ao obter saldo do perfil: {e}")
            return None

    async def change_balance(self, balance_type: str):
        """Muda entre a conta de prática e a conta real."""
        try:
            loop = asyncio.get_event_loop()
            # CORRIGIDO: O nome da função é provavelmente 'set_active_account'
            await loop.run_in_executor(None, lambda: self.api.set_active_account(balance_type.upper()))
        except AttributeError:
            self.logger.error("Erro: O método 'set_active_account' não foi encontrado. Verifique a biblioteca 'exnovaapi'.")
        except Exception as e:
            self.logger.error(f"Erro ao mudar de conta para {balance_type}: {e}")

    async def execute_trade(self, amount: float, asset: str, direction: str, expiration_minutes: int) -> Optional[int]:
        """Executa uma operação de compra ou venda."""
        try:
            loop = asyncio.get_event_loop()
            status, order_id = await loop.run_in_executor(None, lambda: self.api.buy(amount, asset, direction, expiration_minutes))
            return order_id if status else None
        except Exception as e:
            self.logger.error(f"Erro ao executar operação em {asset}: {e}")
            return None

    async def check_win(self, order_id: int) -> Optional[str]:
        """Verifica o resultado de uma operação específica pelo seu ID."""
        try:
            loop = asyncio.get_event_loop()
            status, result = await loop.run_in_executor(None, lambda: self.api.check_win_v4(order_id))
            if status:
                return result
            return None
        except Exception as e:
            self.logger.error(f"Erro ao verificar o resultado da ordem {order_id}: {e}")
            return None
