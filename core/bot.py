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
            'Pullback MQL': ti.strategy_mql_pullback,
            'Padrão de Reversão': ti.strategy_reversal_pattern,
            'Fluxo de Tendência': ti.strategy_trend_flow,
            'Reversão por Exaustão': ti.strategy_exhaustion_reversal,
            'Bandas de Bollinger': ti.strategy_bollinger_bands,
            'Cruzamento MACD': ti.strategy_macd_crossover,
            'Tripla Confirmação': ti.strategy_triple_confirmation,
            'Fuga Bollinger + EMA': ti.strategy_bb_ema_filter,
            'MACD + RSI': ti.strategy_macd_rsi_confirm,
            'Rejeição RSI + Pavio': ti.strategy_rejection_rsi_wick,
            'EMA Cross + Volume': ti.strategy_ema_volume_crossover,
            'Rompimento Falso': ti.strategy_fake_breakout,
            'Inside Bar + RSI': ti.strategy_inside_bar_rsi,
            'Engolfo + Tendência': ti.strategy_engulfing_trend,
            'Compressão Bollinger': ti.strategy_bollinger_squeeze,
            'Scalping StochRSI': ti.strategy_stochrsi_scalp,
            'Pires Awesome': ti.strategy_awesome_saucer,
            'Reversão Keltner': ti.strategy_keltner_reversion,
            'Tendência Heikin-Ashi': ti.strategy_heikinashi_trend,
            'Cruzamento Vortex': ti.strategy_vortex_cross,
            'Reversão de Fractal': ti.strategy_fractal_reversal,
            'Bollinger + Fractal + Stoch': ti.strategy_bollinger_fractal_stoch,
        }
        
        self.last_analysis_minute = -1
        self.daily_wins = 0
        self.daily_losses = 0
        self.last_daily_reset_date = None

    def logger(self, level: str, message: str):
        ts = datetime.utcnow().isoformat()
        print(f"[{ts}] [{level.upper()}] {message}", flush=True)
        if self.supabase:
            self.supabase.insert_log(level, message)

    def _soft_restart(self):
        self.logger('WARNING', "--- REINÍCIO SUAVE ATIVADO ---")
        self.daily_wins = 0
        self.daily_losses = 0
        self.logger('INFO', "Placar diário interno zerado.")
        self._daily_reset_if_needed()
        self.is_trade_active = False
        self.martingale_state.clear()
        self.logger('INFO', "Estado interno limpo. O bot está pronto para operar.")

    def trading_loop_sync(self):
        self.logger('INFO', 'A iniciar o bot...')
        check, reason = self.exnova.connect()
        if not check:
            self.logger('CRITICAL', f"Falha ao conectar na Exnova: {reason}. O bot será encerrado.")
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
        self.logger('SUCCESS', f"Perfil carregado! Olá, {profile_data.get('name', 'Utilizador')}.")
        
        self.current_account_type = self.bot_config.get('account_type', 'PRACTICE')
        self.previous_status = self.bot_config.get('status', 'PAUSED')
        self.exnova.change_balance(self.current_account_type)
        
        self._daily_reset_if_needed()

        while self.is_running:
            try:
                self._daily_reset_if_needed()
                
                new_config = self.supabase.get_bot_config()
                if new_config: self.bot_config = new_config
                
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
                    if not self.is_trade_active:
                        self.trading_cycle()
                else:
                    time.sleep(5)
                time.sleep(1)
            except Exception as e:
                self.logger('ERROR', f"Loop principal falhou: {e}")
                traceback.print_exc()
                self.exnova.reconnect()

    def trading_cycle(self):
        if self._check_stop_limits():
            return

        now = datetime.utcnow()
        if now.second >= 45 and now.minute != self.last_analysis_minute:
            self.last_analysis_minute = now.minute
            self.logger('INFO', "Janela de análise M1 ATIVADA.")
            self.run_analysis_for_timeframe(60, 1)
    
    # FUNÇÃO ATUALIZADA E MAIS ROBUSTA
    def _get_automatic_pairs(self, min_payout):
        """
        Busca os pares abertos com o melhor payout de forma mais direta.
        """
        try:
            best_pairs = {}
            # Usamos get_all_init_v2() que é mais moderno e completo
            init_data = self.exnova.api.get_all_init_v2()

            if not init_data:
                self.logger('WARNING', "Não foi possível obter os dados de inicialização da corretora.")
                return []

            # Itera sobre os tipos de opção (binárias e turbo)
            for option_type in ['binary', 'turbo']:
                if option_type in init_data:
                    for asset_id, asset_details in init_data[option_type]['actives'].items():
                        asset_name = asset_details.get('name', '').split('.')[-1]
                        
                        is_enabled = asset_details.get('enabled', False)
                        is_suspended = asset_details.get('is_suspended', False)
                        
                        if is_enabled and not is_suspended:
                            commission = asset_details.get('option', {}).get('profit', {}).get('commission', 100)
                            payout = (100 - commission) / 100.0
                            
                            if payout >= min_payout:
                                # Armazena o melhor payout para cada par
                                if asset_name not in best_pairs or payout > best_pairs[asset_name]:
                                    best_pairs[asset_name] = payout
                        # else:
                        #     self.logger('DEBUG', f"Par {asset_name} ignorado (Fechado ou Suspenso).")

            if not best_pairs:
                self.logger('INFO', "Nenhum par aberto cumpre o requisito de payout mínimo no momento.")
                return []
            
            # Ordena os pares pelo maior payout
            sorted_pairs = sorted(best_pairs.items(), key=lambda item: item[1], reverse=True)
            
            return [pair[0] for pair in sorted_pairs]

        except Exception as e:
            self.logger('ERROR', f"Erro ao buscar pares automaticamente: {e}")
            traceback.print_exc()
            return []

    def run_analysis_for_timeframe(self, tf_secs, exp_mins):
        pair_mode = self.bot_config.get('pair_management_mode', 'MANUAL')
        strategy_mode = self.bot_config.get('strategy_management_mode', 'MANUAL')
        
        assets_to_check = []
        if pair_mode == 'AUTOMATIC':
            min_payout = self.bot_config.get('min_payout', 80) / 100.0
            self.logger('INFO', f"Modo Automático: Buscando pares com payout mínimo de {min_payout*100:.0f}%.")
            assets_to_check = self._get_automatic_pairs(min_payout)
            if assets_to_check:
                self.logger('INFO', f"Pares encontrados que cumprem os critérios: {assets_to_check}")
        else:  # MANUAL
            assets_to_check = self.bot_config.get('manual_pairs', [])

        strategies_to_check = []
        if strategy_mode == 'AUTOMATIC':
            strategies_to_check = list(self.strategy_map.keys())
            self.logger('INFO', "Modo Automático: Usando todas as estratégias.")
        else:  # MANUAL
            strategies_to_check = self.bot_config.get('manual_strategies', [])

        if not assets_to_check or not strategies_to_check:
            self.logger("INFO", "Nenhum par ou estratégia disponível para análise. A aguardar...")
            return

        for pair in assets_to_check:
            if self.is_trade_active: break
            self._analyze_asset(pair, tf_secs, exp_mins, strategies_to_check)


    def _analyze_asset(self, pair_name, tf_secs, exp_mins, strategies_to_run: List[str]):
        try:
            self.logger('INFO', f"A analisar {pair_name}...")
            candles = self.exnova.get_historical_candles(pair_name, 60, 50)
            if not candles: return
            
            for strat_name in strategies_to_run:
                if self.is_trade_active: break
                strategy_function = self.strategy_map.get(strat_name)
                if not strategy_function: continue

                direction = strategy_function(candles)
                if direction:
                    now = datetime.utcnow()
                    wait = (60 - now.second - 1) + (1 - now.microsecond / 1e6) + 0.2
                    self.logger('SUCCESS', f"SINAL ENCONTRADO! {pair_name} | {strat_name} | {direction.upper()}")
                    if wait > 0: time.sleep(wait)
                    
                    signal = TradeSignal(pair=pair_name, direction=direction, strategy=strat_name, **candles[-1])
                    self._execute_and_wait(signal, pair_name, exp_mins)

        except Exception as e:
            self.logger('ERROR', f"Erro em _analyze_asset({pair_name}): {e}")
            traceback.print_exc()

    async def run(self):
        self.supabase = SupabaseService(settings.SUPABASE_URL, settings.SUPABASE_KEY)
        thread = Thread(target=self.trading_loop_sync, daemon=True)
        thread.start()
        try:
            while self.is_running and thread.is_alive(): 
                await asyncio.sleep(1)
        finally:
            self.logger("INFO", "A encerrar o bot...")
            self.exnova.quit()

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
            
            sid = self.supabase.insert_trade_signal(signal)
            
            time.sleep(exp_mins * 60 + 5)
            bal_after = self.exnova.get_current_balance()
            result = 'UNKNOWN'
            profit = 0
            if bal_after is not None:
                profit = round(bal_after - bal_before, 2)
                if profit > 0: result = 'WIN'
                elif profit < 0: result = 'LOSS'
                else: result = 'DRAW'
            
            self.logger('SUCCESS' if result == 'WIN' else 'ERROR', f"Resultado: {result} | Lucro: {profit}")
            
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
        
        if result == 'WIN':
            self.daily_wins += 1
            self.martingale_state[pair] = {'level': 0, 'is_active': False}
        elif result == 'LOSS':
            self.daily_losses += 1
            if self.bot_config.get('use_martingale', False):
                level = self.martingale_state.get(pair, {}).get('level', 0)
                max_levels = self.bot_config.get('martingale_levels', 2)
                if level < max_levels:
                    self.martingale_state[pair] = {'level': level + 1, 'is_active': True}
                    
                    mg_value = self._get_entry_value(pair, True)
                    current_balance = self.exnova.get_current_balance()
                    if current_balance is not None and mg_value > current_balance:
                        self.logger('ERROR', f"MARTINGALE CANCELADO: Saldo insuficiente.")
                        self.martingale_state[pair] = {'level': 0, 'is_active': False}
                        return

                    candles = self.exnova.get_historical_candles(pair, 60, 1)
                    if not candles:
                        self.is_trade_active = False
                        return
                    
                    strat_name = f"{signal.strategy.split('_MG_')[0]}_MG_{level + 1}"
                    mg_signal = TradeSignal(pair=pair, direction=signal.direction, strategy=strat_name, **candles[-1])
                    
                    self.logger('SUCCESS', f"EXECUTANDO MARTINGALE NÍVEL {level + 1}!")
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

    def _daily_reset_if_needed(self):
        if self.last_daily_reset_date != datetime.utcnow().date():
            self.logger('INFO', f"NOVO DIA DETETADO.")
            self.daily_wins, self.daily_losses = 0, 0
            self.last_daily_reset_date = datetime.utcnow().date()
            bal = self.exnova.get_current_balance()
            if bal:
                self.supabase.update_config({'daily_initial_balance': bal, 'current_balance': bal})
