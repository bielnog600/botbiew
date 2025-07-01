# core/bot.py
import asyncio
import time
import traceback
from datetime import datetime, timedelta
from typing import List, Dict, Optional

from config import settings
from services.exnova_service import AsyncExnovaService
from services.supabase_service import SupabaseService
from analysis.strategy import STRATEGIES
from core.data_models import TradeSignal, ActiveTrade, Candle

class TradingBot:
    def __init__(self):
        self.supabase = SupabaseService(settings.SUPABASE_URL, settings.SUPABASE_KEY)
        self.exnova = AsyncExnovaService(settings.EXNOVA_EMAIL, settings.EXNOVA_PASSWORD)
        self.is_running = True
        self.bot_config = {}
        self.trade_queue = asyncio.Queue()
        # Dicionário para guardar os setups encontrados no início do minuto
        self.pending_setups: Dict[str, Dict] = {}
        self.martingale_state: Dict[str, Dict] = {}

    async def logger(self, level: str, message: str):
        print(f"[{level.upper()}] {message}")
        await self.supabase.insert_log(level, message)

    async def run(self):
        await self.logger('INFO', 'Bot a iniciar...')
        await self.exnova.connect()
        await self.logger('SUCCESS', f"Conexão com a Exnova estabelecida.")
        
        # Inicia o loop de verificação de resultados em segundo plano
        asyncio.create_task(self._result_checker_loop())

        while self.is_running:
            try:
                self.bot_config = await self.supabase.get_bot_config()
                if self.bot_config.get('status') == 'RUNNING':
                    await self.trading_cycle()
                else:
                    await self.logger('INFO', 'Bot em modo PAUSADO. A aguardar...')
                    await asyncio.sleep(15)
            except Exception as e:
                await self.logger('ERROR', f"Erro fatal no loop principal: {e}")
                traceback.print_exc()
                await asyncio.sleep(30)

    async def trading_cycle(self):
        """Ciclo principal que gere a análise em duas fases."""
        # --- FASE 1: Identificação de Setups (Início do Minuto) ---
        await self._wait_for_minute_start()
        await self._find_setups()

        if not self.pending_setups:
            return

        # --- FASE 2: Confirmação de Gatilhos (Meio do Minuto) ---
        await self._wait_for_mid_minute()
        await self._check_and_execute_breakouts()

    async def _wait_for_minute_start(self):
        """Espera até 2 segundos após a viragem do minuto."""
        now = datetime.now()
        wait_time = (60 - now.second) + 2 if now.second > 2 else 2 - now.second
        await asyncio.sleep(wait_time)

    async def _wait_for_mid_minute(self):
        """Espera até o segundo 32 do minuto atual."""
        now = datetime.now()
        target_second = 15
        if now.second < target_second:
            await asyncio.sleep(target_second - now.second)

    async def _find_setups(self):
        """Busca por setups de negociação em todos os ativos abertos."""
        await self.logger('INFO', "Nova vela M1. A procurar por setups...")
        self.pending_setups.clear()
        open_assets = await self.exnova.get_open_assets()
        
        tasks = [self._analyze_for_setup(asset) for asset in open_assets[:settings.MAX_CONCURRENT_ASSETS]]
        await asyncio.gather(*tasks)

        if self.pending_setups:
            setup_keys = list(self.pending_setups.keys())
            await self.logger('SUCCESS', f"Setups encontrados em: {setup_keys}. A aguardar confirmação de rompimento...")

    async def _analyze_for_setup(self, full_asset_name: str):
        """Analisa um único ativo para encontrar um setup."""
        clean_asset_name = full_asset_name.split('-')[0]
        candles = await self.exnova.get_historical_candles(clean_asset_name, 60, 100)
        if not candles: return

        for strategy in STRATEGIES:
            setup = strategy.find_setup(candles)
            if setup:
                self.pending_setups[full_asset_name] = setup
                break

    async def _check_and_execute_breakouts(self):
        """Verifica os setups pendentes e executa as ordens se houver rompimento."""
        if not self.pending_setups: return

        await self.logger('INFO', "Meio do minuto. A verificar rompimentos...")
        tasks = [self._check_single_breakout(asset, setup) for asset, setup in self.pending_setups.items()]
        await asyncio.gather(*tasks)
        self.pending_setups.clear()

    async def _check_single_breakout(self, full_asset_name: str, setup: Dict):
        """Verifica o rompimento para um único ativo."""
        clean_asset_name = full_asset_name.split('-')[0]
        live_candles = await self.exnova.get_historical_candles(clean_asset_name, 60, 1)
        if not live_candles: return

        live_price = live_candles[0].close
        direction = setup['direction']
        breakout_level = setup['breakout_level']

        if direction == 'call' and live_price > breakout_level:
            await self.logger('SUCCESS', f"[{full_asset_name}] ROMPIMENTO DE ALTA CONFIRMADO!")
            signal = TradeSignal(pair=clean_asset_name, direction='call', strategy=setup['strategy'], volatility_score=0)
            await self._execute_trade(signal, full_asset_name)
        
        elif direction == 'put' and live_price < breakout_level:
            await self.logger('SUCCESS', f"[{full_asset_name}] ROMPIMENTO DE BAIXA CONFIRMADO!")
            signal = TradeSignal(pair=clean_asset_name, direction='put', strategy=setup['strategy'], volatility_score=0)
            await self._execute_trade(signal, full_asset_name)

    def _get_entry_value(self, asset: str) -> float:
        base_value = self.bot_config.get('entry_value', 1.0)
        use_mg = self.bot_config.get('use_martingale', False)
        if not use_mg: return base_value
        asset_mg_state = self.martingale_state.get(asset, {'level': 0, 'last_value': base_value})
        if asset_mg_state['level'] == 0: return base_value
        mg_factor = self.bot_config.get('martingale_factor', 2.3)
        next_value = asset_mg_state['last_value'] * mg_factor
        return round(next_value, 2)

    async def _execute_trade(self, signal: TradeSignal, full_asset_name: str):
        try:
            entry_value = self._get_entry_value(signal.pair)
            signal_id = await self.supabase.insert_trade_signal(signal)
            if not signal_id:
                await self.logger('ERROR', f"[{signal.pair}] Falha ao registrar sinal.")
                return

            order_id = await self.exnova.execute_trade(entry_value, full_asset_name, signal.direction, 1)
            if order_id:
                await self.logger('SUCCESS', f"[{signal.pair}] Ordem {order_id} (sinal ID: {signal_id}) enviada.")
                active_trade = ActiveTrade(order_id=str(order_id), signal_id=signal_id, pair=signal.pair, entry_value=entry_value)
                await self.trade_queue.put(active_trade)
            else:
                await self.logger('ERROR', f"[{signal.pair}] Falha na execução da ordem na Exnova para '{full_asset_name}'.")
                await self.supabase.update_trade_result(signal_id, "ERROR")
        except Exception as e:
            await self.logger('ERROR', f"Exceção não tratada em _execute_trade para {signal.pair}: {e}")
            traceback.print_exc()

    async def _result_checker_loop(self):
        while self.is_running:
            try:
                trade = await asyncio.wait_for(self.trade_queue.get(), timeout=1.0)
                result = None
                for _ in range(15):
                    result = await self.exnova.check_trade_result(trade.order_id)
                    if result: break
                    await asyncio.sleep(5)
                
                if result:
                    await self.logger('SUCCESS' if result == 'WIN' else 'ERROR', f"[{trade.pair}] Resultado da ordem {trade.order_id}: {result}")
                    await self.supabase.update_trade_result(trade.signal_id, result)
                    self._update_martingale_state(trade.pair, result, trade.entry_value)
                else:
                    await self.logger('WARNING', f"[{trade.pair}] Timeout ao obter resultado da ordem {trade.order_id}.")
                    await self.supabase.update_trade_result(trade.signal_id, "TIMEOUT")
                
                self.trade_queue.task_done()
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                await self.logger('ERROR', f"Erro no loop de verificação de resultados: {e}")

    def _update_martingale_state(self, asset: str, result: str, last_value: float):
        if not self.bot_config.get('use_martingale', False): return
        max_levels = self.bot_config.get('martingale_levels', 2)
        current_level = self.martingale_state.get(asset, {}).get('level', 0)
        if result == 'WIN':
            self.martingale_state[asset] = {'level': 0, 'last_value': self.bot_config.get('entry_value', 1.0)}
            asyncio.create_task(self.logger('INFO', f"[{asset}] Martingale resetado após WIN."))
        elif result == 'LOSS':
            if current_level < max_levels:
                self.martingale_state[asset] = {'level': current_level + 1, 'last_value': last_value}
                asyncio.create_task(self.logger('WARNING', f"[{asset}] LOSS. A ativar Martingale nível {current_level + 1}."))
            else:
                self.martingale_state[asset] = {'level': 0, 'last_value': self.bot_config.get('entry_value', 1.0)}
                asyncio.create_task(self.logger('ERROR', f"[{asset}] Limite de Martingale ({max_levels}) atingido. A resetar."))
