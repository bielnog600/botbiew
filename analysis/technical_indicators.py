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

def check_candlestick_pattern(candles: List[Candle]) -> Optional[str]:
    if len(candles) < 2: return None
    df = _convert_candles_to_dataframe(candles)
    if df.empty or len(df.columns) < 4 or df.isnull().values.any(): return None

    # Anexa apenas os padrões que não precisam da TA-Lib
    df.ta.cdl_engulfing(append=True)
    df.ta.cdl_hammer(append=True)
    df.ta.cdl_shootingstar(append=True)

    last_candle = df.iloc[-1]
    
    is_engulfing_bullish = last_candle.get('CDL_ENGULFING', 0) == 100
    is_hammer = last_candle.get('CDL_HAMMER', 0) == 100
    is_engulfing_bearish = last_candle.get('CDL_ENGULFING', 0) == -100
    is_shooting_star = last_candle.get('CDL_SHOOTINGSTAR', 0) == -100

    if is_engulfing_bullish or is_hammer: return 'call'
    if is_engulfing_bearish or is_shooting_star: return 'put'
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
