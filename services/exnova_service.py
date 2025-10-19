import asyncio
import logging
from typing import List, Optional, Dict
from exnovaapi.api import Exnovaapi

class AsyncExnovaService:
    def __init__(self, email: str, password: str):
        self.api = Exnovaapi(email, password)
        self.logger = logging.getLogger(__name__)
        self.api.profile = None

    async def connect(self) -> bool:
        try:
            loop = asyncio.get_event_loop()
            check, reason = await loop.run_in_executor(None, self.api.connect)
            if not check:
                self.logger.error(f"Falha na conexão com a Exnova: {reason}")
                return False
            
            for _ in range(15): 
                if hasattr(self.api, 'profile') and self.api.profile is not None and self.api.get_balances():
                    self.logger.info("Conexão e dados iniciais carregados com sucesso.")
                    return True
                await asyncio.sleep(1)
            
            self.logger.error("Conexão estabelecida, mas os dados do utilizador não foram carregados a tempo.")
            return False
        except Exception as e:
            self.logger.error(f"Erro crítico na conexão: {e}")
            return False

    async def get_open_assets(self) -> List[str]:
        try:
            loop = asyncio.get_event_loop()
            all_assets_data = await loop.run_in_executor(None, self.api.get_api_option_init_all_v2)
            
            if not all_assets_data:
                self.logger.warning("A API não retornou dados de ativos.")
                return []

            tradables = all_assets_data.get('binary', {}).get('actives', {})
            if not tradables:
                tradables = all_assets_data.get('turbo', {}).get('actives', {})

            return [asset for asset, data in tradables.items() if data.get('open')]
        except Exception as e:
            self.logger.error(f"Erro ao obter ativos abertos: {e}")
            return []

    async def get_historical_candles(self, asset: str, timeframe: int, count: int) -> Optional[List[Dict]]:
        try:
            loop = asyncio.get_event_loop()
            status, candles = await loop.run_in_executor(None, lambda: self.api.getcandles(asset, timeframe, count))
            return candles if status else None
        except Exception as e:
            self.logger.error(f"Erro ao obter velas para {asset}: {e}")
            return None

    async def get_current_balance(self) -> Optional[float]:
        try:
            loop = asyncio.get_event_loop()
            balances_data = await loop.run_in_executor(None, self.api.get_balances)
            if balances_data and balances_data.get('msg'):
                for balance_info in balances_data['msg']:
                    if balance_info.get('is_active'):
                        return balance_info.get('amount')
            
            if self.api.profile and hasattr(self.api.profile, 'balance'):
                return self.api.profile.balance

            self.logger.warning("Não foi possível encontrar o saldo da conta ativa.")
            return None
        except Exception as e:
            self.logger.error(f"Erro ao obter saldo: {e}")
            return None

    async def change_balance(self, balance_type: str):
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: self.api.changebalance(balance_type.upper()))
        except Exception as e:
            self.logger.warning(f"Ocorreu um erro esperado ao mudar de conta para {balance_type} (pode ser ignorado): {e}")

    async def execute_trade(self, amount: float, asset: str, direction: str, expiration_minutes: int) -> Optional[int]:
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
            # Tenta usar a versão v4, que é mais comum
            if hasattr(self.api, 'check_win_v4'):
                 status, result = await loop.run_in_executor(None, lambda: self.api.check_win_v4(order_id))
                 if status:
                     return result.lower() if result else None
            # Fallback para a versão v3
            elif hasattr(self.api, 'check_win_v3'):
                 is_win, _ = await loop.run_in_executor(None, lambda: self.api.check_win_v3(order_id))
                 return 'win' if is_win else 'loss'
            
            self.logger.error("Nenhum método check_win (v3 ou v4) encontrado na API.")
            return None
        except Exception as e:
            self.logger.error(f"Erro ao verificar o resultado da ordem {order_id}: {e}")
            return None
