import sys
import os
import asyncio
import time
import traceback
from datetime import datetime
from threading import Thread, Lock
import logging

# Adiciona o diretório pai ao sys.path para importações relativas
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings
from services.exnova_service import ExnovaService
from services.supabase_service import SupabaseService
import analysis.technical_indicators as ti
from core.data_models import TradeSignal
from analysis.cataloger import Cataloger

class TradingBot:
    def __init__(self):
        # --- Serviços ---
        self.supabase: SupabaseService | None = None
        self.exnova_operator: ExnovaService | None = None
        self.exnova_cataloger: ExnovaService | None = None
        
        # --- Configurações e Estado ---
        self.bot_config: dict = {}
        self.is_running = True
        self.is_trade_active = False
        self.trade_lock = Lock()
        self.last_analysis_minute = -1
        self.martingale_state: dict = {}
        
        # --- Contadores Diários ---
        self.daily_wins = 0
        self.daily_losses = 0
        self.last_daily_reset_date = None
        
        # --- Mapeamento de Estratégias ---
        self.strategy_map = {
            'Pullback MQL': ti.strategy_mql_pullback, 'Padrão de Reversão': ti.strategy_reversal_pattern,
            'Fluxo de Tendência': ti.strategy_trend_flow, 'Reversão por Exaustão': ti.strategy_exhaustion_reversal,
            'Bandas de Bollinger': ti.strategy_bollinger_bands, 'Cruzamento MACD': ti.strategy_macd_crossover,
            'Tripla Confirmação': ti.strategy_triple_confirmation, 'Fuga Bollinger + EMA': ti.strategy_bb_ema_filter,
            'MACD + RSI': ti.strategy_macd_rsi_confirm, 'Rejeição RSI + Pavio': ti.strategy_rejection_rsi_wick,
            'EMA Cross + Volume': ti.strategy_ema_volume_crossover, 'Rompimento Falso': ti.strategy_fake_breakout,
            'Inside Bar + RSI': ti.strategy_inside_bar_rsi, 'Engolfo + Tendência': ti.strategy_engulfing_trend,
            'Compressão Bollinger': ti.strategy_bollinger_squeeze, 'Scalping StochRSI': ti.strategy_stochrsi_scalp,
            'Pires Awesome': ti.strategy_awesome_saucer, 'Reversão Keltner': ti.strategy_keltner_reversion,
            'Tendência Heikin-Ashi': ti.strategy_heikinashi_trend, 'Cruzamento Vortex': ti.strategy_vortex_cross,
            'Reversão de Fractal': ti.strategy_fractal_reversal, 'Bollinger + Fractal + Stoch': ti.strategy_bollinger_fractal_stoch,
        }

    def logger(self, level: str, message: str, service: str = "BOT"):
        log_message = f"[{service}] {message}"
        print(f"[{datetime.utcnow().isoformat()}] [{level.upper()}] {log_message}", flush=True)
        if self.supabase:
            self.supabase.insert_log(level, log_message)

    # --- LÓGICA DE CATALOGAÇÃO ---
    def _perform_initial_cataloging(self):
        self.logger('INFO', "A realizar a catalogação inicial. O bot iniciará em breve. Este processo pode demorar alguns minutos...")
        temp_exnova_service = None
        try:
            temp_exnova_service = ExnovaService(settings.EXNOVA_EMAIL, settings.EXNOVA_PASSWORD)
            check, reason = temp_exnova_service.connect()
            if not check:
                self.logger('ERROR', f"Falha ao conectar para catalogação inicial: {reason}")
                return

            cataloger = Cataloger(temp_exnova_service, self.supabase, self.strategy_map)
            cataloger.run_cataloging_cycle()
            self.logger('SUCCESS', "Catalogação inicial concluída.")
        except Exception as e:
            self.logger('ERROR', f"Erro crítico na catalogação inicial: {e}")
            traceback.print_exc()
        finally:
            if temp_exnova_service:
                temp_exnova_service.close()
                self.logger('INFO', "Conexão temporária de catalogação fechada.")

    def cataloging_loop_sync(self):
        self.logger('INFO', "Thread de catalogação periódica iniciada.")
        while self.is_running:
            try:
                if self.exnova_cataloger and self.exnova_cataloger.is_connected():
                    cataloger = Cataloger(self.exnova_cataloger, self.supabase, self.strategy_map)
                    cataloger.run_cataloging_cycle()
                else:
                    self.logger('WARNING', "Serviço de catalogação não está conectado, a pular ciclo.", "CATALOGER")
            except Exception as e:
                self.logger('ERROR', f"Erro no loop de catalogação periódica: {e}", "CATALOGER")
                traceback.print_exc()
                # Tenta reconectar se a conexão falhar
                if self.exnova_cataloger:
                    self.logger('INFO', "A tentar reconectar o serviço de catalogação...", "CATALOGER")
                    self.exnova_cataloger.connect()
            
            time.sleep(15 * 60) # Espera 15 minutos para o próximo ciclo

    # --- LÓGICA PRINCIPAL DE OPERAÇÃO ---
    def trading_loop_sync(self):
        previous_status = 'PAUSED'
        
        while self.is_running:
            try:
                # Carrega a configuração mais recente
                new_config = self.supabase.get_bot_config()
                if new_config: self.bot_config = new_config
                else: self.logger('WARNING', "Não foi possível carregar a configuração. Usando a última versão em memória."); time.sleep(10); continue

                current_status = self.bot_config.get('status', 'PAUSED')

                # Lógica de Reinício Suave ao mudar de PAUSED para RUNNING
                if current_status == 'RUNNING' and previous_status == 'PAUSED':
                    self.logger('WARNING', "--- REINÍCIO SUAVE ATIVADO ---")
                    self._daily_reset_if_needed(force=True)
                    self.martingale_state.clear()
                    self.logger('INFO', "Estado interno limpo. O bot está pronto para operar.")

                previous_status = current_status
                
                # Garante que o operador está conectado se o bot estiver RUNNING
                if current_status == 'RUNNING' and not self.exnova_operator.is_connected():
                    self.logger('INFO', "Operador desconectado. A tentar reconectar...", "OPERATOR")
                    self.exnova_operator.connect()
                    time.sleep(5) # Pausa para estabilizar a conexão
                    continue

                # Ciclo principal de operação
                if current_status == 'RUNNING':
                    self._daily_reset_if_needed()
                    if self._check_stop_limits():
                        continue

                    if not self.is_trade_active:
                        self.trading_cycle()
                else:
                    time.sleep(5) # Bot pausado, verifica com menos frequência
                
                time.sleep(1)

            except Exception as e:
                self.logger('ERROR', f"Loop principal falhou: {e}")
                traceback.print_exc()
                if self.exnova_operator:
                    self.logger('INFO', "A tentar reconectar o serviço do operador...", "OPERATOR")
                    self.exnova_operator.connect()
                time.sleep(15)

    def trading_cycle(self):
        now = datetime.utcnow()
        if now.second >= 58 and now.minute != self.last_analysis_minute:
            self.last_analysis_minute = now.minute
            self.logger('INFO', "Janela de análise M1 ATIVADA.")
            self.run_analysis_for_timeframe(60, 1)

    def run_analysis_for_timeframe(self, tf_secs, exp_mins):
        min_win_rate = self.bot_config.get('min_win_rate', 70)
        self.logger('INFO', f"A procurar sinais com assertividade mínima de {min_win_rate}%.")
        
        qualified_assets = self.supabase.get_cataloged_assets(min_win_rate)
        
        if not qualified_assets:
            self.logger('INFO', "Nenhum par catalogado cumpre os critérios de assertividade.")
            return
            
        self.logger('INFO', f"Pares qualificados: {[asset['pair'] for asset in qualified_assets]}")

        for asset in qualified_assets:
            with self.trade_lock:
                if self.is_trade_active:
                    break
            
            pair_name = asset['pair']
            best_strategy = asset['best_strategy']
            self.logger('INFO', f"A analisar {pair_name} com sua melhor estratégia: {best_strategy}...")
            
            self._analyze_asset(pair_name, tf_secs, exp_mins, best_strategy)

    def _analyze_asset(self, pair_name, tf_secs, exp_mins, strategy_name):
        try:
            strategy_function = self.strategy_map.get(strategy_name)
            if not strategy_function:
                self.logger('WARNING', f"Estratégia '{strategy_name}' não encontrada no mapa de estratégias.")
                return

            candles = self.exnova_operator.get_historical_candles(pair_name, tf_secs, 200)
            if not candles or len(candles) < 50:
                self.logger('WARNING', f"Velas insuficientes para analisar {pair_name}.")
                return

            direction = strategy_function(candles)
            if direction:
                now = datetime.utcnow()
                wait_time = (59 - now.second - 1) + (1 - now.microsecond / 1e6) + 0.2
                
                self.logger('SUCCESS', f"SINAL ENCONTRADO! {pair_name} | {strategy_name} | {direction.upper()}")
                
                signal = TradeSignal(pair=pair_name, direction=direction.lower(), strategy=strategy_name, **candles[-1])
                
                signal_id = self.supabase.insert_trade_signal(signal.to_dict(), status='PENDENTE')
                if not signal_id:
                    self.logger('ERROR', "Falha ao registar sinal PENDENTE na base de dados.")
                    return

                if wait_time > 0:
                    time.sleep(wait_time)

                self._execute_and_wait(signal, signal_id, pair_name, exp_mins)

        except Exception as e:
            self.logger('ERROR', f"Erro em _analyze_asset({pair_name}): {e}")
            traceback.print_exc()
            
    def _execute_and_wait(self, signal: TradeSignal, signal_id: int, full_name: str, exp_mins: int):
        with self.trade_lock:
            if self.is_trade_active:
                self.supabase.update_trade_result(signal_id, 'CANCELLED')
                self.logger('WARNING', f"Operação para {signal.pair} cancelada, outra operação já está ativa.")
                return
            self.is_trade_active = True

        try:
            entry_value = self._get_entry_value(signal.pair)
            
            success, order_id_or_message = self.exnova_operator.execute_trade(entry_value, full_name, signal.direction, exp_mins)
            
            if not success:
                self.logger('ERROR', f"Falha na execução da operação: {order_id_or_message}")
                self.supabase.update_trade_result(signal_id, 'ERROR', details=str(order_id_or_message))
                return

            self.supabase.update_trade_order_id(signal_id, order_id_or_message)
            self.logger('SUCCESS', f"Operação executada. ID da Ordem: {order_id_or_message}. A aguardar resultado...")
            
            win_status, pnl = self.exnova_operator.check_win(order_id_or_message)

            result = 'UNKNOWN'
            if win_status == 'win': result = 'WIN'
            elif win_status == 'loose': result = 'LOSS'
            elif win_status == 'equal': result = 'DRAW'

            self.logger('SUCCESS' if result == 'WIN' else 'ERROR', f"Resultado para {signal.pair}: {result} | P/L: ${pnl:.2f}")

            self.supabase.update_trade_result(signal_id, result, pnl=pnl, details=f"Finalizado: {win_status}")
            self._update_stats_and_martingale(result, signal, full_name, exp_mins, signal_id)

        except Exception as e:
            self.logger('ERROR', f"Erro crítico durante a execução e espera da operação: {e}")
            traceback.print_exc()
            self.supabase.update_trade_result(signal_id, 'ERROR', details=str(e))
        finally:
            with self.trade_lock:
                self.is_trade_active = False

    def _update_stats_and_martingale(self, result, signal, full_name, exp_mins, original_signal_id):
        if result == 'WIN':
            self.daily_wins += 1
            self.martingale_state[signal.pair] = {'level': 0}
        elif result == 'LOSS':
            self.daily_losses += 1
            if self.bot_config.get('use_martingale', False):
                level = self.martingale_state.get(signal.pair, {}).get('level', 0)
                max_levels = self.bot_config.get('martingale_levels', 2)
                if level < max_levels:
                    self.martingale_state[signal.pair] = {'level': level + 1}
                    self.logger('WARNING', f"A iniciar Martingale Nível {level + 1} para {signal.pair}...")
                    
                    # Cria um novo sinal para o martingale
                    candles = self.exnova_operator.get_historical_candles(signal.pair, 60, 1)
                    if not candles: 
                        self.logger('ERROR', f"Não foi possível obter velas para o Martingale em {signal.pair}.")
                        return
                    
                    mg_strategy_name = f"{signal.strategy}_MG_{level + 1}"
                    mg_signal = TradeSignal(pair=signal.pair, direction=signal.direction, strategy=mg_strategy_name, **candles[-1])
                    
                    # Regista o novo sinal de martingale na DB
                    mg_signal_id = self.supabase.insert_trade_signal(mg_signal.to_dict(), status='PENDENTE', martingale_level=level+1)
                    if not mg_signal_id:
                        self.logger('ERROR', "Falha ao registar sinal de Martingale na DB.")
                        return

                    self._execute_and_wait(mg_signal, mg_signal_id, full_name, exp_mins)
                else:
                    self.logger('ERROR', f"Nível máximo de Martingale atingido para {signal.pair}.")
                    self.martingale_state[signal.pair] = {'level': 0}

    def _get_entry_value(self, asset: str) -> float:
        base = self.bot_config.get('entry_value', 1.0)
        if not self.bot_config.get('use_martingale', False):
            return base
        
        level = self.martingale_state.get(asset, {}).get('level', 0)
        if level == 0:
            return base
            
        factor = self.bot_config.get('martingale_factor', 2.3)
        return round(base * (factor ** level), 2)

    def _check_stop_limits(self) -> bool:
        stop_win = self.bot_config.get('stop_win', 0)
        stop_loss = self.bot_config.get('stop_loss', 0)
        stop_mode = self.bot_config.get('stop_mode', 'operations')
        initial_balance = self.bot_config.get('daily_initial_balance', 0)
        current_balance = self.exnova_operator.get_current_balance() if self.exnova_operator else initial_balance
        
        limit_hit = False
        message = ""

        if stop_mode == 'operations':
            if stop_win > 0 and self.daily_wins >= stop_win:
                limit_hit, message = True, f"STOP WIN por operações atingido ({self.daily_wins}/{stop_win})."
            if not limit_hit and stop_loss > 0 and self.daily_losses >= stop_loss:
                limit_hit, message = True, f"STOP LOSS por operações atingido ({self.daily_losses}/{stop_loss})."
        elif stop_mode == 'percentage' and initial_balance > 0:
            profit_loss = current_balance - initial_balance
            profit_loss_percent = (profit_loss / initial_balance) * 100
            
            if stop_win > 0 and profit_loss_percent >= stop_win:
                limit_hit, message = True, f"STOP WIN por percentagem atingido ({profit_loss_percent:.2f}%/{stop_win}%)."
            if not limit_hit and stop_loss > 0 and profit_loss_percent <= -stop_loss:
                 limit_hit, message = True, f"STOP LOSS por percentagem atingido ({profit_loss_percent:.2f}%/-{stop_loss}%)."

        if limit_hit:
            self.logger('SUCCESS' if 'WIN' in message else 'ERROR', message)
            self.logger('WARNING', "O BOT FOI PAUSADO AUTOMATICAMENTE.")
            self.supabase.update_config({'status': 'PAUSED'})
            self.bot_config['status'] = 'PAUSED'
            return True
        return False

    def _daily_reset_if_needed(self, force=False):
        today = datetime.utcnow().date()
        if self.last_daily_reset_date != today or force:
            self.logger('INFO', f"NOVO DIA DETETADO ({today}). A zerar contadores diários.")
            self.daily_wins, self.daily_losses = 0, 0
            self.last_daily_reset_date = today
            if self.exnova_operator and self.exnova_operator.is_connected():
                bal = self.exnova_operator.get_current_balance()
                if bal:
                    self.supabase.update_config({'daily_initial_balance': bal})

    async def run(self):
        # 1. Inicializa Supabase
        self.supabase = SupabaseService(settings.SUPABASE_URL, settings.SUPABASE_KEY)
        self.logger('INFO', "Conexão com o Supabase estabelecida com sucesso.")

        # 2. Catalogação Inicial Síncrona
        self._perform_initial_cataloging()
        
        self.logger('INFO', "A iniciar o bot...")

        # 3. Inicializa e conecta os serviços permanentes
        self.exnova_operator = ExnovaService(settings.EXNOVA_EMAIL, settings.EXNOVA_PASSWORD)
        self.exnova_cataloger = ExnovaService(settings.EXNOVA_EMAIL, settings.EXNOVA_PASSWORD)
        
        self.logger('INFO', "A estabelecer conexão principal do operador...", "OPERATOR")
        op_check, op_reason = self.exnova_operator.connect()
        if not op_check:
            self.logger('CRITICAL', f"Falha ao conectar operador: {op_reason}. O bot será encerrado.", "OPERATOR")
            return
        
        self.logger('INFO', "A estabelecer conexão do catalogador...", "CATALOGER")
        cat_check, cat_reason = self.exnova_cataloger.connect()
        if not cat_check:
            self.logger('CRITICAL', f"Falha ao conectar catalogador: {cat_reason}. O bot continuará sem catalogação periódica.", "CATALOGER")
        
        # 4. Inicia as threads de fundo
        operator_thread = Thread(target=self.trading_loop_sync, daemon=True)
        cataloging_thread = Thread(target=self.cataloging_loop_sync, daemon=True)
        
        operator_thread.start()
        cataloging_thread.start()

        try:
            while self.is_running and operator_thread.is_alive():
                await asyncio.sleep(1)
        finally:
            self.is_running = False
            self.logger("INFO", "A encerrar o bot e as conexões...")
            if self.exnova_operator: self.exnova_operator.close()
            if self.exnova_cataloger: self.exnova_cataloger.close()
            self.logger("INFO", "Bot encerrado.")

