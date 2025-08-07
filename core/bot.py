import sys
import os
import asyncio
import time
import traceback
from datetime import datetime, timedelta
from typing import Dict, Optional, List
from threading import Thread

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings
from services.exnova_service import ExnovaService
from services.supabase_service import SupabaseService
import analysis.technical_indicators as ti
# Importa a classe de modelo de dados
from core.data_models import TradeSignal

class TradingBot:
    def __init__(self):
        self.supabase: Optional[SupabaseService] = None
        self.exnova = ExnovaService(settings.EXNOVA_EMAIL, settings.EXNOVA_PASSWORD)
        self.is_running = True
        self.bot_config: Dict = {}
        self.main_loop = None
        self.currency_char = '$'
        self.current_account_type = ''
        self.previous_status = 'PAUSED'
        self.is_trade_active = False
        self.martingale_state: Dict[str, Dict] = {}
        
        self.strategy_map: Dict[str, callable] = {
            # Estratégias Originais
            'Pullback MQL': ti.strategy_mql_pullback,
            'Padrão de Reversão': ti.strategy_reversal_pattern,
            'Fluxo de Tendência': ti.strategy_trend_flow,
            'Reversão por Exaustão': ti.strategy_exhaustion_reversal,
            'Bandas de Bollinger': ti.strategy_bollinger_bands,
            'Cruzamento MACD': ti.strategy_macd_crossover,
            # Estratégias de Confluência (Nível 1)
            'Tripla Confirmação': ti.strategy_triple_confirmation,
            'Fuga Bollinger + EMA': ti.strategy_bb_ema_filter,
            'MACD + RSI': ti.strategy_macd_rsi_confirm,
            'EMA Cross + Volume': ti.strategy_ema_volume_crossover,
            # Estratégias Profissionais (Nível 2)
            'Reversão Pavio + RSI': ti.strategy_rejection_rsi_wick,
            'Rompimento Falso': ti.strategy_fake_breakout,
            'Inside Bar + RSI': ti.strategy_inside_bar_rsi,
            'Engolfo + Tendência': ti.strategy_engulfing_trend,
            'Compressão Bollinger': ti.strategy_bollinger_squeeze,
        }
        self.asset_strategy_map: Dict[str, str] = {}
        
        self.asset_performance: Dict[str, Dict[str, int]] = {}
        self.consecutive_losses: Dict[str, int] = {}
        self.blacklisted_assets: set = set()
        self.last_reset_time: datetime = datetime.utcnow()
        self.last_analysis_minute = -1
        self.daily_wins = 0
        self.daily_losses = 0
        self.last_daily_reset_date = None

    def logger(self, level: str, message: str):
        ts = datetime.utcnow().isoformat()
        print(f"[{ts}] [{level.upper()}] {message}", flush=True)
        if self.supabase:
            self.supabase.insert_log(level, message)

    def _is_news_time(self) -> bool:
        pause_times = self.bot_config.get('news_pause_times', [])
        if not pause_times: return False
        now_utc = datetime.utcnow()
        for time_str in pause_times:
            try:
                pause_hour, pause_minute = map(int, time_str.split(':'))
                news_time_utc = now_utc.replace(hour=pause_hour, minute=pause_minute, second=0, microsecond=0)
                pause_start = news_time_utc - timedelta(minutes=15)
                pause_end = news_time_utc + timedelta(minutes=15)
                if pause_start <= now_utc <= pause_end:
                    self.logger("WARNING", f"Bot em pausa. Dentro da janela de notícias das {time_str} UTC.")
                    return True
            except ValueError:
                self.logger("ERROR", f"Formato de hora inválido no filtro de notícias: {time_str}")
                continue
        return False
            
    def _soft_restart(self):
        self.logger('WARNING', "--- REINÍCIO SUAVE ATIVADO ---")
        self.daily_wins = 0
        self.daily_losses = 0
        self.logger('INFO', "Placar diário interno zerado.")
        self._daily_reset_if_needed()
        self.asset_strategy_map.clear()
        self.asset_performance.clear()
        self.consecutive_losses.clear()
        self.blacklisted_assets.clear()
        self.is_trade_active = False
        self.martingale_state.clear()
        self.last_reset_time = datetime.utcnow()
        self.logger('INFO', "Estado interno limpo. A iniciar nova catalogação...")
        self._run_cataloging()

    def _run_cataloging(self):
        self.logger('INFO', "--- INICIANDO MODO DE CATALOGAÇÃO DINÂMICA ---")
        self.asset_strategy_map.clear()
        open_assets = self.exnova.get_open_assets()
        if not open_assets:
            self.logger('WARNING', "Nenhum ativo aberto encontrado para catalogar.")
            return

        min_win_rate_threshold = self.bot_config.get('min_win_rate', 55)
        self.logger('INFO', f"A usar taxa de acerto mínima de {min_win_rate_threshold}%.")
        
        cataloged_results = {}

        for asset in open_assets:
            base_name = asset.split('-')[0]
            try:
                historical_candles = self.exnova.get_historical_candles(base_name, 60, 500)
                if not historical_candles or len(historical_candles) < 100:
                    continue
                
                best_strategy_for_asset, highest_win_rate = None, 0
                
                for strategy_name, strategy_func in self.strategy_map.items():
                    wins, losses, total_trades = 0, 0, 0
                    for i in range(50, len(historical_candles) - 1):
                        past_candles, signal_candle, result_candle = historical_candles[:i], historical_candles[i-1], historical_candles[i]
                        signal = strategy_func(past_candles)
                        if signal:
                            total_trades += 1
                            if (signal == 'call' and result_candle['close'] > signal_candle['close']) or \
                               (signal == 'put' and result_candle['close'] < signal_candle['close']):
                                wins += 1
                            else:
                                losses += 1
                    
                    if total_trades > 10:
                        win_rate = (wins / total_trades) * 100
                        if win_rate > highest_win_rate:
                            highest_win_rate, best_strategy_for_asset = win_rate, strategy_name
                
                if best_strategy_for_asset and highest_win_rate >= min_win_rate_threshold:
                    if base_name not in cataloged_results or highest_win_rate > cataloged_results[base_name]['win_rate']:
                        self.asset_strategy_map[base_name] = best_strategy_for_asset
                        self.logger('SUCCESS', f"==> Melhor estratégia para {base_name}: '{best_strategy_for_asset}' ({highest_win_rate:.2f}%)")
                        cataloged_results[base_name] = { "pair": base_name, "best_strategy": best_strategy_for_asset, "win_rate": round(highest_win_rate, 2) }
                else:
                    self.logger('WARNING', f"==> Nenhuma estratégia qualificada para {base_name}.")

            except ValueError as ve:
                if "not found in constants" not in str(ve):
                    self.logger('ERROR', f"Erro de valor ao catalogar {base_name}: {ve}")
            except Exception as e:
                self.logger('ERROR', f"Erro geral ao catalogar {base_name}: {e}")
        
        cataloged_data_to_save = list(cataloged_results.values())
        if cataloged_data_to_save:
            self.logger('INFO', f"A guardar {len(cataloged_data_to_save)} ativos catalogados na base de dados...")
            self.supabase.upsert_cataloged_assets(cataloged_data_to_save)

        self.logger('INFO', "--- CATALOGAÇÃO CONCLUÍDA ---")

    def trading_loop_sync(self):
        self.logger('INFO', 'A iniciar o bot...')
        if not self.exnova.connect(): 
            self.is_running = False
            return

        max_retries = 5
        retry_delay = 10
        for attempt in range(max_retries):
            self.logger('INFO', f"A buscar configuração do bot... (Tentativa {attempt + 1}/{max_retries})")
            config = self.supabase.get_bot_config()
            if config:
                self.bot_config = config
                self.logger('SUCCESS', "Configuração carregada com sucesso!")
                break
            
            self.logger('WARNING', f"Não foi possível obter a configuração. A tentar novamente em {retry_delay} segundos...")
            time.sleep(retry_delay)
        else:
            self.logger('CRITICAL', "NÃO FOI POSSÍVEL CARREGAR A CONFIGURAÇÃO. O BOT NÃO IRÁ INICIAR.")
            self.is_running = False
            return

        profile_data = self.exnova.get_profile()
        if not profile_data: 
            self.is_running = False
            return
            
        try:
            self.currency_char = profile_data.get('currency_char', '$')
            self.logger('SUCCESS', f"Perfil carregado! Olá, {profile_data.get('name', 'Utilizador')}.")
        except Exception as e:
            self.logger('ERROR', f"Erro ao processar perfil: {e}")
            self.is_running = False
            return
        
        self.current_account_type = self.bot_config.get('account_type', 'PRACTICE')
        self.previous_status = self.bot_config.get('status', 'PAUSED')
        self.exnova.change_balance(self.current_account_type)
        self.logger('INFO', f"Conta inicial definida para: {self.current_account_type}")
        
        self._daily_reset_if_needed()
        if self.previous_status == 'RUNNING': 
            self._run_cataloging()

        while self.is_running:
            try:
                if (datetime.utcnow() - self.last_reset_time).total_seconds() >= 7200: 
                    self._hourly_cycle_reset()

                self._daily_reset_if_needed()
                
                new_config = self.supabase.get_bot_config()
                if new_config:
                    self.bot_config = new_config
                
                current_status = self.bot_config.get('status', 'PAUSED')
                if current_status == 'RUNNING' and self.previous_status == 'PAUSED': 
                    self._soft_restart()
                
                self.previous_status = current_status
                
                desired_account_type = self.bot_config.get('account_type', 'PRACTICE')
                if desired_account_type != self.current_account_type:
                    self.logger('WARNING', f"MUDANÇA DE CONTA! De {self.current_account_type} para {desired_account_type}.")
                    self.exnova.change_balance(desired_account_type)
                    self.current_account_type = desired_account_type
                
                if current_status == 'RUNNING':
                    if self._is_news_time():
                        time.sleep(15)
                        continue
                    if not self.is_trade_active:
                        self.trading_cycle()
                else:
                    time.sleep(5)
                time.sleep(1)
            except Exception as e:
                self.logger('ERROR', f"Loop principal falhou: {e}"); traceback.print_exc(); time.sleep(30)

    def trading_cycle(self):
        if self._check_stop_limits():
            return

        now = datetime.utcnow()
        if now.second >= 45 and now.minute != self.last_analysis_minute:
            self.last_analysis_minute = now.minute
            self.logger('INFO', "Janela de análise M1 ATIVADA.")
            self.run_analysis_for_timeframe(60, 1)

    def run_analysis_for_timeframe(self, tf_secs, exp_mins):
        manual_mode = self.bot_config.get('manual_mode_enabled', False)
        
        if manual_mode:
            assets_to_check = self.bot_config.get('manual_pairs', [])
            strategies_to_check = self.bot_config.get('manual_strategies', [])
            if not assets_to_check or not strategies_to_check:
                self.logger("WARNING", "Modo manual ativo, mas nenhum par ou estratégia foi selecionado.")
                return
        else:
            assets_to_check = list(self.asset_strategy_map.keys())
            strategies_to_check = []
            if not assets_to_check: 
                self.logger('INFO', "Nenhum ativo qualificado para análise automática."); return

        all_open_assets = self.exnova.get_open_assets()
        
        prioritized_assets = assets_to_check if manual_mode else sorted(assets_to_check, key=lambda p: (self.asset_performance.get(p,{}).get('wins',0)+1)/(self.asset_performance.get(p,{}).get('wins',0)+self.asset_performance.get(p,{}).get('losses',0)+2), reverse=True)

        for pair in prioritized_assets:
            if self.is_trade_active: break
            full_name = next((a for a in all_open_assets if a.startswith(pair)), None)
            if full_name and pair not in self.blacklisted_assets:
                self._analyze_asset(full_name, tf_secs, exp_mins, strategies_to_check if manual_mode else [])

    def _analyze_asset(self, full_name, tf_secs, exp_mins, manual_strategies: List[str]):
        try:
            base_name = full_name.split('-')[0]
            
            strategies_to_run = manual_strategies or ([self.asset_strategy_map.get(base_name)] if self.asset_strategy_map.get(base_name) else [])
            if not strategies_to_run: return

            self.logger('INFO', f"A analisar {base_name} com as estratégias: {strategies_to_run}...")
            candles = self.exnova.get_historical_candles(base_name, 60, 50)
            if not candles or len(candles) < 20: return

            vol_prof = self.bot_config.get('volatility_profile', 'EQUILIBRADO')
            if vol_prof != 'DESATIVADO':
                limits = {'ULTRA_CONSERVADOR': (0.00001, 0.00015), 'CONSERVADOR': (0.00010, 0.00050), 'EQUILIBRADO': (0.00030, 0.00100), 'AGRESSIVO': (0.00080, 0.00200), 'ULTRA_AGRESSIVO': (0.00150, 999.0)}.get(vol_prof)
                atr = ti.calculate_atr(candles)
                if atr is None or not (limits[0] <= atr <= limits[1]):
                    self.logger('INFO', f"[{base_name}] Análise abortada: Volatilidade fora dos limites."); return
            
            for strat_name in strategies_to_run:
                if self.is_trade_active: break
                strategy_function = self.strategy_map.get(strat_name)
                if not strategy_function: continue

                direction = strategy_function(candles)
                if direction:
                    now = datetime.utcnow()
                    wait = (60 - now.second - 1) + (1 - now.microsecond / 1e6) + 0.2
                    self.logger('SUCCESS', f"SINAL ENCONTRADO! {base_name} | {strat_name} | {direction.upper()}")
                    if wait > 0: time.sleep(wait)
                    
                    signal = TradeSignal(pair=base_name, direction=direction, strategy=strat_name, **candles[-1])
                    self._execute_and_wait(signal, full_name, exp_mins)

        except Exception as e:
            self.logger('ERROR', f"Erro em _analyze_asset({full_name}): {e}")
            traceback.print_exc()

    async def run(self):
        self.supabase = SupabaseService(settings.SUPABASE_URL, settings.SUPABASE_KEY)
        thread = Thread(target=self.trading_loop_sync, daemon=True)
        thread.start()
        while self.is_running and thread.is_alive(): 
            await asyncio.sleep(1)

    def _execute_and_wait(self, signal: TradeSignal, full_name: str, exp_mins: int):
        self.is_trade_active = True
        try:
            is_mg = "Martingale" in signal.strategy
            value = self._get_entry_value(signal.pair, is_mg)
            bal_before = self.exnova.get_current_balance()
            if bal_before is None: return
            
            order_id = self.exnova.execute_trade(value, full_name, signal.direction.lower(), exp_mins)
            if not order_id: 
                self.supabase.insert_trade_signal(signal)
                return
            
            self.logger('INFO', f"Ordem {order_id} enviada. Valor: {self.currency_char}{value:.2f}")
            sid = self.supabase.insert_trade_signal(signal)
            
            time.sleep(exp_mins * 60 + 5)
            bal_after = self.exnova.get_current_balance()
            result = 'UNKNOWN'
            if bal_after is not None:
                profit = round(bal_after - bal_before, 2)
                if profit > 0: result = 'WIN'
                elif profit < 0: result = 'LOSS'
                else: result = 'DRAW'
            
            self.logger('SUCCESS' if result == 'WIN' else 'ERROR', f"Resultado: {result}")
            
            if sid:
                self.supabase.update_trade_result(sid, result, self.martingale_state.get(signal.pair, {}).get('level', 0))
            if bal_after:
                self.supabase.update_current_balance(bal_after)
            
            self._update_stats_and_martingale(result, signal, full_name, exp_mins)
        finally:
            if not self.martingale_state.get(signal.pair, {}).get('is_active', False):
                self.is_trade_active = False

    def _get_entry_value(self, asset, is_mg):
        base = self.bot_config.get('entry_value', 1.0)
        if not self.bot_config.get('use_martingale', False): return base
        level = self.martingale_state.get(asset, {}).get('level', 0)
        if level == 0: return base
        factor = self.bot_config.get('martingale_factor', 2.3)
        return round(base * (factor ** level), 2)

    def _update_stats_and_martingale(self, result, signal, full_name, exp_mins):
        pair = signal.pair
        self.asset_performance.setdefault(pair, {'wins': 0, 'losses': 0})
        self.consecutive_losses.setdefault(pair, 0)
        
        if result == 'WIN':
            self.daily_wins += 1
            self.asset_performance[pair]['wins'] += 1
            self.consecutive_losses[pair] = 0
            self.martingale_state[pair] = {'level': 0, 'is_active': False}
        elif result == 'LOSS':
            self.daily_losses += 1
            self.asset_performance[pair]['losses'] += 1
            self.consecutive_losses[pair] += 1
            if self.consecutive_losses[pair] >= 2:
                self.blacklisted_assets.add(pair)
                self.logger('ERROR', f"Par {pair} na lista negra.")
            
            if self.bot_config.get('use_martingale', False):
                level = self.martingale_state.get(pair, {}).get('level', 0)
                max_levels = self.bot_config.get('martingale_levels', 2)
                if level < max_levels:
                    self.logger('WARNING', f"MARTINGALE NÍVEL {level + 1} ATIVADO IMEDIATAMENTE.")
                    self.martingale_state[pair] = {'level': level + 1, 'is_active': True}
                    
                    candles = self.exnova.get_historical_candles(pair, 60, 1)
                    if not candles:
                        self.logger("ERROR", f"Não foi possível obter a vela para o martingale de {pair}.")
                        self.is_trade_active = False
                        return
                    
                    strat_name = f"{signal.strategy.split('_MG_')[0]}_MG_{level + 1}"
                    mg_signal = TradeSignal(pair=pair, direction=signal.direction, strategy=strat_name, **candles[-1])
                    
                    self.logger('SUCCESS', f"EXECUTANDO MARTINGALE!")
                    self._execute_and_wait(mg_signal, full_name, exp_mins)
                    return
                else:
                    self.logger('ERROR', f"Nível máximo de Martingale atingido.")
                    self.martingale_state[pair] = {'level': 0, 'is_active': False}
        
        self.martingale_state.setdefault(pair, {})['is_active'] = False
        self._check_stop_limits()

    def _check_stop_limits(self) -> bool:
        stop_win = self.bot_config.get('stop_win') or 0
        stop_loss = self.bot_config.get('stop_loss') or 0
        
        limit_hit = False
        message = ""

        if stop_win > 0 and self.daily_wins >= stop_win:
            limit_hit = True
            message = f"META DE STOP WIN ATINGIDA ({self.daily_wins}/{stop_win})!"
        
        if not limit_hit and stop_loss > 0 and self.daily_losses >= stop_loss:
            limit_hit = True
            message = f"META DE STOP LOSS ATINGIDA ({self.daily_losses}/{stop_loss})!"

        if limit_hit:
            if self.bot_config.get('status') == 'RUNNING':
                self.logger('SUCCESS' if 'WIN' in message else 'ERROR', message)
                self.logger('WARNING', "O BOT FOI PAUSADO AUTOMATICAMENTE.")
                self.supabase.update_config({'status': 'PAUSED'})
                self.bot_config['status'] = 'PAUSED'
            return True
        return False

    def _hourly_cycle_reset(self):
        self.logger('INFO', "--- RESET DE CICLO HORÁRIO ---")
        self._soft_restart()

    def _daily_reset_if_needed(self):
        if self.last_daily_reset_date != datetime.utcnow().date():
            self.logger('INFO', f"NOVO DIA DETETADO.")
            self.daily_wins, self.daily_losses = 0, 0
            self.last_daily_reset_date = datetime.utcnow().date()
            bal = self.exnova.get_current_balance()
            if bal:
                self.supabase.update_config({'daily_initial_balance': bal, 'current_balance': bal})
