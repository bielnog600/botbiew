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

def check_candlestick_pattern(candles: List[Candle]) -> Optional[str]:
    if len(candles) < 3: return None
    c1, c2 = candles[-3], candles[-2]
    if c1.close < c1.open and c2.close > c2.open and c2.open <= c1.close and c2.close >= c1.open:
        return 'call'
    if c1.close > c1.open and c2.close < c2.open and c2.open >= c1.close and c2.close <= c1.open:
        return 'put'
    body = abs(c2.close - c2.open)
    if body > 0:
        lower_wick = min(c2.open, c2.close) - c2.min
        upper_wick = c2.max - max(c2.open, c2.close)
        if lower_wick >= 2 * body and upper_wick < body: return 'call'
        if upper_wick >= 2 * body and lower_wick < body: return 'put'
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

# NOVO: Estratégia específica para M5 baseada em Price Action
def check_m5_price_action(candles: List[Candle], zones: Dict) -> Optional[Dict]:
    """
    Analisa a vela anterior em busca de um sinal de Pinbar (pavio longo)
    próximo a uma zona de Suporte ou Resistência.
    """
    if len(candles) < 2:
        return None

    signal_candle = candles[-2] # A vela que acabou de fechar

    # 1. Analisa para um sinal de COMPRA (CALL) em Suporte
    is_near_support = check_price_near_sr(signal_candle, {'support': zones.get('support', [])}) == 'call'
    if is_near_support:
        body_size = abs(signal_candle.close - signal_candle.open)
        if body_size > 0:
            lower_wick = min(signal_candle.open, signal_candle.close) - signal_candle.min
            # Condição: Pavio inferior é pelo menos 1.5x o tamanho do corpo
            if lower_wick >= 1.5 * body_size:
                return {'direction': 'call', 'confluences': ['SR_Zone_Support', 'Pinbar_Bullish']}

    # 2. Analisa para um sinal de VENDA (PUT) em Resistência
    is_near_resistance = check_price_near_sr(signal_candle, {'resistance': zones.get('resistance', [])}) == 'put'
    if is_near_resistance:
        body_size = abs(signal_candle.close - signal_candle.open)
        if body_size > 0:
            upper_wick = signal_candle.max - max(signal_candle.open, signal_candle.close)
            # Condição: Pavio superior é pelo menos 1.5x o tamanho do corpo
            if upper_wick >= 1.5 * body_size:
                return {'direction': 'put', 'confluences': ['SR_Zone_Resistance', 'Pinbar_Bearish']}
            
    return None
