import asyncio
import logging
from typing import List, Optional, Dict
from exnovaapi.api import Exnovaapi

class AsyncExnovaService:
    def __init__(self, email: str, password: str):
        self.api = Exnovaapi(email, password)
        self.logger = logging.getLogger(__name__)

    async def connect(self) -> bool:
        """Conecta-se à API da Exnova."""
        try:
            loop = asyncio.get_event_loop()
            # CORRIGIDO: O nome correto da função é 'connect'
            check, reason = await loop.run_in_executor(None, self.api.connect)
            if check:
                self.logger.info("Conexão com a Exnova estabelecida com sucesso.")
                return True
            else:
                self.logger.error(f"Falha na conexão com a Exnova: {reason}")
                return False
        except Exception as e:
            self.logger.error(f"Erro crítico na conexão: {e}")
            return False

    async def get_open_assets(self) -> List[str]:
        """Obtém a lista de ativos abertos para negociação."""
        try:
            loop = asyncio.get_event_loop()
            # CORRIGIDO: O nome correto da função é 'get_all_open_time'
            all_assets = await loop.run_in_executor(None, self.api.get_all_open_time)
            return [asset for asset, data in all_assets.items() if data.get('open')]
        except Exception as e:
            self.logger.error(f"Erro ao obter ativos abertos: {e}")
            return []

    async def get_historical_candles(self, asset: str, timeframe: int, count: int) -> Optional[List[Dict]]:
        """Busca o histórico de velas para um ativo."""
        try:
            loop = asyncio.get_event_loop()
            # O nome correto da função é 'get_candles'
            status, candles = await loop.run_in_executor(None, lambda: self.api.get_candles(asset, timeframe, count))
            return candles if status else None
        except Exception as e:
            self.logger.error(f"Erro ao obter velas para {asset}: {e}")
            return None

    async def get_current_balance(self) -> Optional[float]:
        """Obtém o saldo atual da conta selecionada."""
        try:
            loop = asyncio.get_event_loop()
            # CORRIGIDO: O nome correto da função é 'get_balance'
            return await loop.run_in_executor(None, self.api.get_balance)
        except Exception as e:
            self.logger.error(f"Erro ao obter saldo: {e}")
            return None

    async def change_balance(self, balance_type: str):
        """Muda entre a conta de prática e a conta real."""
        try:
            loop = asyncio.get_event_loop()
            # O nome correto da função é 'change_balance'
            await loop.run_in_executor(None, lambda: self.api.change_balance(balance_type.upper()))
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
            # O nome correto da função é 'check_win_v4'
            status, result = await loop.run_in_executor(None, lambda: self.api.check_win_v4(order_id))
            if status:
                self.logger.info(f"Resultado da ordem {order_id} obtido: {result}")
                return result
            return None
        except Exception as e:
            self.logger.error(f"Erro ao verificar o resultado da ordem {order_id}: {e}")
            return None
