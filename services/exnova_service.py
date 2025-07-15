import asyncio
import logging
import time
from typing import List, Optional, Dict

# Importa a classe correta, como no seu bot antigo
from exnovaapi.stable_api import Exnova

class AsyncExnovaService:
    def __init__(self, email: str, password: str):
        self.api = Exnova(email, password)
        self.logger = logging.getLogger(__name__)
        self.api.profile = None # Inicializa o perfil como None
        self.connection_lock = asyncio.Lock() # Garante que apenas uma chamada à API é feita de cada vez
        self.is_connected = False

    async def _run_sync(self, func, *args, **kwargs):
        """Executa uma função síncrona da biblioteca de forma segura."""
        async with self.connection_lock:
            # Se a conexão caiu, tenta reconectar antes de cada ação
            if not self.is_connected:
                self.logger.warning("Conexão perdida. A tentar reconectar...")
                if not await self.connect():
                    self.logger.error("Falha na reconexão. A abortar a operação.")
                    return None
            
            try:
                loop = asyncio.get_running_loop()
                return await loop.run_in_executor(None, lambda: func(*args, **kwargs))
            except Exception as e:
                self.logger.error(f"Erro durante a execução da API: {e}. A marcar para reconexão.")
                self.is_connected = False # Marca a conexão como perdida
                return None

    async def connect(self) -> bool:
        """Conecta-se à API da Exnova e aguarda o perfil ser carregado."""
        try:
            loop = asyncio.get_event_loop()
            check, reason = await loop.run_in_executor(None, self.api.connect)
            if not check:
                self.logger.error(f"Falha na conexão com a Exnova: {reason}")
                self.is_connected = False
                return False
            
            # Chama explicitamente a função para carregar o perfil
            await loop.run_in_executor(None, self.api.get_profile_ansyc)
            
            # Aguarda o perfil ser carregado
            for _ in range(15): 
                if hasattr(self.api, 'profile') and self.api.profile is not None:
                    self.logger.info("Conexão e perfil carregados com sucesso.")
                    self.is_connected = True
                    return True
                await asyncio.sleep(1)
            
            self.logger.error("Conexão estabelecida, mas o perfil do utilizador não foi carregado a tempo.")
            self.is_connected = False
            return False
        except Exception as e:
            self.logger.error(f"Erro crítico na conexão: {e}")
            self.is_connected = False
            return False

    async def get_open_assets(self) -> List[str]:
        """Obtém a lista de ativos abertos para negociação."""
        response = await self._run_sync(self.api.get_all_open_time)
        if response is None: return []
        
        open_assets = []
        for market_type in ['binary', 'turbo']:
            if market_type in response:
                for asset, info in response[market_type].items():
                    if info.get('open', False):
                        open_assets.append(asset)
        return list(set(open_assets))

    async def get_historical_candles(self, asset: str, timeframe: int, count: int) -> Optional[List[Dict]]:
        """Busca o histórico de velas para um ativo."""
        response = await self._run_sync(self.api.get_candles, asset, timeframe, count, time.time())
        # A biblioteca retorna a lista de velas diretamente se for bem-sucedida
        return response if isinstance(response, list) else None

    async def get_current_balance(self) -> Optional[float]:
        """Obtém o saldo atual da conta selecionada."""
        return await self._run_sync(self.api.get_balance)

    async def change_balance(self, balance_type: str):
        """Muda entre a conta de prática e a conta real."""
        await self._run_sync(self.api.change_balance, balance_type.upper())

    async def execute_trade(self, amount: float, asset: str, direction: str, expiration_minutes: int) -> Optional[int]:
        """Executa uma operação de compra ou venda."""
        response = await self._run_sync(self.api.buy, amount, asset, direction, expiration_minutes)
        if response and isinstance(response, tuple) and len(response) == 2:
            status, order_id = response
            return order_id if status else None
        return None

    async def check_win(self, order_id: int) -> Optional[str]:
        """Verifica o resultado de uma operação específica pelo seu ID."""
        profit_or_loss = await self._run_sync(self.api.check_win_v3, order_id)
        if profit_or_loss is None:
            self.logger.warning(f"Não foi possível obter o resultado para a ordem {order_id}.")
            return None
        if profit_or_loss > 0: return 'WIN'
        elif profit_or_loss < 0: return 'LOSS'
        else: return 'DRAW'
