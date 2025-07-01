# analysis/technical.py
from typing import List, Tuple, Optional
import pandas as pd
from core.data_models import Candle

def calculate_sma(closes: List[float], period: int) -> float:
    """Calcula a Média Móvel Simples."""
    if len(closes) < period: return 0.0
    return sum(closes[-period:]) / period

def calculate_ema(closes: List[float], period: int) -> float:
    """Calcula a Média Móvel Exponencial (EMA) usando pandas."""
    if len(closes) < period:
        return 0.0
    series = pd.Series(closes)
    ema = series.ewm(span=period, adjust=False).mean()
    return ema.iloc[-1]

def get_sma_slope(closes: List[float], period: int) -> float:
    """Calcula a inclinação da SMA, indicando a nano-tendência."""
    if len(closes) < period + 2: return 0.0
    sma1 = sum(closes[-(period+1):-1]) / period
    sma2 = sum(closes[-period:]) / period
    return sma2 - sma1

def calculate_volatility(candles: List[Candle], lookback: int) -> float:
    """Calcula uma pontuação de volatilidade (0-1)."""
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

# FIX: Adicionadas as funções de Suporte e Resistência que estavam em falta.
def detect_sr_levels(candles: List[Candle], n_levels: int = 5) -> Tuple[List[float], List[float]]:
    """
    Detecta os níveis de Suporte e Resistência mais recentes usando fractais.
    Retorna (resistance_levels, support_levels).
    """
    if len(candles) < 5:
        return [], []

    highs = [c.max for c in candles]
    lows = [c.min for c in candles]
    
    resistance_levels = []
    support_levels = []

    for i in range(2, len(candles) - 2):
        # Fractal de Topo (Resistência)
        if highs[i] > highs[i-1] and highs[i] > highs[i-2] and highs[i] > highs[i+1] and highs[i] > highs[i+2]:
            resistance_levels.append(highs[i])
        
        # Fractal de Fundo (Suporte)
        if lows[i] < lows[i-1] and lows[i] < lows[i-2] and lows[i] < lows[i+1] and lows[i] < lows[i+2]:
            support_levels.append(lows[i])
            
    return sorted(resistance_levels, reverse=True)[:n_levels], sorted(support_levels, reverse=True)[:n_levels]

def is_near_level(price: float, levels: List[float], candles: List[Candle]) -> bool:
    """
    Verifica se um preço está próximo de algum dos níveis fornecidos.
    A proximidade é definida dinamicamente com base no tamanho médio das velas.
    """
    if not levels or not candles:
        return False
    
    avg_candle_size = sum(c.max - c.min for c in candles[-10:]) / 10
    # Se o tamanho médio for zero, define uma proximidade mínima para evitar divisão por zero
    if avg_candle_size == 0:
        avg_candle_size = price * 0.0001 

    proximity = avg_candle_size * 0.25

    for level in levels:
        if abs(price - level) <= proximity:
            return True
    return False
