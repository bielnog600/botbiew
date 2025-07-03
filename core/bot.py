# core/bot.py
import asyncio
import time
import traceback
from datetime import datetime
from typing import List, Dict, Optional

from config import settings
from services.exnova_service import AsyncExnovaService
from services.supabase_service import SupabaseService
from analysis.strategy import STRATEGIES
from analysis.technical import get_m15_sr_zones
from core.data_models import TradeSignal, ActiveTrade, Candle

class TradingBot:
    def __init__(self):
        self.supabase = SupabaseService(settings.SUPABASE_URL, settings.SUPABASE_KEY)
        self.exnova = AsyncExnovaService(settings.EXNOVA_EMAIL, settings.EXNOVA_PASSWORD)
        self.is_running = True
        self.bot_config: Dict = {}
        self.martingale_state: Dict[str, Dict] = {}
        # Novo estado para garantir que apenas uma operação é feita de cada vez.
        self.is_trade_active = False

    async def logger(self, level: str, message: str):
        print(f"[{level.upper()}] {message}", flush=True)
        await self.supabase.insert_log(level, message)

    async def run(self):
        await self.logger('INFO', 'Bot a iniciar...')
        await self.exnova.connect()
        await self.logger('SUCCESS', "Conexão com a Exnova estabelecida.")

        while self.is_running:
            try:
                self.bot_config = await self.supabase.get_bot_config()
                if self.bot_config.get('status') == 'RUNNING':
                    # A lógica agora verifica se já existe uma operação ativa.
                    if not self.is_trade_active:
                        await self.logger('INFO', "Bot livre. A iniciar ciclo de análise...")
                        await self.trading_cycle()
                    else:
                        await self.logger('INFO', "A aguardar resultado da operação ativa...")
                        await asyncio.sleep(5) # Espera 5s antes de verificar de novo
                else:
                    await self.logger('INFO', 'Bot em modo PAUSADO. A aguardar...')
                    await asyncio.sleep(15)
            except Exception as e:
                await self.logger('ERROR', f"Erro fatal no loop principal: {e}")
                traceback.print_exc()
                await asyncio.sleep(30)

    async def trading_cycle(self):
        """Ciclo que analisa os ativos em busca de um único sinal."""
        account_type = self.bot_config.get('account_type', 'PRACTICE')
        await self.exnova.change_balance(account_type)

        open_assets = await self.exnova.get_open_assets()
        assets_to_trade = open_assets[:settings.MAX_ASSETS_TO_MONITOR]
        
        await self.logger('INFO', f"Ativos a serem monitorizados: {assets_to_trade}")

        await self._wait_for_next_candle()
        
        # A análise agora é sequencial para encontrar a primeira melhor oportunidade.
        for full_asset_name in assets_to_trade:
            # Se uma operação for aberta, o bot fica ocupado e para de procurar.
            if self.is_trade_active:
                break
            await self._process_asset_task(full_asset_name)

    async def _wait_for_next_candle(self):
        now = datetime.now()
        target_second = 58
        if now.second < target_second:
            wait_time = target_second - now.second
        else:
            wait_time = (60 - now.second) + target_second
        
        await self.logger('INFO', f"A aguardar {wait_time}s para o ponto de entrada...")
        await asyncio.sleep(wait_time)

    async def _process_asset_task(self, full_asset_name: str):
        try:
            clean_asset_name = full_asset_name.split('-')[0]
            
            await self.logger('INFO', f"[{full_asset_name}] Ponto de entrada! Analisando...")
            
            m1_candles_task = self.exnova.get_historical_candles(clean_asset_name, 60, 20)
            m15_candles_task = self.exnova.get_historical_candles(clean_asset_name, 900, 4)
            m1_candles, m15_candles = await asyncio.gather(m1_candles_task, m15_candles_task)
            
            if not m1_candles or not m15_candles: return

            resistance, support = get_m15_sr_zones(m15_candles)
            m15_zones = {'resistance': resistance, 'support': support}

            for strategy in STRATEGIES:
                direction = strategy.analyze(m1_candles, m15_zones)
                if direction:
                    await self.logger('SUCCESS', f"[{full_asset_name}] Sinal confirmado! Direção: {direction.upper()}, Estratégia: {strategy.name}")
                    
                    last_candle = m1_candles[-1]
                    signal = TradeSignal(
                        pair=clean_asset_name, 
                        direction=direction, 
                        strategy=strategy.name,
                        setup_candle_open=last_candle.open,
                        setup_candle_high=last_candle.max,
                        setup_candle_low=last_candle.min,
                        setup_candle_close=last_candle.close
                    )
                    # Executa o trade e espera pela sua conclusão
                    await self._execute_and_wait_for_trade(signal, full_asset_name)
                    return 
        except Exception as e:
            await self.logger('ERROR', f"Erro ao processar o ativo {full_asset_name}: {e}")
            traceback.print_exc()

    def _get_entry_value(self, asset: str) -> float:
        base_value = self.bot_config.get('entry_value', 1.0)
        use_mg = self.bot_config.get('use_martingale', False)
        if not use_mg: return base_value
        asset_mg_state = self.martingale_state.get(asset, {'level': 0, 'last_value': base_value})
        if asset_mg_state['level'] == 0: return base_value
        mg_factor = self.bot_config.get('martingale_factor', 2.3)
        next_value = asset_mg_state['last_value'] * mg_factor
        return round(next_value, 2)

    async def _execute_and_wait_for_trade(self, signal: TradeSignal, full_asset_name: str):
        self.is_trade_active = True
        try:
            entry_value = self._get_entry_value(signal.pair)
            
            signal_id = await self.supabase.insert_trade_signal(signal)
            if not signal_id:
                await self.logger('ERROR', f"[{signal.pair}] Falha ao registrar sinal.")
                self.is_trade_active = False
                return

            order_id = await self.exnova.execute_trade(entry_value, full_asset_name, signal.direction, 1)
            if order_id:
                await self.logger('SUCCESS', f"[{signal.pair}] Ordem {order_id} (sinal ID: {signal_id}) enviada. A aguardar resultado...")
                
                # Lógica de Polling Ativo, inspirada no seu bot original.
                expiration_time = time.time() + 75 # Timeout de 75 segundos
                result = None
                while time.time() < expiration_time:
                    status_tuple = await self.exnova.check_win_v4(order_id)
                    if status_tuple and status_tuple[0]: # Se o status não for None
                        status = status_tuple[0]
                        result = "WIN" if status == 'win' else "LOSS"
                        break
                    await asyncio.sleep(0.5) # Pausa curta entre verificações
                
                if result is None:
                    result = "UNKNOWN"
                
                current_mg_level = self.martingale_state.get(signal.pair, {}).get('level', 0)
                update_success = await self.supabase.update_trade_result(signal_id, result, current_mg_level)
                
                if update_success:
                    await self.logger('SUCCESS', f"[{signal.pair}] Resultado da ordem {order_id} atualizado para {result}.")
                else:
                    await self.logger('ERROR', f"[{signal.pair}] FALHA CRÍTICA ao atualizar o resultado da ordem {order_id} no Supabase.")
                
                self._update_martingale_state(signal.pair, result, entry_value)
            else:
                await self.logger('ERROR', f"[{signal.pair}] Falha na execução da ordem na Exnova para '{full_asset_name}'.")
                await self.supabase.update_trade_result(signal_id, "REJEITADO")
        
        except Exception as e:
            await self.logger('ERROR', f"Exceção não tratada em _execute_trade para {signal.pair}: {e}")
            traceback.print_exc()
        finally:
            self.is_trade_active = False
            await self.logger('INFO', "Bot libertado. Pronto para a próxima análise.")

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
