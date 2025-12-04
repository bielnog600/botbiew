import asyncio
import traceback
from datetime import datetime
from typing import Dict, Optional, Set, List

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
        self.pending_martingale_trades: Dict[str, Dict] = {} 
        self.active_trading_pairs: Set[str] = set() 
        self.asset_performance: Dict[str, Dict[str, int]] = {}
        self.consecutive_losses: Dict[str, int] = {}
        self.blacklisted_assets: set = set()
        self.last_reset_time: datetime = datetime.utcnow()
        self.last_analysis_minute = -1
        self.last_daily_reset_date = None
        self.daily_wins = 0
        self.daily_losses = 0

    async def logger(self, level: str, message: str):
        """Logs para console e Supabase"""
        ts = datetime.utcnow().isoformat()
        print(f"[{ts}] [{level.upper()}] {message}", flush=True)
        try:
            await asyncio.to_thread(self.supabase.insert_log, level, message)
        except Exception:
            pass

    async def _hourly_cycle_reset(self):
        await self.logger('INFO', "CICLO HORÁRIO: Limpeza de stats e blacklist.")
        self.asset_performance.clear()
        self.consecutive_losses.clear()
        self.blacklisted_assets.clear()
        self.last_reset_time = datetime.utcnow()
        
    async def _daily_reset_if_needed(self):
        current_date_utc = datetime.utcnow().date()
        if self.last_daily_reset_date != current_date_utc:
            await self.logger('INFO', f"NOVO DIA ({current_date_utc}). Metas diárias zeradas.")
            self.daily_wins = 0
            self.daily_losses = 0
            self.last_daily_reset_date = current_date_utc
            bal = await self.exnova.get_current_balance()
            if bal > 0:
                await asyncio.to_thread(self.supabase.update_config, {'daily_initial_balance': bal, 'current_balance': bal})

    async def run(self):
        await self.logger('INFO', 'Bot a iniciar no modo DEBUG (Tagarela)...')
        
        # Conexão inicial
        if not await self.exnova.connect():
            await self.logger('ERROR', 'Falha na conexão inicial. Entrando em loop de recuperação.')

        await self._daily_reset_if_needed()

        while self.is_running:
            try:
                # --- AUTO-RECONNECT ---
                connected = True
                try:
                    if hasattr(self.exnova, 'is_connected'):
                         connected = await self.exnova.is_connected()
                except:
                    connected = True

                if not connected:
                    print("[AVISO] Conexão perdida detetada pelo loop principal. Reconectando...")
                    if await self.exnova.connect():
                        await self.logger('SUCCESS', 'Conexão restabelecida.')
                    else:
                        await asyncio.sleep(5)
                        continue
                # -----------------------

                await self._daily_reset_if_needed()
                
                if (datetime.utcnow() - self.last_reset_time).total_seconds() >= 3600:
                    await self._hourly_cycle_reset()

                self.bot_config = await asyncio.to_thread(self.supabase.get_bot_config)
                status = self.bot_config.get('status', 'PAUSED')

                if status == 'RUNNING':
                    # Martingales
                    pending_pairs = list(self.pending_martingale_trades.keys())
                    for pair in pending_pairs:
                        if pair not in self.active_trading_pairs:
                            asyncio.create_task(self._execute_martingale_trade(pair))

                    # Análise Normal
                    await self.trading_cycle()
                
                elif status != 'RUNNING':
                    if len(self.active_trading_pairs) > 0:
                        print(f"[PAUSA] Aguardando {len(self.active_trading_pairs)} trades finalizarem.")
                    await asyncio.sleep(2)

                await asyncio.sleep(1)

            except Exception as e:
                print(f"[LOOP ERROR] {e}")
                traceback.print_exc()
                await asyncio.sleep(5)

    async def trading_cycle(self):
        # Verifica conexão ANTES de tentar qualquer coisa
        try:
            if hasattr(self.exnova, 'is_connected') and not await self.exnova.is_connected():
                return # Aborta ciclo se desconectado
        except: pass

        now = datetime.utcnow()
        if now.second >= 50:
            if now.minute != self.last_analysis_minute:
                self.last_analysis_minute = now.minute
                
                is_m5 = (now.minute + 1) % 5 == 0
                
                if is_m5:
                    await self.logger('INFO', f"Iniciando varredura M5...")
                    asyncio.create_task(self.run_analysis_for_timeframe(300, 5))
                else:
                    await self.logger('INFO', f"Iniciando varredura M1...")
                    asyncio.create_task(self.run_analysis_for_timeframe(60, 1))

    async def run_analysis_for_timeframe(self, timeframe_seconds: int, expiration_minutes: int):
        # Proteção extra contra execução offline
        try:
            if hasattr(self.exnova, 'is_connected') and not await self.exnova.is_connected():
                print("[SKIP] Varredura abortada: Sem conexão.")
                return
        except: pass

        await self.exnova.change_balance(self.bot_config.get('account_type', 'PRACTICE'))
        
        assets = await self.exnova.get_open_assets()
        available_assets = [asset for asset in assets if asset.split('-')[0] not in self.blacklisted_assets]

        def get_asset_score(asset_name):
            pair = asset_name.split('-')[0]
            stats = self.asset_performance.get(pair, {'wins': 0, 'losses': 0})
            total = stats['wins'] + stats['losses']
            if total == 0: return 0.5
            return stats['wins'] / total

        target_assets = sorted(available_assets, key=get_asset_score, reverse=True)[:settings.MAX_ASSETS_TO_MONITOR]
        
        max_simultaneous = self.bot_config.get('max_simultaneous_trades', 1)
        if len(self.active_trading_pairs) >= max_simultaneous: 
            return

        tasks = []
        for asset in target_assets:
            if asset.split('-')[0] in self.active_trading_pairs: continue
            tasks.append(self._analyze_asset(asset, timeframe_seconds, expiration_minutes))

        if tasks: await asyncio.gather(*tasks)

    async def _analyze_asset(self, full_name: str, timeframe_seconds: int, expiration_minutes: int):
        base = full_name.split('-')[0]
        if base in self.active_trading_pairs: return

        try:
            if expiration_minutes == 1:
                t1, t2, res_func = 60, 900, get_m15_sr_zones
            elif expiration_minutes == 5:
                t1, t2, res_func = 300, 3600, get_h1_sr_zones
            else: return

            candles_tuple = await asyncio.gather(
                self.exnova.get_historical_candles(base, t1, 200),
                self.exnova.get_historical_candles(base, t2, 100)
            )
            analysis_candles, sr_candles = candles_tuple
            
            if not analysis_candles or not sr_candles:
                # Se não vieram velas, pode ser falha de conexão silenciosa
                return

            res, sup = res_func(sr_candles)
            signal_candle = analysis_candles[-1]
            final_direction, confluences = None, []
            zones = {'resistance': res, 'support': sup}
            threshold = self.bot_config.get('confirmation_threshold', 2)

            if expiration_minutes == 1:
                sr_signal = ti.check_price_near_sr(signal_candle, zones)
                
                if not sr_signal:
                    if base == "EURUSD": 
                        print(f"[DEBUG M1] {base}: Sem SR. Preço: {signal_candle.close} | S: {sup} R: {res}")
                else:
                    print(f"[SINAL M1] {base}: Toque em SR detetado ({sr_signal})! Verificando filtros...")
                    confluences.append("SR_Zone")
                    
                    pattern = ti.check_candlestick_pattern(analysis_candles)
                    if pattern == sr_signal: 
                        confluences.append("Candle_Pattern")
                        print(f"   -> Padrão de Vela OK ({pattern})")
                    else:
                        print(f"   -> Padrão de Vela falhou (Esperado: {sr_signal}, Deu: {pattern})")

                    rsi_sig = ti.check_rsi_condition(analysis_candles)
                    if rsi_sig == sr_signal: 
                        confluences.append("RSI_Condition")
                        print(f"   -> RSI OK ({rsi_sig})")
                    else:
                        print(f"   -> RSI falhou (Esperado: {sr_signal}, Deu: {rsi_sig})")

                    if len(confluences) >= threshold: 
                        final_direction = sr_signal
                    else:
                        print(f"   -> Confluências insuficientes: {len(confluences)}/{threshold}")

            elif expiration_minutes == 5:
                m5_signal = ti.check_m5_price_action(analysis_candles, zones)
                if m5_signal:
                    temp_conf = m5_signal['confluences']
                    rsi_sig = ti.check_rsi_condition(analysis_candles)
                    
                    if rsi_sig == m5_signal['direction']: 
                        temp_conf.append("RSI_Condition")
                    
                    print(f"[DEBUG M5] {base}: Sinal PriceAction {m5_signal['direction']}. Conf: {temp_conf}")
                    
                    if len(temp_conf) >= threshold:
                        final_direction = m5_signal['direction']
                        confluences = temp_conf
                else:
                    if base == "EURUSD": print(f"[DEBUG M5] {base}: Sem padrão de Price Action.")
            
            if final_direction:
                if not ti.validate_reversal_candle(signal_candle, final_direction): 
                    print(f"[{base}] Vela de reversão inválida.")
                    return
                
                max_trades = self.bot_config.get('max_simultaneous_trades', 1)
                if len(self.active_trading_pairs) >= max_trades: return

                now = datetime.utcnow()
                wait_sec = (60 - now.second - 1) + (1 - now.microsecond / 1000000) + 0.2
                await self.logger('INFO', f"Sinal CONFIRMADO em {base} ({final_direction}). Aguardando {wait_sec:.1f}s.")
                await asyncio.sleep(wait_sec)
                
                if base in self.active_trading_pairs: return
                self.active_trading_pairs.add(base)

                strategy = f"M{expiration_minutes}_" + ', '.join(confluences)
                await self.logger('SUCCESS', f"EXECUTANDO ORDEM: {base} | {final_direction.upper()} | {strategy}")
                
                signal = TradeSignal(
                    pair=base, direction=final_direction, strategy=strategy,
                    setup_candle_open=signal_candle.open, setup_candle_high=signal_candle.high,
                    setup_candle_low=signal_candle.low, setup_candle_close=signal_candle.close
                )
                
                trade_exp = 4 if expiration_minutes == 5 else expiration_minutes
                asyncio.create_task(self._execute_and_wait(signal, full_name, trade_exp))

        except Exception as e:
            if base in self.active_trading_pairs: self.active_trading_pairs.remove(base)
            print(f"[ERRO ANÁLISE] {base}: {e}")
            traceback.print_exc()

    async def _execute_martingale_trade(self, pair: str):
        trade_info = self.pending_martingale_trades.pop(pair, None)
        if not trade_info: return
        
        self.active_trading_pairs.add(pair)
        now = datetime.utcnow()
        next_min = (now.timestamp() // 60 + 1) * 60
        wait_sec = next_min - now.timestamp() + 0.2
        
        lvl = self.martingale_state.get(pair, {}).get('level', 1)
        await self.logger('WARNING', f"GALE {lvl} para {pair}. Aguardando {wait_sec:.2f}s.")
        await asyncio.sleep(wait_sec)

        strategy = f"M{trade_info['expiration_minutes']}_Gale_{lvl}"
        signal = TradeSignal(pair=trade_info['pair'], direction=trade_info['direction'], strategy=strategy)
        
        await self.logger('SUCCESS', f"ENTRADA GALE {pair}!")
        trade_exp = 4 if trade_info['expiration_minutes'] == 5 else trade_info['expiration_minutes']
        await self._execute_and_wait(signal, trade_info['full_name'], trade_exp)

    def _get_entry_value(self, asset: str, is_martingale: bool = False) -> float:
        base_val = self.bot_config.get('entry_value', 1.0)
        if not self.bot_config.get('use_martingale', False): return base_val
        mg_level = self.martingale_state.get(asset, {}).get('level', 0)
        level_calc = mg_level if is_martingale else 0
        if level_calc == 0: return base_val
        factor = self.bot_config.get('martingale_factor', 2.3)
        return round(base_val * (factor ** level_calc), 2)

    async def _execute_and_wait(self, signal: TradeSignal, full_name: str, expiration: int):
        try:
            is_gale = "Gale" in signal.strategy or "Martingale" in signal.strategy
            val = self._get_entry_value(signal.pair, is_martingale=is_gale)
            
            oid = await self.exnova.execute_trade(val, full_name, signal.direction.lower(), expiration)
            
            if not oid:
                await self.logger('ERROR', f"Falha ordem {full_name}.")
                if is_gale: self.martingale_state[signal.pair] = {'level': 0}
                self.active_trading_pairs.discard(signal.pair)
                return

            await self.logger('INFO', f"Ordem {oid} enviada. ${val}. Aguardando...")
            sid = await asyncio.to_thread(self.supabase.insert_trade_signal, signal)
            
            await asyncio.sleep(expiration * 60 + 15)
            result = await self.exnova.check_win(oid)
            
            await self.process_trade_result(signal.pair, full_name, result, sid, is_gale, expiration, signal.direction)

        except Exception as e:
            await self.logger('ERROR', f"Erro execução {full_name}: {e}")
        finally:
            self.active_trading_pairs.discard(signal.pair)

    async def process_trade_result(self, pair, full_name, result, sid, is_martingale, expiration, direction):
        await self.logger('SUCCESS' if result == 'win' else 'ERROR', f"Resultado {pair}: {result.upper()}")

        mg_lv = self.martingale_state.get(pair, {}).get('level', 0)
        
        if sid:
            await asyncio.to_thread(self.supabase.update_trade_result, sid, result.upper(), mg_lv)
        
        bal = await self.exnova.get_current_balance()
        if bal:
            await asyncio.to_thread(self.supabase.update_current_balance, bal)

        self.asset_performance.setdefault(pair, {'wins': 0, 'losses': 0})
        self.consecutive_losses.setdefault(pair, 0)

        if result == 'win':
            self.daily_wins += 1
            self.asset_performance[pair]['wins'] += 1
            self.consecutive_losses[pair] = 0
            self.martingale_state[pair] = {'level': 0}
            if pair in self.blacklisted_assets:
                self.blacklisted_assets.remove(pair)
                await self.logger('INFO', f"{pair} removido da blacklist.")
                
        elif result == 'loss':
            self.daily_losses += 1
            self.asset_performance[pair]['losses'] += 1
            self.consecutive_losses[pair] += 1
            
            if self.consecutive_losses[pair] >= 2:
                self.blacklisted_assets.add(pair)
                await self.logger('ERROR', f"{pair} -> Blacklist (2 loss seguidos).")

            if self.bot_config.get('use_martingale', False):
                cur_lv = self.martingale_state.get(pair, {}).get('level', 0)
                max_lv = self.bot_config.get('martingale_levels', 2)
                
                if cur_lv < max_lv:
                    self.martingale_state[pair] = {'level': cur_lv + 1}
                    self.pending_martingale_trades[pair] = {
                        "full_name": full_name, "direction": direction,
                        "expiration_minutes": expiration, "pair": pair
                    }
                    await self.logger('WARNING', f"Agendado Gale Nível {cur_lv + 1} para {pair}")
                else:
                    self.martingale_state[pair] = {'level': 0}
                    await self.logger('ERROR', f"Stop Gale em {pair}.")
