# analysis/technical.py
from typing import List, Tuple, Optional
import pandas as pd
from core.data_models import Candle

def calculate_sma(closes: List[float], period: int) -> float:
    if len(closes) < period: return 0.0
    return sum(closes[-period:]) / period

def calculate_ema(closes: List[float], period: int) -> float:
    """Calcula a Média Móvel Exponencial (EMA) usando pandas."""
    if len(closes) < period:
        return 0.0
    # Usar a biblioteca pandas é a forma mais robusta e padrão da indústria para calcular EMA
    series = pd.Series(closes)
    ema = series.ewm(span=period, adjust=False).mean()
    return ema.iloc[-1]

# O resto das funções (get_sma_slope, calculate_volatility, etc.) permanecem as mesmas,
# mas não serão usadas pela nova estratégia. Podemos mantê-las para uso futuro.

def get_sma_slope(closes: List[float], period: int) -> float:
    if len(closes) < period + 2: return 0.0
    sma1 = sum(closes[-(period+1):-1]) / period
    sma2 = sum(closes[-period:]) / period
    return sma2 - sma1

def calculate_volatility(candles: List[Candle], lookback: int) -> float:
    if len(candles) < lookback: return 1.0
    recent_candles = candles[-lookback:]
    total_range, total_body = 0, 0
    for c in recent_candles:
        candle_range = c.max - c.min
        if candle_range > 0:
            total_range += candle_range
            total_body += abs(c.close - c.open)
    if total_range == 0: return 0.0
    return (total_range - total_body) / total_range
