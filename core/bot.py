import sys
import os
import asyncio
import time
import traceback
from datetime import datetime
from typing import Dict, Optional, List
from threading import Thread

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings
from services.exnova_service import ExnovaService
from services.supabase_service import SupabaseService
import analysis.technical_indicators as ti
from analysis.cataloger import backtest_strategy
from core.data_models import TradeSignal

class TradingBot:
    def __init__(self):
        self.supabase: Optional[SupabaseService] = None
        self.exnova: Optional[ExnovaService] = None
        self.is_running = True
        self.bot_config: Dict = {}
        self.strategy_map: Dict[str, callable] = {
            'Pullback MQL': ti.strategy_mql_pullback, 'Padrão de Reversão': ti.strategy_reversal_pattern, 'Fluxo de Tendência': ti.strategy_trend_flow,
            'Reversão por Exaustão': ti.strategy_exhaustion_reversal, 'Bandas de Bollinger': ti.strategy_bollinger_bands, 'Cruzamento MACD': ti.strategy_macd_crossover,
            'Tripla Confirmação': ti.strategy_triple_confirmation, 'Fuga Bollinger + EMA': ti.strategy_bb_ema_filter, 'MACD + RSI': ti.strategy_macd_rsi_confirm,
            'Rejeição RSI + Pavio': ti.strategy_rejection_rsi_wick, 'EMA Cross + Volume': ti.strategy_ema_volume_crossover, 'Rompimento Falso': ti.strategy_fake_breakout,
            'Inside Bar + RSI': ti.strategy_inside_bar_rsi, 'Engolfo + Tendência': ti.strategy_engulfing_trend, 'Compressão Bollinger': ti.strategy_bollinger_squeeze,
            'Scalping StochRSI': ti.strategy_stochrsi_scalp, 'Pires Awesome': ti.strategy_awesome_saucer, 'Reversão Keltner': ti.strategy_keltner_reversion,
            'Tendência Heikin-Ashi': ti.strategy_heikinashi_trend, 'Cruzamento Vortex': ti.strategy_vortex_cross, 'Reversão de Fractal': ti.strategy_fractal_reversal,
            'Bollinger + Fractal + Stoch': ti.strategy_bollinger_fractal_stoch,
        }
        self.last_analysis_minute = -1
        self.daily_wins = 0
        self.daily_losses = 0
        self.last_daily_reset_date = None
        self.is_trade_active = False
        self.previous_status = 'PAUSED'
        self.martingale_state: Dict[str, Dict] = {}

    def logger(self, level: str, message: str):
        ts = datetime.utcnow().isoformat()
        print(f"[{ts}] [{level.upper()}] {message}", flush=True)
        if self.supabase: self.supabase.insert_log(level, message)

    def _soft_restart(self):
        self.logger('WARNING', "--- REINÍCIO SUAVE ATIVADO ---")
        self.daily_wins = 0
        self.daily_losses = 0
        self.is_trade_active = False
        self.martingale_state.clear()
        self._daily_reset_if_needed()
        self.logger('INFO', "Estado interno limpo. O bot está pronto para operar.")

    def run_cataloging_cycle(self, exnova_instance: ExnovaService):
        try:
            self.logger('INFO', "[CATALOGER] A iniciar novo ciclo de catalogação...")
            all_open_assets = exnova_instance.get_all_open_assets()
            self.logger('INFO', f"[CATALOGER] {len(all_open_assets)} pares abertos encontrados para análise.")

            for asset in all_open_assets:
                if not self.is_running: break
                candles = exnova_instance.get_historical_candles(asset, 60, 200)
                if not candles or len(candles) < 100: continue

                best_strategy, highest_win_rate, best_stats = None, 0, {'wins': 0, 'losses': 0}
                for strat_name, strat_func in self.strategy_map.items():
                    wins, losses, _ = backtest_strategy(candles, strat_func)
                    total_ops = wins + losses
                    if total_ops > 5:
                        win_rate = (wins / total_ops) * 100
                        # --- NOVO LOG DETALHADO ---
                        self.logger('INFO', f"[CATALOGER] -> {asset}: {strat_name} -> {win_rate:.1f}% ({wins}W/{losses}L)")
                        if win_rate > highest_win_rate:
                            highest_win_rate, best_strategy, best_stats = win_rate, strat_name, {'wins': wins, 'losses': losses}
                
                if best_strategy:
                    self.logger('SUCCESS', f"[CATALOGER] Melhor estratégia para {asset}: {best_strategy} com {highest_win_rate:.1f}%")
                    self.supabase.upsert_cataloged_asset({'pair': asset, 'win_rate': highest_win_rate, 'best_strategy': best_strategy, 'wins': best_stats['wins'], 'losses': best_stats['losses']})
            self.logger('SUCCESS', "[CATALOGER] Ciclo de catalogação concluído.")
        except Exception as e:
            self.logger('ERROR', f"[CATALOGER] Erro no ciclo de catalogação: {e}")
            traceback.print_exc()

    def cataloging_loop_sync(self):
        self.logger('INFO', "Thread de catalogação periódica iniciada.")
        catalog_exnova = ExnovaService(settings.EXNOVA_EMAIL, settings.EXNOVA_PASSWORD)
        while self.is_running:
            time.sleep(15 * 60)
            if self.is_running:
                self.run_cataloging_cycle(catalog_exnova)
        catalog_exnova.quit()

    def trading_loop_sync(self):
        self.logger('INFO', 'A iniciar o bot...')
        self.exnova = ExnovaService(settings.EXNOVA_EMAIL, settings.EXNOVA_PASSWORD)
        check, reason = self.exnova.connect()
        if not check: self.logger('CRITICAL', f"Falha ao conectar: {reason}."); return
        
        self.bot_config = self.supabase.get_bot_config()
        if not self.bot_config: self.logger('CRITICAL', "NÃO FOI POSSÍVEL CARREGAR A CONFIGURAÇÃO."); return
        self.logger('SUCCESS', "Configuração carregada com sucesso!")
        self.exnova.change_balance(self.bot_config.get('account_type', 'PRACTICE'))

        while self.is_running:
            try:
                new_config = self.supabase.get_bot_config()
                if new_config: self.bot_config = new_config
                current_status = self.bot_config.get('status', 'PAUSED')
                if current_status == 'RUNNING' and self.previous_status == 'PAUSED': self._soft_restart()
                self.previous_status = current_status
                if current_status == 'RUNNING':
                    if not self.is_trade_active: self.trading_cycle()
                else: time.sleep(5)
                time.sleep(1)
            except Exception as e: self.logger('ERROR', f"Loop principal falhou: {e}"); traceback.print_exc()

    def trading_cycle(self):
        if self.bot_config.get('status') != 'RUNNING' or self._check_stop_limits(): return
        now = datetime.utcnow()
        if now.second >= 58 and now.minute != self.last_analysis_minute:
            self.last_analysis_minute = now.minute
            self.logger('INFO', "Janela de análise M1 ATIVADA.")
            self.run_analysis_for_timeframe(60, 1)

    def run_analysis_for_timeframe(self, tf_secs, exp_mins):
        min_win_rate = self.bot_config.get('min_win_rate', 70)
        self.logger('INFO', f"A procurar sinais com assertividade mínima de {min_win_rate}%.")

        cataloged_assets = self.supabase.get_cataloged_assets(min_win_rate)
        if not cataloged_assets:
            self.logger('INFO', "Nenhum par catalogado cumpre os critérios de assertividade.")
            return

        self.logger('INFO', f"Pares qualificados: {[asset['pair'] for asset in cataloged_assets]}")
        for asset in cataloged_assets:
            if self.bot_config.get('status') != 'RUNNING' or self._check_stop_limits(): break
            if self.is_trade_active: break
            self._analyze_asset(asset['pair'], tf_secs, exp_mins, asset['best_strategy'])

    def _analyze_asset(self, pair_name, tf_secs, exp_mins, best_strategy_name):
        try:
            self.logger('INFO', f"A analisar {pair_name} com sua melhor estratégia: {best_strategy_name}...")
            candles = self.exnova.get_historical_candles(pair_name, 60, 50)
            if not candles: return

            strategy_function = self.strategy_map.get(best_strategy_name)
            if not strategy_function: return

            direction = strategy_function(candles)
            if direction:
                self.logger('SUCCESS', f"SINAL ENCONTRADO! {pair_name} | {best_strategy_name} | {direction.upper()}")
                signal = TradeSignal(pair=pair_name, direction=direction, strategy=best_strategy_name, **candles[-1])
                
                sid = self.supabase.insert_trade_signal(signal.to_dict())
                if not sid:
                    self.logger('ERROR', "Falha ao registar sinal PENDENTE na base de dados.")
                    return

                time.sleep(max(0, 60 - datetime.utcnow().second))
                self._execute_and_wait(signal, pair_name, exp_mins, sid)
        except Exception as e: self.logger('ERROR', f"Erro em _analyze_asset({pair_name}): {e}"); traceback.print_exc()

    async def run(self):
        self.supabase = SupabaseService(settings.SUPABASE_URL, settings.SUPABASE_KEY)
        
        self.logger('INFO', "A realizar a catalogação inicial. O bot iniciará em breve. Este processo pode demorar alguns minutos...")
        try:
            initial_catalog_exnova = ExnovaService(settings.EXNOVA_EMAIL, settings.EXNOVA_PASSWORD)
            self.run_cataloging_cycle(initial_catalog_exnova)
            initial_catalog_exnova.quit()
            self.logger('SUCCESS', "Catalogação inicial concluída.")
        except Exception as e:
            self.logger('ERROR', f"Falha na catalogação inicial: {e}")

        trading_thread = Thread(target=self.trading_loop_sync, daemon=True)
        cataloging_thread = Thread(target=self.cataloging_loop_sync, daemon=True)
        trading_thread.start()
        cataloging_thread.start()
        try:
            while self.is_running: await asyncio.sleep(1)
        finally:
            self.is_running = False
            self.logger("INFO", "A encerrar o bot...")
            if self.exnova: self.exnova.quit()

    def _execute_and_wait(self, signal: TradeSignal, full_name: str, exp_mins: int, sid: int):
        self.is_trade_active = True
        try:
            value = self._get_entry_value(signal.pair)
            bal_before = self.exnova.get_current_balance()
            if bal_before is None: return
            
            order_id = self.exnova.execute_trade(value, full_name, signal.direction.lower(), exp_mins)
            if not order_id: 
                self.supabase.update_trade_result(sid, 'ERROR', 0)
                return
            
            expiration_timestamp = time.time() + exp_mins * 60
            result = 'UNKNOWN'
            
            while time.time() < expiration_timestamp + 15:
                bal_after = self.exnova.get_current_balance()
                if bal_after is not None and bal_after != bal_before:
                    profit = round(bal_after - bal_before, 2)
                    result = 'WIN' if profit > 0 else 'LOSS' if profit < 0 else 'DRAW'
                    break
                time.sleep(2)

            self.logger('SUCCESS' if result == 'WIN' else 'ERROR', f"Resultado: {result}")
            
            self.supabase.update_trade_result(sid, result, self.martingale_state.get(signal.pair, {}).get('level', 0))
            if self.exnova.get_current_balance(): self.supabase.update_current_balance(self.exnova.get_current_balance())
            
            self._update_stats_and_martingale(result, signal, full_name, exp_mins)
        finally:
            if not self.martingale_state.get(signal.pair, {}).get('is_active', False): self.is_trade_active = False

    def _get_entry_value(self, asset):
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
                max_levels = self.bot_config.get('martingale_levels', 1)
                if level < max_levels:
                    self.martingale_state[pair] = {'level': level + 1, 'is_active': True}
                    self.logger('SUCCESS', f"EXECUTANDO MARTINGALE NÍVEL {level + 1}!")
                    new_sid = self.supabase.insert_trade_signal(signal.to_dict())
                    if new_sid: self._execute_and_wait(signal, full_name, exp_mins, new_sid)
                    return
                else:
                    self.logger('ERROR', f"Nível máximo de Martingale atingido.")
                    self.martingale_state[pair] = {'level': 0, 'is_active': False}
        
        self.martingale_state.setdefault(pair, {})['is_active'] = False
        self._check_stop_limits()

    def _check_stop_limits(self) -> bool:
        stop_mode = self.bot_config.get('stop_mode', 'VALUE')
        limit_hit = False
        message = ""

        if stop_mode == 'PERCENT':
            stop_win_percent = self.bot_config.get('stop_win_percent', 0)
            stop_loss_percent = self.bot_config.get('stop_loss_percent', 0)
            initial_balance = self.bot_config.get('daily_initial_balance', 0)
            current_balance = self.exnova.get_current_balance()

            if initial_balance > 0 and current_balance is not None:
                profit = current_balance - initial_balance
                if stop_win_percent > 0:
                    target_profit = initial_balance * (stop_win_percent / 100.0)
                    if profit >= target_profit:
                        limit_hit = True; message = f"META DE STOP WIN ATINGIDA ({profit:.2f} >= {target_profit:.2f})!"
                if not limit_hit and stop_loss_percent > 0:
                    max_loss = initial_balance * (stop_loss_percent / 100.0)
                    if profit <= -max_loss:
                        limit_hit = True; message = f"META DE STOP LOSS ATINGIDA ({profit:.2f} <= {-max_loss:.2f})!"
        else:
            stop_win = self.bot_config.get('stop_win', 0)
            stop_loss = self.bot_config.get('stop_loss', 0)
            if stop_win > 0 and self.daily_wins >= stop_win:
                limit_hit = True; message = f"META DE STOP WIN ATINGIDA ({self.daily_wins}/{stop_win})!"
            if not limit_hit and stop_loss > 0 and self.daily_losses >= stop_loss:
                limit_hit = True; message = f"META DE STOP LOSS ATINGIDA ({self.daily_losses}/{stop_loss})!"

        if limit_hit:
            if self.bot_config.get('status') == 'RUNNING':
                self.logger('SUCCESS' if 'WIN' in message else 'ERROR', message)
                self.logger('WARNING', "O BOT FOI PAUSADO AUTOMATICAMENTE.")
                self.supabase.update_config({'status': 'PAUSED'})
                self.bot_config['status'] = 'PAUSED'
            return True
        return False

    def _daily_reset_if_needed(self):
        now_utc = datetime.utcnow().date()
        if self.last_daily_reset_date != now_utc:
            self.logger('INFO', f"NOVO DIA DETETADO ({now_utc}).")
            self.last_daily_reset_date = now_utc
            bal = self.exnova.get_current_balance()
            if bal: self.supabase.update_config({'daily_initial_balance': bal, 'current_balance': bal})
