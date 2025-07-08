import logging
from exnovaapi.api import ExnovaAPI
from typing import List, Optional

class AsyncExnovaService:
    def __init__(self, email: str, password: str):
        self.api = ExnovaAPI(email, password)
        self.logger = logging.getLogger(__name__)

    async def connect(self) -> bool:
        # ... (código inalterado) ...

    async def get_open_assets(self) -> List[str]:
        # ... (código inalterado) ...

    async def get_historical_candles(self, asset: str, timeframe: int, count: int) -> Optional[List[Dict]]:
        # ... (código inalterado) ...

    async def get_current_balance(self) -> Optional[float]:
        # ... (código inalterado) ...

    async def change_balance(self, balance_type: str):
        # ... (código inalterado) ...

    async def execute_trade(self, amount: float, asset: str, direction: str, expiration_minutes: int) -> Optional[int]:
        # ... (código inalterado) ...

    # NOVO: Método para verificar o resultado de uma ordem específica
    async def check_win(self, order_id: int) -> Optional[str]:
        """
        Verifica o resultado de uma operação específica pelo seu ID.
        Retorna 'win', 'loss', 'equal' ou None em caso de erro.
        """
        try:
            # A API pode demorar um pouco para ter o resultado, então tentamos algumas vezes.
            for _ in range(3): # Tenta 3 vezes
                status, result = await self.api.check_win_v4(order_id)
                if status:
                    self.logger.info(f"Resultado da ordem {order_id} obtido: {result}")
                    return result
                await asyncio.sleep(2) # Espera 2 segundos antes de tentar novamente
            
            self.logger.warning(f"Não foi possível obter o resultado para a ordem {order_id} após várias tentativas.")
            return None
        except Exception as e:
            self.logger.error(f"Erro ao verificar o resultado da ordem {order_id}: {e}")
            return None

