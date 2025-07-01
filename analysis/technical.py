# analysis/technical.py
from typing import List
from core.data_models import Candle

def calculate_sma(closes: List[float], period: int) -> float:
    """Calcula a Média Móvel Simples."""
    if len(closes) < period:
        return 0.0
    return sum(closes[-period:]) / period

def get_sma_slope(closes: List[float], period: int) -> float:
    """Calcula a inclinação da SMA, indicando a nano-tendência."""
    if len(closes) < period + 1:
        return 0.0
    sma1 = calculate_sma(closes[:-(period+1)], period)
    sma2 = calculate_sma(closes, period)
    return sma2 - sma1

def calculate_volatility(candles: List[Candle], lookback: int) -> float:
    """
    Calcula uma pontuação de volatilidade.
    Valores mais altos indicam mais "nervosismo" (pavios longos).
    """
    if len(candles) < lookback:
        return 1.0 # Retorna valor alto se não houver dados suficientes

    recent_candles = candles[-lookback:]
    total_range = 0
    total_body = 0

    for c in recent_candles:
        total_range += c.max - c.min
        total_body += abs(c.close - c.open)

    if total_range == 0:
        return 0.0

    # A pontuação é a proporção do tamanho dos pavios em relação ao range total
    wick_proportion = (total_range - total_body) / total_range
    return wick_proportion
