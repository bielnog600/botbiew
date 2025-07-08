# Arquivo: analysis/technical_indicators.py

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
    if not candles: return pd.DataFrame()
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

def validate_reversal_candle(candle: Candle, direction: str) -> bool:
    if not all([candle.open, candle.close, candle.max, candle.min]):
        return False
    body_size = abs(candle.close - candle.open)
    total_range = candle.max - candle.min
    if total_range == 0: return False
    if (body_size / total_range) < 0.5:
        return False
    upper_wick = candle.max - max(candle.open, candle.close)
    lower_wick = min(candle.open, candle.close) - candle.min
    if direction == 'call' and upper_wick > body_size: return False
    if direction == 'put' and lower_wick > body_size: return False
    return True

# ATUALIZADO: Função com um vocabulário de padrões de vela muito maior.
def check_candlestick_pattern(candles: List[Candle]) -> Optional[str]:
    """Identifica um conjunto expandido de padrões de vela de reversão com lógica interna."""
    if len(candles) < 3:
        return None

    c1, c2, c3 = candles[-3], candles[-2], candles[-1] # c3 é a vela que acabou de fechar

    # --- Padrões de 3 Velas ---
    # Estrela da Manhã (Morning Star) - Sinal de CALL
    if (c1.close < c1.open and abs(c1.close - c1.open) > 0 and # 1. Vela forte de baixa
        abs(c2.close - c2.open) < abs(c1.close - c1.open) and # 2. Vela pequena (indecisão)
        c3.close > c3.open and c3.close > (c1.open + c1.close) / 2): # 3. Vela de alta que recupera >50% da primeira
        return 'call'

    # Estrela da Noite (Evening Star) - Sinal de PUT
    if (c1.close > c1.open and abs(c1.close - c1.open) > 0 and # 1. Vela forte de alta
        abs(c2.close - c2.open) < abs(c1.close - c1.open) and # 2. Vela pequena (indecisão)
        c3.close < c3.open and c3.close < (c1.open + c1.close) / 2): # 3. Vela de baixa que recupera >50% da primeira
        return 'put'

    # --- Padrões de 2 Velas (usa c2 e c3) ---
    # Engolfo de Alta (Bullish Engulfing)
    if c2.close < c2.open and c3.close > c3.open and c3.open <= c2.close and c3.close >= c2.open:
        return 'call'

    # Engolfo de Baixa (Bearish Engulfing)
    if c2.close > c2.open and c3.close < c3.open and c3.open >= c2.close and c3.close <= c2.open:
        return 'put'
        
    # Piercing Line - Sinal de CALL
    if (c2.close < c2.open and c3.close > c3.open and 
        c3.open < c2.close and c3.close > (c2.open + c2.close) / 2):
        return 'call'

    # Dark Cloud Cover - Sinal de PUT
    if (c2.close > c2.open and c3.close < c3.open and
        c3.open > c2.close and c3.close < (c2.open + c2.close) / 2):
        return 'put'

    # Tweezer Bottom (Pinça de Fundo) - Sinal de CALL
    if c2.close < c2.open and c3.close > c3.open and abs(c2.min - c3.min) < (c2.max - c2.min) * 0.05: # Mínimas quase idênticas
        return 'call'

    # Tweezer Top (Pinça de Topo) - Sinal de PUT
    if c2.close > c2.open and c3.close < c3.open and abs(c2.max - c3.max) < (c2.max - c2.min) * 0.05: # Máximas quase idênticas
        return 'put'

    # --- Padrões de 1 Vela (usa c3) ---
    body = abs(c3.close - c3.open)
    if body > 0:
        lower_wick = min(c3.open, c3.close) - c3.min
        upper_wick = c3.max - max(c3.open, c3.close)
        
        # Martelo (Hammer) - Sinal de CALL
        if lower_wick >= 2 * body and upper_wick < body:
            return 'call'

        # Estrela Cadente (Shooting Star) - Sinal de PUT
        if upper_wick >= 2 * body and lower_wick < body:
            return 'put'
            
    # Doji (após uma tendência)
    total_range = c3.max - c3.min
    if total_range > 0 and (body / total_range) < 0.1:
        if c2.close < c2.open: return 'call' # Doji após vela de baixa
        if c2.close > c2.open: return 'put'  # Doji após vela de alta

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

def check_m5_price_action(candles: List[Candle], zones: Dict) -> Optional[Dict]:
    if len(candles) < 2: return None
    signal_candle = candles[-2]
    
    is_near_support = check_price_near_sr(signal_candle, {'support': zones.get('support', [])}) == 'call'
    if is_near_support:
        body_size = abs(signal_candle.close - signal_candle.open)
        if body_size > 0:
            lower_wick = min(signal_candle.open, signal_candle.close) - signal_candle.min
            if lower_wick >= 1.5 * body_size:
                return {'direction': 'call', 'confluences': ['SR_Zone_Support', 'Pinbar_Bullish']}

    is_near_resistance = check_price_near_sr(signal_candle, {'resistance': zones.get('resistance', [])}) == 'put'
    if is_near_resistance:
        body_size = abs(signal_candle.close - signal_candle.open)
        if body_size > 0:
            upper_wick = signal_candle.max - max(signal_candle.open, signal_candle.close)
            if upper_wick >= 1.5 * body_size:
                return {'direction': 'put', 'confluences': ['SR_Zone_Resistance', 'Pinbar_Bearish']}
            
    return None
