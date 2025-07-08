import asyncio
import logging
import time # ADICIONADO: Importação do módulo 'time' que estava em falta
from typing import List, Optional, Dict
from exnovaapi.stable_api import Exnova

class AsyncExnovaService:
    def __init__(self, email: str, password: str):
        self.api = Exnova(email, password)
        self.logger = logging.getLogger(__name__)
        self.api.profile = None

    async def connect(self) -> bool:
        """Conecta-se à API da Exnova e aguarda os dados essenciais serem carregados."""
        try:
            loop = asyncio.get_event_loop()
            check, reason = await loop.run_in_executor(None, self.api.connect)
            if not check:
                self.logger.error(f"Falha na conexão com a Exnova: {reason}")
                return False
            
            for _ in range(15): 
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
            loop = asyncio.get_event_loop()
            all_assets_data = await loop.run_in_executor(None, self.api.get_all_init_data)
            
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
        """Busca o histórico de velas para um ativo."""
        try:
            loop = asyncio.get_event_loop()
            # CORRIGIDO: Agora a chamada a time.time() funciona porque o módulo foi importado
            candles = await loop.run_in_executor(None, lambda: self.api.get_candles(asset, timeframe, count, time.time()))
            return candles
        except Exception as e:
            self.logger.error(f"Erro ao obter velas para {asset}: {e}")
            return None

    async def get_current_balance(self) -> Optional[float]:
        """Obtém o saldo atual da conta selecionada."""
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
        """Muda entre a conta de prática e a conta real."""
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: self.api.change_balance(balance_type.upper()))
        except Exception as e:
            self.logger.warning(f"Ocorreu um erro esperado ao mudar de conta para {balance_type} (pode ser ignorado): {e}")

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
                return result.lower() if result else None
            return None
        except Exception as e:
            self.logger.error(f"Erro ao verificar o resultado da ordem {order_id}: {e}")
            return None
