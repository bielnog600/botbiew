import asyncio
import logging
from typing import List, Optional, Dict

# Usando um estilo de importação mais explícito para evitar conflitos
import exnovaapi.api as exnova_api_module

class AsyncExnovaService:
    def __init__(self, email: str, password: str):
        # CORRIGIDO: O nome da classe é 'Exnovaapi' com 'a' minúsculo.
        self.api = exnova_api_module.Exnovaapi(email, password)
        self.logger = logging.getLogger(__name__)

    async def connect(self) -> bool:
        """Conecta-se à API da Exnova."""
        try:
            await self.api.connect()
            return True
        except Exception as e:
            self.logger.error(f"Falha na conexão com a Exnova: {e}")
            return False

    async def get_open_assets(self) -> List[str]:
        """Obtém a lista de ativos abertos para negociação."""
        try:
            return await self.api.get_all_open_assets()
        except Exception as e:
            self.logger.error(f"Erro ao obter ativos abertos: {e}")
            return []

    async def get_historical_candles(self, asset: str, timeframe: int, count: int) -> Optional[List[Dict]]:
        """Busca o histórico de velas para um ativo."""
        try:
            return await self.api.get_candles(asset, timeframe, count)
        except Exception as e:
            self.logger.error(f"Erro ao obter velas para {asset}: {e}")
            return None

    async def get_current_balance(self) -> Optional[float]:
        """Obtém o saldo atual da conta selecionada."""
        try:
            return await self.api.get_balance()
        except Exception as e:
            self.logger.error(f"Erro ao obter saldo: {e}")
            return None

    async def change_balance(self, balance_type: str):
        """Muda entre a conta de prática e a conta real."""
        try:
            await self.api.change_balance(balance_type.upper())
        except Exception as e:
            self.logger.error(f"Erro ao mudar de conta para {balance_type}: {e}")

    async def execute_trade(self, amount: float, asset: str, direction: str, expiration_minutes: int) -> Optional[int]:
        """Executa uma operação de compra ou venda."""
        try:
            status, order_id = await self.api.buy(amount, asset, direction, expiration_minutes)
            if status:
                return order_id
            return None
        except Exception as e:
            self.logger.error(f"Erro ao executar operação em {asset}: {e}")
            return None

    async def check_win(self, order_id: int) -> Optional[str]:
        """
        Verifica o resultado de uma operação específica pelo seu ID.
        Retorna 'win', 'loss', 'equal' ou None em caso de erro.
        """
        try:
            for _ in range(3):
                status, result = await self.api.check_win_v4(order_id)
                if status:
                    self.logger.info(f"Resultado da ordem {order_id} obtido: {result}")
                    return result
                await asyncio.sleep(2)
            
            self.logger.warning(f"Não foi possível obter o resultado para a ordem {order_id} após várias tentativas.")
            return None
        except Exception as e:
            self.logger.error(f"Erro ao verificar o resultado da ordem {order_id}: {e}")
            return None
