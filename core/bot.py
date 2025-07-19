import asyncio
import time
import traceback
from datetime import datetime
from typing import Dict, Optional
from threading import Thread

from config import settings
from services.exnova_service import ExnovaService
from services.supabase_service import SupabaseService
from analysis.technical import get_m15_sr_zones, get_h1_sr_zones
from analysis import technical_indicators as ti
from core.data_models import TradeSignal

class TradingBot:
    def __init__(self):
        self.supabase: Optional[SupabaseService] = None
        self.exnova = ExnovaService(settings.EXNOVA_EMAIL, settings.EXNOVA_PASSWORD)
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
        self.last_daily_reset_date = None
        self.pending_martingale_trade: Optional[Dict] = None
        self.main_loop = None

    def _run_async(self, coro):
        if self.main_loop and self.main_loop.is_running():
            return asyncio.run_coroutine_threadsafe(coro, self.main_loop)
        return None

    def logger(self, level: str, message: str):
        ts = datetime.utcnow().isoformat()
        print(f"[{ts}] [{level.upper()}] {message}", flush=True)
        if self.supabase:
            self._run_async(self.supabase.insert_log(level, message))

    def trading_loop_sync(self):
        """
        Coração síncrono do bot, agora imitando a lógica de sucesso do 'botsock.py'.
        """
        self.logger('INFO', 'A iniciar o bot...')
        
        # --- LÓGICA DE LIGAÇÃO CORRIGIDA ---
        # 1. Apenas estabelece a ligação
        if not self.exnova.connect():
            self.logger('ERROR', "Não foi possível ligar ao websocket. A encerrar.")
            self.is_running = False
            return

        # 2. Pede o perfil, tal como no botsock.py
        profile_data = self.exnova.get_profile()
        if not profile_data:
            self.logger('ERROR', "Não foi possível obter os dados do perfil após a ligação. Verifique a sua biblioteca 'exnovaapi'.")
            self.is_running = False
            return

        # 3. Se tudo correu bem, extrai os dados
        try:
            user_name = profile_data.get('name', 'Utilizador')
            currency = profile_data.get('currency_char', '$')
            self.logger('SUCCESS', f"Perfil carregado com sucesso! Olá, {user_name}.")
        except Exception as e:
            self.logger('ERROR', f"O formato dos dados do perfil é inesperado: {profile_data} - Erro: {e}")
            self.is_running = False
            return
        
        # O resto da inicialização continua...
        future = self._run_async(self.supabase.get_bot_config())
        self.bot_config = future.result()
        
        account_type = self.bot_config.get('account_type', 'PRACTICE')
        self.exnova.change_balance(account_type)
        initial_balance = self.exnova.get_current_balance()
        self.logger('INFO', f"Conta definida para: {account_type} | Saldo: {currency}{initial_balance:.2f}")

        self._daily_reset_if_needed()

        while self.is_running:
            try:
                # ... (o resto do seu loop principal permanece o mesmo) ...
                self._daily_reset_if_needed()
                if (datetime.utcnow() - self.last_reset_time).total_seconds() >= 3600:
                    self._hourly_cycle_reset()

                future = self._run_async(self.supabase.get_bot_config())
                self.bot_config = future.result()
                status = self.bot_config.get('status', 'PAUSED')

                if status == 'RUNNING':
                    if self.pending_martingale_trade and not self.is_trade_active:
                        self._execute_martingale_trade()
                    elif not self.is_trade_active:
                        self.trading_cycle()
                
                if status != 'RUNNING':
                    self.logger('INFO', "Bot PAUSADO. Aguardando status 'RUNNING'.")
                elif self.is_trade_active:
                    self.logger('INFO', "Operação em andamento. Aguardando resultado...")
                
                time.sleep(1)

            except Exception as e:
                self.logger('ERROR', f"Loop principal falhou: {e}")
                traceback.print_exc()
                time.sleep(30)

    # --- O resto da classe (run, trading_cycle, etc.) permanece o mesmo ---
    async def run(self):
        self.supabase = SupabaseService(settings.SUPABASE_URL, settings.SUPABASE_KEY)
        self.main_loop = asyncio.get_running_loop()
        trading_thread = Thread(target=self.trading_loop_sync, daemon=True)
        trading_thread.start()
        while self.is_running and trading_thread.is_alive():
            await asyncio.sleep(1)

    def trading_cycle(self):
        now = datetime.utcnow()
        if now.second >= 45:
            if now.minute != self.last_analysis_minute:
                self.last_analysis_minute = now.minute
                self.logger('INFO', "Janela de análise ATIVADA.")
                if (now.minute + 1) % 5 == 0:
                    self.run_analysis_for_timeframe(300, 5)
                else:
                    self.run_analysis_for_timeframe(60, 1)

    def run_analysis_for_timeframe(self, timeframe_seconds: int, expiration_minutes: int):
        assets = self.exnova.get_open_assets()
        if not assets:
            self.logger('WARNING', "Nenhum ativo aberto encontrado.")
            return
        available_assets = [asset for asset in assets if asset.split('-')[0] not in self.blacklisted_assets]
        def get_asset_score(asset_name):
            pair = asset_name.split('-')[0]
            stats = self.asset_performance.get(pair, {'wins': 0, 'losses': 0})
            total_trades = stats['wins'] + stats['losses']
            if total_trades == 0: return 0.5
            return stats['wins'] / total_trades
        prioritized_assets = sorted(available_assets, key=get_asset_score, reverse=True)
        for asset in prioritized_assets[:settings.MAX_ASSETS_TO_MONITOR]:
            if self.is_trade_active:
                break
            self._analyze_asset(asset, timeframe_seconds, expiration_minutes)

    def _analyze_asset(self, full_name: str, timeframe_seconds: int, expiration_minutes: int):
        try:
            if self.is_trade_active: return
            base = full_name.split('-')[0]
            if expiration_minutes == 1:
                analysis_candles = self.exnova.get_historical_candles(base, 60, 200)
                sr_candles = self.exnova.get_historical_candles(base, 900, 100)
                if not analysis_candles or not sr_candles: return
                res, sup = get_m15_sr_zones(sr_candles)
            elif expiration_minutes == 5:
                analysis_candles = self.exnova.get_historical_candles(base, 300, 200)
                sr_candles = self.exnova.get_historical_candles(base, 3600, 100)
                if not analysis_candles or not sr_candles: return
                res, sup = get_h1_sr_zones(sr_candles)
            else: return
            volatility_profile = self.bot_config.get('volatility_profile', 'EQUILIBRADO')
            atr_limits = {'ULTRA_CONSERVADOR': (0.00015, 0.00500), 'CONSERVADOR': (0.00008, 0.01500), 'EQUILIBRADO': (0.00005, 0.05000), 'AGRESSIVO': (0.00001, 0.15000), 'ULTRA_AGRESSIVO': (0.00001, 0.50000)}
            if volatility_profile != 'DESATIVADO':
                min_atr, max_atr = atr_limits.get(volatility_profile, (0.00005, 0.05000))
                atr_value = ti.calculate_atr(analysis_candles, period=14)
                if atr_value is None or not (min_atr < atr_value < max_atr): return
            signal_candle = analysis_candles[-1]
            final_direction = None
            confluences = []
            zones = {'resistance': res, 'support': sup}
            confirmation_threshold = self.bot_config.get('confirmation_threshold') or 2
            if expiration_minutes == 1:
                sr_signal_type = ti.check_price_near_sr(signal_candle, zones)
                if sr_signal_type == 'call':
                    confluences.append("SR_Zone")
                    if ti.check_candlestick_pattern(analysis_candles) == 'call': confluences.append("Candle_Pattern")
                    if ti.check_rsi_condition(analysis_candles) == 'call': confluences.append("RSI_Condition")
                    if len(confluences) >= confirmation_threshold: final_direction = 'call'
                elif sr_signal_type == 'put':
                    confluences.append("SR_Zone")
                    if ti.check_candlestick_pattern(analysis_candles) == 'put': confluences.append("Candle_Pattern")
                    if ti.check_rsi_condition(analysis_candles) == 'put': confluences.append("RSI_Condition")
                    if len(confluences) >= confirmation_threshold: final_direction = 'put'
            elif expiration_minutes == 5:
                m5_signal = ti.check_m5_price_action(analysis_candles, zones)
                if m5_signal:
                    temp_confluences = m5_signal['confluences']
                    if ti.check_rsi_condition(analysis_candles) == m5_signal['direction']:
                        temp_confluences.append("RSI_Condition")
                    if len(temp_confluences) >= confirmation_threshold:
                        final_direction = m5_signal['direction']
                        confluences = temp_confluences
            if final_direction:
                if not ti.validate_reversal_candle(signal_candle, final_direction): return
                if self.is_trade_active: return
                now = datetime.utcnow()
                wait_seconds = (60 - now.second - 1) + (1 - now.microsecond / 1000000) + 0.2
                self.logger('INFO', f"Sinal encontrado em {base}. Aguardando {wait_seconds:.2f}s para entrada precisa.")
                time.sleep(wait_seconds)
                self.is_trade_active = True
                strategy_name = f"M{expiration_minutes}_" + ', '.join(confluences)
                self.logger('SUCCESS', f"EXECUTANDO SINAL! Dir: {final_direction.upper()}. Conf: {strategy_name}")
                signal = TradeSignal(
                    pair=base, 
                    direction=final_direction, 
                    strategy=strategy_name,
                    setup_candle_open=signal_candle['open'], 
                    setup_candle_high=signal_candle['max'],
                    setup_candle_low=signal_candle['min'], 
                    setup_candle_close=signal_candle['close']
                )
                trade_expiration = 4 if expiration_minutes == 5 else expiration_minutes
                self._execute_and_wait(signal, full_name, trade_expiration)
        except Exception as e:
            self.logger('ERROR', f"Erro em _analyze_asset({full_name}, M{expiration_minutes}): {e}")
            traceback.print_exc()

    def _execute_martingale_trade(self):
        trade_info = self.pending_martingale_trade
        if not trade_info: return
        self.pending_martingale_trade = None
        now = datetime.utcnow()
        next_minute_ts = (now.timestamp() // 60 + 1) * 60
        wait_seconds = next_minute_ts - now.timestamp() + 0.2
        current_level = self.martingale_state.get(trade_info['pair'], {}).get('level', 1)
        self.logger('WARNING', f"MARTINGALE NÍVEL {current_level} PREPARADO para {trade_info['pair']}. Aguardando {wait_seconds:.2f}s.")
        time.sleep(wait_seconds)
        self.is_trade_active = True
        strategy_name = f"M{trade_info['expiration_minutes']}_Martingale_{current_level}"
        signal = TradeSignal(
            pair=trade_info['pair'], 
            direction=trade_info['direction'], 
            strategy=strategy_name
        )
        self.logger('SUCCESS', f"EXECUTANDO MARTINGALE! Dir: {signal.direction.upper()}.")
        trade_expiration = 4 if trade_info['expiration_minutes'] == 5 else trade_info['expiration_minutes']
        self._execute_and_wait(signal, trade_info['full_name'], trade_expiration)

    def _get_entry_value(self, asset: str, is_martingale: bool = False) -> float:
        base_value = self.bot_config.get('entry_value', 1.0)
        if not self.bot_config.get('use_martingale', False):
            return base_value
        mg_level = self.martingale_state.get(asset, {}).get('level', 0)
        if not is_martingale and mg_level == 0:
            return base_value
        factor = self.bot_config.get('martingale_factor', 2.3)
        mg_value = base_value * (factor ** mg_level)
        return round(mg_value, 2)

    def _execute_and_wait(self, signal: TradeSignal, full_name: str, expiration_minutes: int):
        try:
            is_martingale_trade = "Martingale" in signal.strategy
            entry_value = self._get_entry_value(signal.pair, is_martingale=is_martingale_trade)

            # 1. Obter saldo ANTES da operação
            balance_before = self.exnova.get_current_balance()
            if balance_before is None:
                self.logger('ERROR', "Não foi possível obter o saldo antes da operação. A cancelar a operação.")
                self.is_trade_active = False
                return

            # 2. Executar a operação
            order_id = self.exnova.execute_trade(entry_value, full_name, signal.direction.lower(), expiration_minutes)
            if not order_id:
                self.logger('ERROR', f"Falha ao executar a ordem para {full_name}.")
                if is_martingale_trade: self.martingale_state[signal.pair] = {'level': 0}
                self.is_trade_active = False
                return

            self.logger('INFO', f"Ordem {order_id} enviada. Valor: {entry_value}. Exp: {expiration_minutes} min. Saldo pré-op: {balance_before:.2f}")
            sid_future = self._run_async(self.supabase.insert_trade_signal(signal))

            # 3. Aguardar o tempo da operação + uma margem de segurança
            wait_time = expiration_minutes * 60 + 5
            self.logger('INFO', f"A aguardar {wait_time} segundos pelo resultado...")
            time.sleep(wait_time)

            # 4. Obter saldo DEPOIS da operação
            balance_after = self.exnova.get_current_balance()
            
            # 5. Determinar o resultado pela diferença de saldo
            if balance_after is None:
                self.logger('ERROR', "Não foi possível obter o saldo após a operação. A marcar como DESCONHECIDO.")
                result = 'UNKNOWN'
            else:
                self.logger('INFO', f"Saldo pós-op: {balance_after:.2f}. A comparar com o saldo anterior: {balance_before:.2f}")
                if balance_after > balance_before:
                    result = 'WIN'
                elif balance_after < balance_before:
                    result = 'LOSS'
                else:
                    result = 'DRAW'
            
            self.logger('SUCCESS' if result == 'WIN' else 'ERROR', f"Resultado da ordem {order_id}: {result}")
            
            # O resto da lógica de contagem e Martingale continua igual
            sid = sid_future.result() if sid_future else None
            if sid:
                mg_lv = self.martingale_state.get(signal.pair, {}).get('level', 0)
                self._run_async(self.supabase.update_trade_result(sid, result, mg_lv))
            
            # Atualiza o saldo no Supabase com o valor final
            if balance_after is not None:
                self._run_async(self.supabase.update_current_balance(balance_after))

            pair = signal.pair
            self.asset_performance.setdefault(pair, {'wins': 0, 'losses': 0})
            self.consecutive_losses.setdefault(pair, 0)
            if result == 'WIN':
                self.daily_wins += 1
                self.asset_performance[pair]['wins'] += 1
                self.consecutive_losses[pair] = 0
                self.martingale_state[pair] = {'level': 0}
                if pair in self.blacklisted_assets:
                    self.blacklisted_assets.remove(pair)
                    self.logger('INFO', f"O par {pair} foi removido da lista negra.")
            elif result == 'LOSS':
                self.daily_losses += 1
                self.asset_performance[pair]['losses'] += 1
                self.consecutive_losses[pair] += 1
                if self.consecutive_losses[pair] >= 2:
                    self.blacklisted_assets.add(pair)
                    self.logger('ERROR', f"O par {pair} foi colocado na lista negra.")
                if self.bot_config.get('use_martingale', False):
                    current_level = self.martingale_state.get(pair, {}).get('level', 0)
                    max_levels = self.bot_config.get('martingale_levels', 2)
                    if current_level < max_levels:
                        self.martingale_state[pair] = {'level': current_level + 1}
                        self.pending_martingale_trade = {
                            "full_name": full_name, "direction": signal.direction,
                            "expiration_minutes": expiration_minutes, "pair": pair
                        }
                        self.logger('WARNING', f"MARTINGALE NÍVEL {current_level + 1} PREPARADO para {pair}.")
                    else:
                        self.martingale_state[pair] = {'level': 0}
                        self.logger('ERROR', f"Nível máximo de Martingale atingido para {pair}.")
            stop_win = self.bot_config.get('stop_win') or 0
            stop_loss = self.bot_config.get('stop_loss') or 0
            if (stop_win > 0 and self.daily_wins >= stop_win) or \
               (stop_loss > 0 and self.daily_losses >= stop_loss):
                msg = f"META DE STOP WIN ATINGIDA!" if self.daily_wins >= stop_win else f"META DE STOP LOSS ATINGIDA!"
                self.logger('SUCCESS' if result == 'WIN' else 'ERROR', f"{msg} A pausar o bot.")
                self._run_async(self.supabase.update_config({'status': 'PAUSED'}))
        finally:
            if not self.pending_martingale_trade:
                self.is_trade_active = False
                self.logger('INFO', 'Ciclo de operação concluído.')

    def _hourly_cycle_reset(self):
        self.logger('INFO', "CICLO HORÁRIO CONCLUÍDO. A zerar performance de ativos e lista negra.")
        self.asset_performance.clear()
        self.consecutive_losses.clear()
        self.blacklisted_assets.clear()
        self.last_reset_time = datetime.utcnow()
        self.logger('SUCCESS', "Estatísticas de ativos zeradas.")
        
    def _daily_reset_if_needed(self):
        current_date_utc = datetime.utcnow().date()
        if self.last_daily_reset_date != current_date_utc:
            self.logger('INFO', f"NOVO DIA DETETADO ({current_date_utc}). A zerar metas de Stop Win/Loss e saldo diário.")
            self.daily_wins = 0
            self.daily_losses = 0
            self.last_daily_reset_date = current_date_utc
            
            bal = self.exnova.get_current_balance()
            if bal is not None and self.supabase:
                self._run_async(self.supabase.update_config({'daily_initial_balance': bal, 'current_balance': bal}))

