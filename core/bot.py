import asyncio
import time
import traceback
from datetime import datetime, timedelta
from typing import Dict

from config import settings
from services.exnova_service import AsyncExnovaService
from services.supabase_service import SupabaseService
from analysis.technical import get_m15_sr_zones, get_h1_sr_zones
from analysis import technical_indicators as ti
from core.data_models import TradeSignal

class TradingBot:
    def __init__(self):
        self.supabase = SupabaseService(settings.SUPABASE_URL, settings.SUPABASE_KEY)
        self.exnova = AsyncExnovaService(settings.EXNOVA_EMAIL, settings.EXNOVA_PASSWORD)
        self.is_running = True
        self.bot_config: Dict = {}
        self.martingale_state: Dict[str, Dict] = {}
        self.is_trade_active = False
        self.asset_performance: Dict[str, Dict[str, int]] = {}
        self.consecutive_losses: Dict[str, int] = {}
        self.blacklisted_assets: set = set()
        self.last_reset_time: datetime = datetime.utcnow()
        self.last_analysis_minute = -1
        self.daily_wins = 0
        self.daily_losses = 0

    async def logger(self, level: str, message: str):
        ts = datetime.utcnow().isoformat()
        print(f"[{ts}] [{level.upper()}] {message}", flush=True)
        await self.supabase.insert_log(level, message)

    async def _hourly_cycle_reset(self):
        await self.logger('INFO', "CICLO HORÁRIO CONCLUÍDO. A zerar estatísticas e a recatalogar todos os ativos.")
        self.asset_performance.clear()
        self.consecutive_losses.clear()
        self.blacklisted_assets.clear()
        self.last_reset_time = datetime.utcnow()
        self.daily_wins = 0
        self.daily_losses = 0
        
        bal = await self.exnova.get_current_balance()
        if bal is not None:
            await self.supabase.update_config({'daily_initial_balance': bal, 'current_balance': bal})
        
        await self.logger('SUCCESS', "Estatísticas e saldo diário zerados. A iniciar novo ciclo.")

    async def run(self):
        await self.logger('INFO', 'Bot a iniciar com GESTÃO DE RISCO ADAPTATIVA...')
        await self.exnova.connect()

        config = await self.supabase.get_bot_config()
        if config.get('daily_initial_balance', 0) == 0:
            await self.logger('INFO', "Primeira execução do dia. A definir o saldo inicial...")
            initial_balance = await self.exnova.get_current_balance()
            if initial_balance is not None:
                await self.supabase.update_config({
                    'daily_initial_balance': initial_balance,
                    'current_balance': initial_balance
                })
                await self.logger('SUCCESS', f"Saldo inicial do dia definido para: ${initial_balance:.2f}")

        while self.is_running:
            try:
                if (datetime.utcnow() - self.last_reset_time).total_seconds() >= 3600:
                    await self._hourly_cycle_reset()

                self.bot_config = await self.supabase.get_bot_config()
                status = self.bot_config.get('status', 'PAUSED')

                if status == 'RUNNING' and not self.is_trade_active:
                    await self.trading_cycle()
                else:
                    if status != 'RUNNING':
                        await self.logger('INFO', "Bot PAUSADO. Aguardando status 'RUNNING'.")
                    elif self.is_trade_active:
                         await self.logger('INFO', "Operação em andamento. Aguardando resultado...")
                
                await asyncio.sleep(1)

            except Exception as e:
                await self.logger('ERROR', f"Loop principal falhou: {e}")
                traceback.print_exc()
                await asyncio.sleep(30)

    async def trading_cycle(self):
        now = datetime.utcnow()
        if now.minute == self.last_analysis_minute:
            return

        if now.second < 5:
            self.last_analysis_minute = now.minute
            
            if now.minute % 5 == 0:
                asyncio.create_task(self.run_analysis_for_timeframe(300, 5))
            else:
                asyncio.create_task(self.run_analysis_for_timeframe(60, 1))

    async def run_analysis_for_timeframe(self, timeframe_seconds: int, expiration_minutes: int):
        await self.logger('INFO', f"Iniciando ciclo de análise para M{expiration_minutes}...")
        await self.exnova.change_balance(self.bot_config.get('account_type', 'PRACTICE'))
        assets = await self.exnova.get_open_assets()
        
        available_assets = [asset for asset in assets if asset.split('-')[0] not in self.blacklisted_assets]

        def get_asset_score(asset_name):
            pair = asset_name.split('-')[0]
            stats = self.asset_performance.get(pair, {'wins': 0, 'losses': 0})
            total_trades = stats['wins'] + stats['losses']
            if total_trades == 0: return 0.5
            return stats['wins'] / total_trades

        prioritized_assets = sorted(available_assets, key=get_asset_score, reverse=True)
        
        asset_names = [a.split('-')[0] for a in prioritized_assets[:5]]
        await self.logger('INFO', f"[M{expiration_minutes}] Ativos Priorizados: {asset_names}")
        
        for asset in prioritized_assets[:settings.MAX_ASSETS_TO_MONITOR]:
            if self.is_trade_active:
                break
            await self._analyze_asset(asset, timeframe_seconds, expiration_minutes)

    async def _analyze_asset(self, full_name: str, timeframe_seconds: int, expiration_minutes: int):
        try:
            if self.is_trade_active: return
            base = full_name.split('-')[0]
            
            if expiration_minutes == 1:
                analysis_candles, sr_candles = await asyncio.gather(
                    self.exnova.get_historical_candles(base, 60, 200),
                    self.exnova.get_historical_candles(base, 900, 100),
                )
                if not analysis_candles or not sr_candles: return
                res, sup = get_m15_sr_zones(sr_candles)
            elif expiration_minutes == 5:
                analysis_candles, sr_candles = await asyncio.gather(
                    self.exnova.get_historical_candles(base, 300, 200),
                    self.exnova.get_historical_candles(base, 3600, 100),
                )
                if not analysis_candles or not sr_candles: return
                res, sup = get_h1_sr_zones(sr_candles)
            else:
                return

            # --- FILTRO 1: VOLATILIDADE (ATR) DINÂMICO ---
            atr_value = ti.calculate_atr(analysis_candles, period=14)
            volatility_profile = self.bot_config.get('volatility_profile', 'EQUILIBRADO')
            
            # ATUALIZADO: Adicionadas todas as opções de volatilidade
            atr_limits = {
                'ULTRA_CONSERVADOR': (0.00015, 0.00500),
                'CONSERVADOR':       (0.00008, 0.01500),
                'EQUILIBRADO':       (0.00005, 0.05000),
                'AGRESSIVO':         (0.00001, 0.15000),
                'ULTRA_AGRESSIVO':   (0.00001, 0.50000),
            }
            # O perfil 'DESATIVADO' não estará no dicionário, então o filtro será pulado
            if volatility_profile != 'DESATIVADO':
                min_atr, max_atr = atr_limits.get(volatility_profile, (0.00005, 0.05000)) # Padrão é EQUILIBRADO
                if atr_value is None or not (min_atr < atr_value < max_atr):
                    await self.logger('DEBUG', f"[{base}-M{expiration_minutes}] Filtro de volatilidade ({volatility_profile}): Fora dos limites (ATR={atr_value}). Ativo ignorado.")
                    return

            signal_candle = analysis_candles[-2]
            
            confluences = {'call': [], 'put': []}
            zones = {'resistance': res, 'support': sup}
            
            if (sr_signal := ti.check_price_near_sr(signal_candle, zones)):
                confluences[sr_signal].append("SR_Zone")
            if (candle_signal := ti.check_candlestick_pattern(analysis_candles)):
                confluences[candle_signal].append("Candle_Pattern")
            if (rsi_signal := ti.check_rsi_condition(analysis_candles)):
                confluences[rsi_signal].append("RSI_Condition")
            
            final_direction = None
            if len(confluences['call']) >= 2: final_direction = 'call'
            elif len(confluences['put']) >= 2: final_direction = 'put'
            
            if final_direction:
                if not ti.validate_reversal_candle(signal_candle, final_direction):
                    return

                if self.is_trade_active: return
                self.is_trade_active = True

                strategy_name = f"M{expiration_minutes}_" + ', '.join(confluences[final_direction])
                await self.logger('SUCCESS', f"SINAL VÁLIDO! Dir: {final_direction.upper()}. Conf: {strategy_name}")
                
                signal = TradeSignal(pair=base, direction=final_direction, strategy=strategy_name,
                                     setup_candle_open=signal_candle.open, setup_candle_high=signal_candle.max,
                                     setup_candle_low=signal_candle.min, setup_candle_close=signal_candle.close)
                
                trade_expiration = 4 if expiration_minutes == 5 else expiration_minutes
                await self._execute_and_wait(signal, full_name, trade_expiration)

        except Exception as e:
            await self.logger('ERROR', f"Erro em _analyze_asset({full_name}, M{expiration_minutes}): {e}")
            traceback.print_exc()

    def _get_entry_value(self, asset: str) -> float:
        base = self.bot_config.get('entry_value', settings.ENTRY_VALUE)
        if not self.bot_config.get('use_martingale', False): return base
        state = self.martingale_state.get(asset, {'level': 0, 'last_value': base})
        if state['level'] == 0: return base
        return round(state['last_value'] * self.bot_config.get('martingale_factor', 2.3), 2)

    async def _execute_and_wait(self, signal: TradeSignal, full_name: str, expiration_minutes: int):
        try:
            bal_before = await self.exnova.get_current_balance()
            entry_value = self._get_entry_value(signal.pair)

            order_id = await self.exnova.execute_trade(entry_value, full_name, signal.direction.lower(), expiration_minutes)
            
            if not order_id:
                await self.logger('ERROR', f"Falha ao executar a ordem para {full_name}. A corretora pode ter rejeitado a entrada.")
                self.is_trade_active = False
                return

            await self.logger('INFO', f"Ordem {order_id} enviada com sucesso. Valor: {entry_value}. Exp: {expiration_minutes} min. Aguardando...")
            sid = await self.supabase.insert_trade_signal(signal)
            if not sid:
                await self.logger('CRITICAL', f"ORDEM {order_id} ABERTA NA CORRETORA MAS FALHOU AO REGISTAR NO SUPABASE!")
            
            await asyncio.sleep(expiration_minutes * 60 + 45)

            bal_after = await self.exnova.get_current_balance()
            
            if bal_before is None or bal_after is None: result = 'UNKNOWN'
            else:
                delta = bal_after - bal_before
                result = 'WIN' if delta > 0 else 'LOSS' if delta < 0 else 'DRAW'
            await self.logger('SUCCESS' if result == 'WIN' else 'ERROR', f"Resultado: {result}. ΔSaldo = {delta:.2f}")

            if sid:
                mg_lv = self.martingale_state.get(signal.pair, {}).get('level', 0)
                await self.supabase.update_trade_result(sid, result, mg_lv)
            
            if bal_after is not None:
                await self.supabase.update_current_balance(bal_after)

            pair = signal.pair
            self.asset_performance.setdefault(pair, {'wins': 0, 'losses': 0})
            self.consecutive_losses.setdefault(pair, 0)

            if result == 'WIN':
                self.daily_wins += 1
                self.asset_performance[pair]['wins'] += 1
                self.consecutive_losses[pair] = 0
                if pair in self.blacklisted_assets:
                    self.blacklisted_assets.remove(pair)
                    await self.logger('INFO', f"O par {pair} foi redimido e REMOVIDO da lista negra.")
            
            elif result == 'LOSS':
                self.daily_losses += 1
                self.asset_performance[pair]['losses'] += 1
                self.consecutive_losses[pair] += 1
                await self.logger('WARNING', f"O par {pair} está com {self.consecutive_losses[pair]} derrota(s) consecutiva(s).")
                
                if self.consecutive_losses[pair] >= 2:
                    self.blacklisted_assets.add(pair)
                    await self.logger('ERROR', f"O par {pair} atingiu 2 derrotas consecutivas e foi COLOCADO na lista negra.")

            stop_win = self.bot_config.get('stop_win', 0)
            stop_loss = self.bot_config.get('stop_loss', 0)

            if stop_win > 0 and self.daily_wins >= stop_win:
                await self.logger('SUCCESS', f"META DE STOP WIN ({stop_win}) ATINGIDA! A pausar o bot.")
                await self.supabase.update_config({'status': 'PAUSED'})
            
            if stop_loss > 0 and self.daily_losses >= stop_loss:
                await self.logger('ERROR', f"META DE STOP LOSS ({stop_loss}) ATINGIDA! A pausar o bot.")
                await self.supabase.update_config({'status': 'PAUSED'})

            if self.bot_config.get('use_martingale', False):
                if result == 'WIN': self.martingale_state[signal.pair] = {'level': 0, 'last_value': entry_value}
                elif result == 'LOSS':
                    lvl = mg_lv + 1
                    max_lv = self.bot_config.get('martingale_levels', 2)
                    if lvl <= max_lv: self.martingale_state[signal.pair] = {'level': lvl, 'last_value': entry_value}
                    else: self.martingale_state[signal.pair] = {'level': 0, 'last_value': self.bot_config.get('entry_value', entry_value)}
        finally:
            self.is_trade_active = False
            await self.logger('INFO', 'Ciclo de operação concluído. Pronto para nova análise.')
