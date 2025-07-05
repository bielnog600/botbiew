# analysis/technical_indicators.py

import pandas as pd
import pandas_ta as ta
from typing import List, Dict, Optional

class Candle:
    def __init__(self, data):
        self.open = data.get('open')
        self.max = data.get('max')
        self.min = data.get('min')
        self.close = data.get('close')

def _convert_candles_to_dataframe(candles: List[Candle]) -> pd.DataFrame:
    if not candles:
        return pd.DataFrame()
    
    df = pd.DataFrame([vars(c) for c in candles])
    df.rename(columns={'max': 'high', 'min': 'low'}, inplace=True)
    
    for col in ['open', 'high', 'low', 'close']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    return df

# --- Funções dos Indicadores ---

def calculate_ema(candles: List[Candle], period: int) -> Optional[float]:
    if len(candles) < period: return None
    df = _convert_candles_to_dataframe(candles)
    if df.empty or 'close' not in df.columns or df['close'].isnull().any(): return None
    return ta.ema(df['close'], length=period).iloc[-1]

def calculate_atr(candles: List[Candle], period: int) -> Optional[float]:
    if len(candles) < period: return None
    df = _convert_candles_to_dataframe(candles)
    if df.empty or 'high' not in df.columns or df['high'].isnull().any(): return None
    return ta.atr(df['high'], df['low'], df['close'], length=period).iloc[-1]

def check_rsi_condition(candles: List[Candle], overbought=70, oversold=30, period=14) -> Optional[str]:
    if len(candles) < period: return None
    df = _convert_candles_to_dataframe(candles)
    if df.empty or 'close' not in df.columns or df['close'].isnull().any(): return None
    rsi_value = ta.rsi(df['close'], length=period).iloc[-1]
    if rsi_value > overbought: return 'put'
    if rsi_value < oversold: return 'call'
    return None

# NOVO: Função para validar a qualidade da vela de sinal
def validate_signal_candle(candle: Candle) -> bool:
    """
    Verifica se a vela tem um corpo forte e pavios pequenos.
    Retorna True se a vela for de alta qualidade, False caso contrário.
    """
    body_size = abs(candle.close - candle.open)
    total_range = candle.max - candle.min

    # Evita divisão por zero e velas sem corpo
    if total_range == 0 or body_size == 0:
        return False

    # Regra: O corpo deve ser pelo menos 60% do tamanho total da vela.
    # Isto garante que não é uma vela de indecisão (doji) com pavios longos.
    is_strong_body = (body_size / total_range) >= 0.60
    
    return is_strong_body

# ATUALIZADO: A análise de padrões agora usa a validação da vela
def check_candlestick_pattern(candles: List[Candle]) -> Optional[str]:
    if len(candles) < 3: return None

    c1, c2, c3 = candles[-3], candles[-2], candles[-1]

    # A análise agora foca na vela ANTERIOR (c2) como a vela de sinal
    if not validate_signal_candle(c2):
        return None # Ignora se a vela de sinal for fraca

    # Lógica para Engolfo de Alta
    if c1.close < c1.open and c2.close > c2.open and c2.open <= c1.close and c2.close >= c1.open:
        return 'call'

    # Lógica para Engolfo de Baixa
    if c1.close > c1.open and c2.close < c2.open and c2.open >= c1.close and c2.close <= c1.open:
        return 'put'

    # Lógica para Martelo (Hammer)
    body = abs(c2.close - c2.open)
    lower_wick = min(c2.open, c2.close) - c2.min
    upper_wick = c2.max - max(c2.open, c2.close)
    if lower_wick >= 2 * body and upper_wick < body:
        return 'call'

    # Lógica para Estrela Cadente (Shooting Star)
    if upper_wick >= 2 * body and lower_wick < body:
        return 'put'
        
    return None

def check_price_near_sr(last_candle: Candle, zones: Dict, tolerance=0.0005) -> Optional[str]:
    if last_candle is None or last_candle.close is None: return None
    price = last_candle.close
    for r in zones.get('resistance', []):
        if r is None: continue
        if abs(price - r) / r < tolerance: return 'put'
    for s in zones.get('support', []):
        if s is None: continue
        if abs(price - s) / s < tolerance: return 'call'
    return None
```

---

### Passo 2: Corrigir `core/bot.py`

Agora vamos reestruturar o ciclo principal do bot para garantir que ele espere por um resultado antes de fazer qualquer outra coisa.

**Substitua o conteúdo inteiro do seu arquivo `core/bot.py` por este código:**


```python
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

    async def logger(self, level: str, message: str):
        ts = datetime.utcnow().isoformat()
        print(f"[{ts}] [{level.upper()}] {message}", flush=True)
        await self.supabase.insert_log(level, message)

    # ATUALIZADO: O loop principal agora é mais simples e seguro
    async def run(self):
        await self.logger('INFO', 'Bot a iniciar com LÓGICA DE EXECUÇÃO ÚNICA E ANÁLISE DE VELA...')
        await self.exnova.connect()
        
        while self.is_running:
            try:
                self.bot_config = await self.supabase.get_bot_config()
                status = self.bot_config.get('status', 'PAUSED')

                # A condição principal: só opera se estiver RUNNING e NENHUMA operação estiver ativa
                if status == 'RUNNING' and not self.is_trade_active:
                    await self.trading_cycle()
                else:
                    if status != 'RUNNING':
                        await self.logger('INFO', "Bot PAUSADO. Aguardando status 'RUNNING'.")
                    # Se uma trade está ativa, este log aparecerá, o que é o comportamento correto
                    elif self.is_trade_active:
                         await self.logger('INFO', "Operação em andamento. Aguardando resultado...")

                # Espera antes de verificar novamente
                await asyncio.sleep(settings.BOT_CONFIG_POLL_INTERVAL)

            except Exception as e:
                await self.logger('ERROR', f"Loop principal falhou: {e}")
                traceback.print_exc()
                await asyncio.sleep(30) # Espera mais em caso de erro grave

    # ATUALIZADO: O ciclo agora decide qual análise fazer e retorna
    async def trading_cycle(self):
        now = datetime.utcnow()
        # Se estamos nos primeiros 5 segundos de um minuto que é múltiplo de 5, analisa M5
        if now.minute % 5 == 0 and now.second < 5:
            await self.run_analysis_for_timeframe(timeframe_seconds=300, expiration_minutes=5)
        # Se estamos nos primeiros 5 segundos de qualquer outro minuto, analisa M1
        elif now.second < 5:
            await self.run_analysis_for_timeframe(timeframe_seconds=60, expiration_minutes=1)

    async def run_analysis_for_timeframe(self, timeframe_seconds: int, expiration_minutes: int):
        await self.logger('INFO', f"Iniciando ciclo de análise para M{expiration_minutes}...")
        await self.exnova.change_balance(self.bot_config.get('account_type', 'PRACTICE'))
        assets = await self.exnova.get_open_assets()
        
        # Cria uma tarefa de análise para cada ativo
        tasks = [self._analyze_asset(asset, timeframe_seconds, expiration_minutes) for asset in assets[:settings.MAX_ASSETS_TO_MONITOR]]
        await asyncio.gather(*tasks)

    # ATUALIZADO: A análise agora inclui a validação da vela de sinal
    async def _analyze_asset(self, full_name: str, timeframe_seconds: int, expiration_minutes: int):
        try:
            # Se uma trade já foi acionada por outra análise, para esta.
            if self.is_trade_active:
                return

            base = full_name.split('-')[0]
            
            # A análise é feita na vela que ACABOU de fechar
            primary_candles_count = 500
            context_candles_count = 100

            if expiration_minutes == 1:
                analysis_candles, sr_candles = await asyncio.gather(
                    self.exnova.get_historical_candles(base, 60, primary_candles_count),
                    self.exnova.get_historical_candles(base, 900, context_candles_count),
                )
                if not analysis_candles or not sr_candles: return
                res, sup = get_m15_sr_zones(sr_candles)
            
            elif expiration_minutes == 5:
                analysis_candles, sr_candles = await asyncio.gather(
                    self.exnova.get_historical_candles(base, 300, primary_candles_count),
                    self.exnova.get_historical_candles(base, 3600, context_candles_count),
                )
                if not analysis_candles or not sr_candles: return
                res, sup = get_h1_sr_zones(sr_candles)
            else:
                return

            # --- BUSCA POR CONFLUÊNCIAS DE REVERSÃO ---
            confluences = {'call': [], 'put': []}
            zones = {'resistance': res, 'support': sup}
            
            # A vela de sinal é a penúltima vela (a que acabou de fechar)
            signal_candle = analysis_candles[-2]
            
            # CONFLUÊNCIA 1: Validação da Qualidade da Vela de Sinal
            if ti.validate_signal_candle(signal_candle):
                confluences[candle_signal].append("Strong_Candle") if (candle_signal := ti.check_candlestick_pattern(analysis_candles)) else None
            
            # CONFLUÊNCIA 2: Zona de Suporte/Resistência
            if (sr_signal := ti.check_price_near_sr(signal_candle, zones)):
                confluences[sr_signal].append("SR_Zone")
            
            # CONFLUÊNCIA 3: Condição do RSI
            if (rsi_signal := ti.check_rsi_condition(analysis_candles)):
                confluences[rsi_signal].append("RSI_Condition")
            
            # --- DECISÃO FINAL ---
            final_direction = None
            confirmation_threshold = 2
            if len(confluences['call']) >= confirmation_threshold:
                final_direction = 'call'
            elif len(confluences['put']) >= confirmation_threshold:
                final_direction = 'put'
            
            if final_direction:
                # Garante que não entramos em duas trades ao mesmo tempo
                if self.is_trade_active: return
                self.is_trade_active = True # Bloqueia novas entradas

                strategy_name = f"M{expiration_minutes}_" + ', '.join(confluences[final_direction])
                await self.logger('SUCCESS', f"[{base}-M{expiration_minutes}] SINAL VÁLIDO! Direção: {final_direction.upper()}. Confluências: {strategy_name}")
                
                signal = TradeSignal(pair=base, direction=final_direction, strategy=strategy_name,
                                     setup_candle_open=signal_candle.open, setup_candle_high=signal_candle.max,
                                     setup_candle_low=signal_candle.min, setup_candle_close=signal_candle.close)
                
                await self._execute_and_wait(signal, full_name, expiration_minutes)

        except Exception as e:
            await self.logger('ERROR', f"Erro em _analyze_asset({full_name}, M{expiration_minutes}): {e}")
            traceback.print_exc()

    # ... (os métodos _get_entry_value e _execute_and_wait permanecem os mesmos) ...

    def _get_entry_value(self, asset: str) -> float:
        base = self.bot_config.get('entry_value', settings.ENTRY_VALUE)
        if not self.bot_config.get('use_martingale', False):
            return base
        state = self.martingale_state.get(asset, {'level': 0, 'last_value': base})
        if state['level'] == 0:
            return base
        return round(state['last_value'] * self.bot_config.get('martingale_factor', 2.3), 2)

    async def _execute_and_wait(self, signal: TradeSignal, full_name: str, expiration_minutes: int):
        try:
            bal_before = await self.exnova.get_current_balance()
            entry_value = self._get_entry_value(signal.pair)
            sid = await self.supabase.insert_trade_signal(signal)
            if not sid:
                await self.logger('ERROR', f"[{signal.pair}] Falha ao inserir sinal, abortando.")
                self.is_trade_active = False # Libera o bloqueio se falhar
                return

            order_id = await self.exnova.execute_trade(entry_value, full_name, signal.direction.lower(), expiration_minutes)
            await self.logger('INFO', f"[{signal.pair}] Ordem {order_id} enviada. Valor: {entry_value}. Expiração: {expiration_minutes} min. Aguardando...")
            
            await asyncio.sleep(expiration_minutes * 60 + 5)

            bal_after = await self.exnova.get_current_balance()
            
            if bal_before is None or bal_after is None:
                result = 'UNKNOWN'
            else:
                delta = bal_after - bal_before
                result = 'WIN' if delta > 0 else 'LOSS' if delta < 0 else 'DRAW'
            await self.logger('SUCCESS' if result == 'WIN' else 'ERROR', f"[{signal.pair}] Resultado: {result}. ΔSaldo = {delta:.2f}")

            mg_lv = self.martingale_state.get(signal.pair, {}).get('level', 0)
            await self.supabase.update_trade_result(sid, result, mg_lv)
            await self.supabase.update_current_balance(bal_after or 0.0)

            if self.bot_config.get('use_martingale', False):
                if result == 'WIN':
                    self.martingale_state[signal.pair] = {'level': 0, 'last_value': entry_value}
                elif result == 'LOSS':
                    lvl = mg_lv + 1
                    max_lv = self.bot_config.get('martingale_levels', 2)
                    if lvl <= max_lv:
                        self.martingale_state[signal.pair] = {'level': lvl, 'last_value': entry_value}
                    else: 
                        self.martingale_state[signal.pair] = {'level': 0, 'last_value': self.bot_config.get('entry_value', entry_value)}

        except Exception as e:
            await self.logger('ERROR', f"_execute_and_wait({signal.pair}) falhou: {e}")
            traceback.print_exc()
        finally:
            self.is_trade_active = False # Libera o bloqueio APÓS a operação ser concluída
            await self.logger('INFO', 'Pronto para próxima análise.')
