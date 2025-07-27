import sys
import os
import asyncio
import time
import traceback
from datetime import datetime
from typing import Dict, Optional, List
from threading import Thread

# Adiciona o diretório pai ao path para permitir importações relativas
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
        
        # --- ATRIBUTOS PARA O MARTINGALE ---
        self.pending_martingale_trade: Optional[Dict] = None
        self.martingale_state: Dict[str, Dict] = {} # Armazena o nível de gale por ativo

        self.strategy_map: Dict[str, callable] = {
            'Pullback MQL': ti.strategy_mql_pullback,
            'Padrão de Reversão': ti.strategy_reversal_pattern,
            'Fluxo de Tendência': ti.strategy_trend_flow,
            'Reversão por Exaustão': ti.strategy_exhaustion_reversal,
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

    def _run_async(self, coro):
        if self.main_loop and self.main_loop.is_running():
            return asyncio.run_coroutine_threadsafe(coro, self.main_loop)
        return None

    def logger(self, level: str, message: str):
        ts = datetime.utcnow().isoformat()
        print(f"[{ts}] [{level.upper()}] {message}", flush=True)
        if self.supabase:
            self._run_async(self.supabase.insert_log(level, message))
            
    def _soft_restart(self):
        self.logger('WARNING', "--- REINÍCIO SUAVE ATIVADO ---")
        self.asset_strategy_map.clear()
        self.asset_performance.clear()
        self.consecutive_losses.clear()
        self.blacklisted_assets.clear()
        self.is_trade_active = False
        self.pending_martingale_trade = None
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
        self.logger('INFO', f"Encontrados {len(open_assets)} ativos. A analisar cada um...")
        for asset in open_assets:
            base_name = asset.split('-')[0]
            try:
                historical_candles = self.exnova.get_historical_candles(base_name, 60, 500)
                if not historical_candles or len(historical_candles) < 100:
                    self.logger('WARNING', f"Dados históricos insuficientes para {base_name}.")
                    continue
                best_strategy_for_asset = None
                highest_win_rate = 0
                for strategy_name, strategy_func in self.strategy_map.items():
                    wins, losses, total_trades = 0, 0, 0
                    for i in range(50, len(historical_candles) - 1):
                        past_candles = historical_candles[:i]
                        signal_candle = past_candles[-1]
                        result_candle = historical_candles[i]
                        signal = strategy_func(past_candles)
                        if signal:
                            total_trades += 1
                            if signal == 'call' and result_candle['close'] > signal_candle['close']: wins += 1
                            elif signal == 'put' and result_candle['close'] < signal_candle['close']: wins += 1
                            else: losses += 1
                    if total_trades > 10:
                        win_rate = (wins / total_trades) * 100
                        if win_rate > highest_win_rate:
                            highest_win_rate, best_strategy_for_asset = win_rate, strategy_name
                if best_strategy_for_asset and highest_win_rate >= 55:
                    self.asset_strategy_map[base_name] = best_strategy_for_asset
                    self.logger('SUCCESS', f"==> Melhor estratégia para {base_name} definida como: '{best_strategy_for_asset}' ({highest_win_rate:.2f}%)")
                else:
                    self.logger('WARNING', f"==> Nenhuma estratégia atingiu a assertividade mínima para {base_name}.")
            except Exception as e:
                self.logger('ERROR', f"Erro ao catalogar o ativo {base_name}: {e}"); traceback.print_exc()
        self.logger('INFO', "--- CATALOGAÇÃO CONCLUÍDA ---")

    def trading_loop_sync(self):
        self.logger('INFO', 'A iniciar o bot...')
        if not self.exnova.connect(): self.is_running = False; return
        profile_data = self.exnova.get_profile()
        if not profile_data: self.is_running = False; return
        try:
            self.currency_char = profile_data.get('currency_char', '$')
            self.logger('SUCCESS', f"Perfil carregado! Olá, {profile_data.get('name', 'Utilizador')}.")
        except Exception: self.is_running = False; return
        
        self.bot_config = self._run_async(self.supabase.get_bot_config()).result()
        self.current_account_type = self.bot_config.get('account_type', 'PRACTICE')
        self.previous_status = self.bot_config.get('status', 'PAUSED')
        self.exnova.change_balance(self.current_account_type)
        self.logger('INFO', f"Conta inicial definida para: {self.current_account_type}")
        
        self._daily_reset_if_needed()
        if self.previous_status == 'RUNNING':
            self._run_cataloging()

        while self.is_running:
            try:
                if (datetime.utcnow() - self.last_reset_time).total_seconds() >= 3600:
                    self._hourly_cycle_reset()
                self._daily_reset_if_needed()

                self.bot_config = self._run_async(self.supabase.get_bot_config()).result()
                current_status = self.bot_config.get('status', 'PAUSED')

                if current_status == 'RUNNING' and self.previous_status == 'PAUSED': self._soft_restart()
                self.previous_status = current_status

                desired_account_type = self.bot_config.get('account_type', 'PRACTICE')
                if desired_account_type != self.current_account_type:
                    self.logger('WARNING', f"MUDANÇA DE CONTA! De {self.current_account_type} para {desired_account_type}.")
                    self.exnova.change_balance(desired_account_type)
                    self.current_account_type = desired_account_type

                if current_status == 'RUNNING':
                    if self.pending_martingale_trade and not self.is_trade_active:
                        self._execute_martingale_trade()
                    elif not self.is_trade_active:
                        self.trading_cycle()
                else:
                    self.logger('INFO', "Bot PAUSADO. A aguardar o estado 'RUNNING' no painel.")
                    time.sleep(5) 

                time.sleep(1)
                
            except Exception as e:
                self.logger('ERROR', f"Loop principal falhou: {e}"); traceback.print_exc(); time.sleep(30)

    def trading_cycle(self):
        now = datetime.utcnow()
        if now.second >= 45 and now.minute != self.last_analysis_minute:
            self.last_analysis_minute = now.minute
            self.logger('INFO', f"Janela de análise M1 ATIVADA. A procurar oportunidades...")
            self.run_analysis_for_timeframe(60, 1)
        elif now.second % 15 == 0:
            self.logger('INFO', f"A aguardar janela de análise (segundo atual: {now.second})...")

    def run_analysis_for_timeframe(self, timeframe_seconds: int, expiration_minutes: int):
        assets_with_strategy = list(self.asset_strategy_map.keys())
        if not assets_with_strategy:
            self.logger('INFO', "Nenhum ativo qualificado para análise no momento.")
            return

        def get_asset_score(pair):
            stats = self.asset_performance.get(pair, {'wins': 0, 'losses': 0})
            return (stats['wins'] + 1) / (stats['wins'] + stats['losses'] + 2)
        
        prioritized_pairs = sorted(assets_with_strategy, key=get_asset_score, reverse=True)
        all_open_assets = self.exnova.get_open_assets()

        for pair in prioritized_pairs:
            if self.is_trade_active: break
            full_asset_name = next((asset for asset in all_open_assets if asset.startswith(pair)), None)
            if full_asset_name and full_asset_name.split('-')[0] not in self.blacklisted_assets:
                self._analyze_asset(full_asset_name, timeframe_seconds, expiration_minutes)

    def _analyze_asset(self, full_name: str, timeframe_seconds: int, expiration_minutes: int):
        try:
            if self.is_trade_active: return
            base_name = full_name.split('-')[0]
            best_strategy_name = self.asset_strategy_map.get(base_name)
            if not best_strategy_name: return

            self.logger('INFO', f"A analisar {base_name} com a sua melhor estratégia: '{best_strategy_name}'...")
            
            analysis_candles = self.exnova.get_historical_candles(base_name, 60, 50)
            if not analysis_candles or len(analysis_candles) < 20: return

            volatility_profile = self.bot_config.get('volatility_profile', 'EQUILIBRADO')
            if volatility_profile != 'DESATIVADO':
                atr_limits = {'ULTRA_CONSERVADOR': (0.00001, 0.00015), 'CONSERVADOR': (0.00010, 0.00050), 'EQUILIBRADO': (0.00030, 0.00100), 'AGRESSIVO': (0.00080, 0.00200), 'ULTRA_AGRESSIVO': (0.00150, 999.0)}
                min_atr, max_atr = atr_limits.get(volatility_profile, (0.00030, 0.00100))
                atr_value = ti.calculate_atr(analysis_candles)
                if atr_value is None or not (min_atr <= atr_value <= max_atr):
                    atr_text = f"{atr_value:.6f}" if atr_value is not None else "N/A"
                    self.logger('INFO', f"[{base_name}] Análise abortada: Volatilidade (ATR {atr_text}) fora dos limites para o perfil '{volatility_profile}'."); return

            strategy_function = self.strategy_map.get(best_strategy_name)
            if not strategy_function: return
            final_direction = strategy_function(analysis_candles)
            if not final_direction: return

            signal_candle = analysis_candles[-1]
            if not ti.validate_reversal_candle(signal_candle, final_direction): return
            
            if self.is_trade_active: return
            now = datetime.utcnow()
            wait_seconds = (60 - now.second - 1) + (1 - now.microsecond / 1000000) + 0.2
            self.logger('SUCCESS', f"SINAL ENCONTRADO! Ativo: {base_name}, Estratégia: {best_strategy_name}, Direção: {final_direction.upper()}")
            time.sleep(wait_seconds)
            self.is_trade_active = True
            signal = TradeSignal(pair=base_name, direction=final_direction, strategy=best_strategy_name, setup_candle_open=signal_candle['open'], setup_candle_high=signal_candle['max'], setup_candle_low=signal_candle['min'], setup_candle_close=signal_candle['close'])
            self._execute_and_wait(signal, full_name, expiration_minutes)

        except Exception as e:
            self.logger('ERROR', f"Erro em _analyze_asset({full_name}): {e}"); traceback.print_exc()

    def _execute_and_wait(self, signal: TradeSignal, full_name: str, expiration_minutes: int):
        try:
            is_martingale_trade = "Martingale" in signal.strategy
            entry_value = self._get_entry_value(signal.pair, is_martingale=is_martingale_trade)
            balance_before = self.exnova.get_current_balance()
            if balance_before is None:
                self.logger('ERROR', "Não foi possível obter saldo antes da operação. A cancelar."); self.is_trade_active = False; return
            
            order_id = self.exnova.execute_trade(entry_value, full_name, signal.direction.lower(), expiration_minutes)
            if not order_id:
                self.logger('ERROR', f"Falha ao executar ordem para {full_name}."); self.is_trade_active = False; return

            self.logger('INFO', f"Ordem {order_id} enviada. Valor: {self.currency_char}{entry_value:.2f}. Saldo pré-op: {self.currency_char}{balance_before:.2f}")
            sid_future = self._run_async(self.supabase.insert_trade_signal(signal))
            
            time.sleep(expiration_minutes * 60 + 5)
            
            balance_after = self.exnova.get_current_balance()
            result = 'UNKNOWN'
            if balance_after is not None:
                self.logger('INFO', f"Saldo pós-op: {self.currency_char}{balance_after:.2f}. A comparar com: {self.currency_char}{balance_before:.2f}")
                profit = round(balance_after - balance_before, 2)
                if profit > 0: result = 'WIN'
                elif profit < 0: result = 'LOSS'
                else: result = 'DRAW'
            else: self.logger('ERROR', "Não foi possível obter saldo após a operação.")
            
            self.logger('SUCCESS' if result == 'WIN' else 'ERROR', f"Resultado da ordem {order_id}: {result}")
            sid = sid_future.result() if sid_future else None
            if sid:
                mg_lv = self.martingale_state.get(signal.pair, {}).get('level', 0)
                self._run_async(self.supabase.update_trade_result(sid, result, mg_lv))
            if balance_after is not None: self._run_async(self.supabase.update_current_balance(balance_after))
            
            self._update_stats_and_martingale(result, signal, full_name, expiration_minutes)
        finally:
            # --- CORREÇÃO DO BUG DE CONGELAMENTO ---
            # Independentemente de ter um martingale pendente, a operação ATUAL terminou.
            # A flag is_trade_active deve ser liberada para que o loop principal possa
            # decidir o que fazer a seguir (executar o gale ou procurar novo sinal).
            self.is_trade_active = False
            self.logger('INFO', 'Ciclo de operação concluído. O loop principal irá decidir a próxima ação.')

    # --- FUNÇÕES DE MARTINGALE ---

    def _execute_martingale_trade(self):
        """Prepara e executa a operação de Martingale pendente."""
        trade_info = self.pending_martingale_trade
        if not trade_info: return

        self.pending_martingale_trade = None # Limpa o lembrete

        now = datetime.utcnow()
        wait_seconds = (60 - now.second - 1) + (1 - now.microsecond / 1000000)
        
        current_level = self.martingale_state.get(trade_info['pair'], {}).get('level', 1)
        self.logger('WARNING', f"MARTINGALE NÍVEL {current_level} PREPARADO para {trade_info['pair']}. A aguardar {wait_seconds:.2f}s para entrada precisa na próxima vela.")
        
        if wait_seconds > 0:
            time.sleep(wait_seconds)

        self.is_trade_active = True
        strategy_name = f"{trade_info['strategy']}_MG_{current_level}"
        
        signal = TradeSignal(
            pair=trade_info['pair'], 
            direction=trade_info['direction'], 
            strategy=strategy_name
        )
        
        self.logger('SUCCESS', f"EXECUTANDO MARTINGALE! Ativo: {trade_info['pair']}, Direção: {signal.direction.upper()}.")
        
        self._execute_and_wait(signal, trade_info['full_name'], trade_info['expiration_minutes'])

    def _get_entry_value(self, asset: str, is_martingale: bool = False) -> float:
        """Calcula o valor da entrada, considerando o Martingale se aplicável."""
        base_value = self.bot_config.get('entry_value', 1.0)
        
        if not self.bot_config.get('use_martingale', False):
            return base_value
            
        mg_level = self.martingale_state.get(asset, {}).get('level', 0)
        
        if mg_level == 0:
            return base_value
        
        factor = self.bot_config.get('martingale_factor', 2.3)
        mg_value = base_value * (factor ** mg_level)
        
        return round(mg_value, 2)

    def _update_stats_and_martingale(self, result: str, signal: TradeSignal, full_name: str, expiration_minutes: int):
        """Atualiza as estatísticas e prepara o Martingale se necessário."""
        pair = signal.pair
        self.asset_performance.setdefault(pair, {'wins': 0, 'losses': 0})
        self.consecutive_losses.setdefault(pair, 0)

        if result == 'WIN':
            self.daily_wins += 1
            self.asset_performance[pair]['wins'] += 1
            self.consecutive_losses[pair] = 0
            self.martingale_state[pair] = {'level': 0} # Zera o Martingale no WIN
            if pair in self.blacklisted_assets: self.blacklisted_assets.remove(pair)

        elif result == 'LOSS':
            self.daily_losses += 1
            self.asset_performance[pair]['losses'] += 1
            self.consecutive_losses[pair] += 1
            if self.consecutive_losses[pair] >= 2:
                self.blacklisted_assets.add(pair)
                self.logger('ERROR', f"O par {pair} foi colocado na lista negra por 1 hora.")

            use_mg = self.bot_config.get('use_martingale', False)
            if use_mg:
                current_level = self.martingale_state.get(pair, {}).get('level', 0)
                max_levels = self.bot_config.get('martingale_levels', 2)
                
                if current_level < max_levels:
                    next_level = current_level + 1
                    self.martingale_state[pair] = {'level': next_level}
                    
                    self.pending_martingale_trade = {
                        "full_name": full_name, 
                        "direction": signal.direction,
                        "expiration_minutes": expiration_minutes, 
                        "pair": pair,
                        "strategy": signal.strategy.split('_MG_')[0] # Pega o nome da estratégia original
                    }
                    self.logger('WARNING', f"MARTINGALE NÍVEL {next_level} ATIVADO para {pair}.")
                else:
                    self.martingale_state[pair] = {'level': 0}
                    self.logger('ERROR', f"Nível máximo de Martingale atingido para {pair}. Ciclo encerrado.")
        
        stop_win = self.bot_config.get('stop_win') or 0
        stop_loss = self.bot_config.get('stop_loss') or 0
        if (stop_win > 0 and self.daily_wins >= stop_win) or \
           (stop_loss > 0 and self.daily_losses >= stop_loss):
            msg = f"META DE STOP WIN ATINGIDA!" if self.daily_wins >= stop_win else f"META DE STOP LOSS ATINGIDA!"
            self.logger('SUCCESS' if result == 'WIN' else 'ERROR', f"{msg} A pausar o bot.")
            self._run_async(self.supabase.update_config({'status': 'PAUSED'}))

    # --- Funções de Ciclo de Vida ---
    async def run(self):
        self.supabase = SupabaseService(settings.SUPABASE_URL, settings.SUPABASE_KEY)
        self.main_loop = asyncio.get_running_loop()
        trading_thread = Thread(target=self.trading_loop_sync, daemon=True)
        trading_thread.start()
        while self.is_running and trading_thread.is_alive(): await asyncio.sleep(1)

    def _hourly_cycle_reset(self):
        self.logger('INFO', "--- RESET DE CICLO HORÁRIO ---")
        self._soft_restart()

    def _daily_reset_if_needed(self):
        current_date_utc = datetime.utcnow().date()
        if self.last_daily_reset_date != current_date_utc:
            self.logger('INFO', f"NOVO DIA DETETADO ({current_date_utc}). A zerar contadores diários.")
            self.daily_wins, self.daily_losses = 0, 0
            self.last_daily_reset_date = current_date_utc
            bal = self.exnova.get_current_balance()
            if bal is not None and self.supabase:
                self._run_async(self.supabase.update_config({'daily_initial_balance': bal, 'current_balance': bal}))
