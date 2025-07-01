# core/bot.py
import asyncio
import time
import traceback
from typing import List, Dict

from config import settings
from services.exnova_service import AsyncExnovaService
from services.supabase_service import SupabaseService
from analysis.strategy import STRATEGIES
from analysis.technical import calculate_volatility
from core.data_models import TradeSignal, ActiveTrade

class TradingBot:
    def __init__(self):
        self.supabase = SupabaseService(settings.SUPABASE_URL, settings.SUPABASE_KEY)
        self.exnova = AsyncExnovaService(settings.EXNOVA_EMAIL, settings.EXNOVA_PASSWORD)
        self.active_assets: List[str] = []
        self.trade_queue = asyncio.Queue()
        self.is_running = True
        self.bot_config = {}
        self.martingale_state: Dict[str, Dict] = {}

    async def logger(self, level: str, message: str):
        print(f"[{level.upper()}] {message}")
        await self.supabase.insert_log(level, message)

    async def run(self):
        await self.logger('INFO', 'Bot a iniciar...')
        await self.exnova.connect()
        await self.logger('SUCCESS', f"Conexão com a Exnova estabelecida.")
        
        while self.is_running:
            try:
                self.bot_config = await self.supabase.get_bot_config()
                bot_status = self.bot_config.get('status', 'PAUSED')

                if bot_status == 'RUNNING':
                    operation_mode = self.bot_config.get('operation_mode', 'CONSERVADOR')
                    await self.logger('INFO', f"Bot em modo RUNNING ({operation_mode}). A iniciar ciclo de negociação...")
                    await self.trading_loop()
                else:
                    await self.logger('INFO', 'Bot em modo PAUSADO. A aguardar...')
                    await asyncio.sleep(15)

            except Exception as e:
                await self.logger('ERROR', f"Erro fatal no loop principal: {e}")
                traceback.print_exc()
                await asyncio.sleep(30)

    async def trading_loop(self):
        account_type = self.bot_config.get('account_type', 'PRACTICE')
        await self.logger('INFO', f"A usar a conta: {account_type}")
        await self.exnova.change_balance(account_type)

        # Atualiza o saldo da conta no painel
        current_balance = await self.exnova.get_current_balance()
        if current_balance is not None:
            await self.supabase.update_current_balance(current_balance)
            await self.logger('INFO', f"Saldo da conta atualizado: ${current_balance:.2f}")

        self.active_assets = await self.exnova.get_open_assets()
        self.active_assets = self.active_assets[:settings.MAX_CONCURRENT_ASSETS]
        
        trading_tasks = [self._process_asset_task(asset) for asset in self.active_assets]
        result_checker_task = asyncio.create_task(self._result_checker_loop())
        
        done, pending = await asyncio.wait(
            trading_tasks + [result_checker_task], 
            timeout=60, 
            return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
    
    # O resto do código (_process_asset_task, _execute_trade, etc.) permanece o mesmo
    # ... (código omitido para brevidade) ...
