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

# --- Funções dos Indicadores (com lógica profissional) ---

def calculate_ema(candles: List[Candle], period: int) -> Optional[float]:
    if len(candles) < period:
        return None
    df = _convert_candles_to_dataframe(candles)
    ema_series = ta.ema(df['close'], length=period)
    if ema_series is None or ema_series.empty:
        return None
    return ema_series.iloc[-1]

def calculate_atr(candles: List[Candle], period: int) -> Optional[float]:
    if len(candles) < period:
        return None
    df = _convert_candles_to_dataframe(candles)
    atr_series = ta.atr(df['high'], df['low'], df['close'], length=period)
    if atr_series is None or atr_series.empty:
        return None
    return atr_series.iloc[-1]

def check_rsi_condition(candles: List[Candle], overbought=70, oversold=30, period=14) -> Optional[str]:
    if len(candles) < period:
        return None
    df = _convert_candles_to_dataframe(candles)
    rsi_series = ta.rsi(df['close'], length=period)
    if rsi_series is None or rsi_series.empty:
        return None
    
    rsi_value = rsi_series.iloc[-1]
    if rsi_value > overbought:
        return 'put'
    if rsi_value < oversold:
        return 'call'
    return None

# MODIFICADO: Esta função agora usa apenas os reconhecedores de padrões
# que são 100% Python, evitando a necessidade da TA-Lib.
def check_candlestick_pattern(candles: List[Candle]) -> Optional[str]:
    if len(candles) < 2:
        return None

    df = _convert_candles_to_dataframe(candles)
    
    # Analisa padrões individualmente. Estas funções não precisam da TA-Lib.
    engulfing = ta.cdl_engulfing(df['open'], df['high'], df['low'], df['close'])
    hammer = ta.cdl_hammer(df['open'], df['high'], df['low'], df['close'])
    shooting_star = ta.cdl_shootingstar(df['open'], df['high'], df['low'], df['close'])

    # Verifica o último candle
    if (engulfing.iloc[-1] == 100) or (hammer.iloc[-1] == 100):
        return 'call'
    
    if (engulfing.iloc[-1] == -100) or (shooting_star.iloc[-1] == -100):
        return 'put'
        
    return None

def check_price_near_sr(last_candle: Candle, zones: Dict, tolerance=0.0005) -> Optional[str]:
    if last_candle is None or last_candle.close is None:
        return None
        
    price = last_candle.close
    for r in zones.get('resistance', []):
        if abs(price - r) / r < tolerance:
            return 'put'
    for s in zones.get('support', []):
        if abs(price - s) / s < tolerance:
            return 'call'
    return None
