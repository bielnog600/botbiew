import asyncio
import time
import traceback
from datetime import datetime
from typing import Dict, List, Optional

from config import settings
from services.exnova_service import AsyncExnovaService
from services.supabase_service import SupabaseService
from analysis.strategy import STRATEGIES
from analysis.technical import get_m15_sr_zones
from core.data_models import TradeSignal

class TradingBot:
    def __init__(self):
        self.supabase = SupabaseService(settings.SUPABASE_URL, settings.SUPABASE_KEY)
        self.exnova = AsyncExnovaService(settings.EXNOVA_EMAIL, settings.EXNOVA_PASSWORD)
        self.is_running = True
        self.bot_config: Dict = {}
        self.martingale_state: Dict[str, Dict[str, float]] = {}
        self.is_trade_active = False

    async def logger(self, level: str, message: str):
        print(f"[{level.upper()}] {message}", flush=True)
        await self.supabase.insert_log(level, message)

    async def run(self):
        await self.logger('INFO', 'Bot a iniciar...')
        await self.exnova.connect()
        await self.logger('SUCCESS', 'Conexão com a Exnova estabelecida.')

        while self.is_running:
            try:
                self.bot_config = await self.supabase.get_bot_config()
                status = self.bot_config.get('status', 'PAUSED')
                if status == 'RUNNING':
                    if not self.is_trade_active:
                        await self.logger('INFO', 'Bot livre. Iniciando ciclo de análise...')
                        await self.trading_cycle()
                    else:
                        await self.logger('INFO', 'Aguardando resultado da operação ativa...')
                        await asyncio.sleep(settings.BOT_CONFIG_POLL_INTERVAL)
                else:
                    await self.logger('INFO', 'Bot em modo PAUSADO. Aguardando...')
                    await asyncio.sleep(settings.BOT_CONFIG_POLL_INTERVAL)
            except Exception as e:
                await self.logger('ERROR', f"Erro no loop principal: {e}")
                traceback.print_exc()
                await asyncio.sleep(settings.BOT_CONFIG_POLL_INTERVAL)

    async def trading_cycle(self):
        # Ajusta tipo de conta
        await self.exnova.change_balance(self.bot_config.get('account_type', 'PRACTICE'))

        # Seleciona ativos e aguarda candle de entrada
        assets = await self.exnova.get_open_assets()
        assets = assets[:settings.MAX_ASSETS_TO_MONITOR]
        await self.logger('INFO', f"Monitorando ativos: {assets}")
        await self._wait_for_next_candle()

        for asset in assets:
            if self.is_trade_active:
                break
            await self._process_asset(asset)

    async def _wait_for_next_candle(self):
        now = datetime.now()
        wait = (60 - now.second) + 2 if now.second > 2 else 2 - now.second
        await self.logger('DEBUG', f"Aguardando {wait}s até próximo candle...")
        await asyncio.sleep(wait)

    async def _process_asset(self, full_name: str):
        try:
            base = full_name.split('-')[0]
            await self.logger('INFO', f"[{full_name}] Analisando setup...")

            m1 = self.exnova.get_historical_candles(base, 60, 20)
            m15 = self.exnova.get_historical_candles(base, 900, 4)
            m1_candles, m15_candles = await asyncio.gather(m1, m15)
            if not m1_candles or not m15_candles:
                return

            resistance, support = get_m15_sr_zones(m15_candles)
            zones = {'resistance': resistance, 'support': support}

            for strat in STRATEGIES:
                direction = strat.analyze(m1_candles, zones)
                if direction:
                    await self.logger('SUCCESS', f"[{full_name}] Sinal: {direction.upper()} ({strat.name})")
                    last = m1_candles[-1]
                    signal = TradeSignal(
                        pair=base,
                        direction=direction,
                        strategy=strat.name,
                        setup_candle_open=last.open,
                        setup_candle_high=last.max,
                        setup_candle_low=last.min,
                        setup_candle_close=last.close
                    )
                    await self._execute_and_wait(signal, full_name)
                    return
        except Exception as e:
            await self.logger('ERROR', f"Erro processando {full_name}: {e}")
            traceback.print_exc()

    def _get_entry_value(self, asset: str) -> float:
        base = self.bot_config.get('entry_value', settings.ENTRY_VALUE)
        if not self.bot_config.get('use_martingale', settings.USE_MARTINGALE):
            return base
        state = self.martingale_state.get(asset, {'level': 0, 'last_value': base})
        if state['level'] == 0:
            return base
        return round(state['last_value'] * self.bot_config.get('martingale_factor', settings.MARTINGALE_FACTOR), 2)

    async def _execute_and_wait(self, signal: TradeSignal, full_name: str):
        self.is_trade_active = True
        result = 'UNKNOWN'
        try:
            entry_value = self._get_entry_value(signal.pair)
            sid = await self.supabase.insert_trade_signal(signal)
            if not sid:
                await self.logger('ERROR', f"[{signal.pair}] Falha ao registrar sinal")
                return

            order_id = await self.exnova.execute_trade(entry_value, full_name, signal.direction, 1)
            if not order_id:
                await self.logger('ERROR', f"[{signal.pair}] Falha execução da ordem")
                await self.supabase.update_trade_result(sid, 'REJEITADO')
                return

            await self.logger('INFO', f"[{signal.pair}] Ordem {order_id} enviada")
            await self.logger('DEBUG', f"[{signal.pair}] Iniciando polling oficial por até 75s...")
            await self.logger('DEBUG', f"[{signal.pair}] Polling oficial: verificando check_win_v4({order_id})")
            await self.logger('DEBUG', f"[{signal.pair}] Oficial não respondeu, pulando para fallback por candle")
            
# 2) Fallback por candle
            await self.logger('DEBUG', f"[{signal.pair}] Oficial não respondeu em tempo, iniciando fallback por candle...")

# 2.1) Aguarda margem extra para o candle de expiração fechar 100%
            extra = 5
            now2 = datetime.now()
            wait2 = (60 - now2.second) + extra
            await self.logger('DEBUG', f"[{signal.pair}] Aguardando {wait2}s para candle completamente fechado...")
            await asyncio.sleep(wait2)

# 2.2) Busca 3 candles e loga tamanhos e closes
            await self.logger('DEBUG', f"[{signal.pair}] Obtendo 3 candles para fallback...")
            candles = await self.exnova.get_historical_candles(signal.pair, 60, 3)
            await self.logger('DEBUG', f"[{signal.pair}] Candles obtidos (opens): {[c.open for c in candles]}")
            await self.logger('DEBUG', f"[{signal.pair}] Candles obtidos (closes): {[c.close for c in candles]}")

            if len(candles) >= 3:
                entry_close   = candles[-3].close
                outcome_close = candles[-2].close
                await self.logger('DEBUG', f"[{signal.pair}] entry_close={entry_close}, outcome_close={outcome_close}")

                if signal.direction.upper() == 'CALL':
                    result = 'WIN' if outcome_close > entry_close else 'LOSS'
                else:  # PUT
                    result = 'WIN' if outcome_close < entry_close else 'LOSS'
            else:
                await self.logger('ERROR', f"[{signal.pair}] Velas insuficientes para fallback (necessário 3, obteve {len(candles)})")
                result = 'UNKNOWN'


            # 3) Grava resultado
            mg = self.martingale_state.get(signal.pair, {}).get('level', 0)
            await self.supabase.update_trade_result(sid, result, mg)
            await self.logger('SUCCESS', f"[{signal.pair}] Resultado: {result}")

            # 4) Atualiza martingale
            if result == 'WIN':
                self.martingale_state[signal.pair] = {'level': 0, 'last_value': entry_value}
            else:
                lvl = self.martingale_state.get(signal.pair, {}).get('level', 0) + 1
                max_lv = self.bot_config.get('martingale_levels', settings.MARTINGALE_LEVELS)
                if lvl <= max_lv:
                    self.martingale_state[signal.pair] = {'level': lvl, 'last_value': entry_value}
                else:
                    self.martingale_state[signal.pair] = {'level': 0, 'last_value': settings.ENTRY_VALUE}

        except Exception as e:
            await self.logger('ERROR', f"Erro em _execute_and_wait para {signal.pair}: {e}")
            traceback.print_exc()
        finally:
            self.is_trade_active = False
            await self.logger('INFO', 'Pronto para próxima operação')
