# analysis/technical.py
from typing import List, Tuple, Optional
from core.data_models import Candle

def calculate_sma(closes: List[float], period: int) -> float:
    """Calcula a Média Móvel Simples."""
    if len(closes) < period:
        return 0.0
    return sum(closes[-period:]) / period

def get_sma_slope(closes: List[float], period: int) -> float:
    """Calcula a inclinação da SMA, indicando a nano-tendência."""
    if len(closes) < period + 2:
        return 0.0
    sma1 = sum(closes[-(period+1):-1]) / period
    sma2 = sum(closes[-period:]) / period
    return sma2 - sma1

def calculate_volatility(candles: List[Candle], lookback: int) -> float:
    """Calcula uma pontuação de volatilidade (0-1)."""
    if len(candles) < lookback:
        return 1.0
    recent_candles = candles[-lookback:]
    total_range = 0
    total_body = 0
    for c in recent_candles:
        candle_range = c.max - c.min
        if candle_range > 0:
            total_range += candle_range
            total_body += abs(c.close - c.open)
    if total_range == 0:
        return 0.0
    wick_proportion = (total_range - total_body) / total_range
    return wick_proportion

def detect_sr_levels(candles: List[Candle], n_levels: int = 5) -> Tuple[List[float], List[float]]:
    """Detecta os níveis de Suporte e Resistência mais recentes usando fractais."""
    if len(candles) < 5:
        return [], []
    highs = [c.max for c in candles]
    lows = [c.min for c in candles]
    resistance_levels, support_levels = [], []
    for i in range(2, len(candles) - 2):
        if highs[i] > highs[i-1] and highs[i] > highs[i-2] and highs[i] > highs[i+1] and highs[i] > highs[i+2]:
            resistance_levels.append(highs[i])
        if lows[i] < lows[i-1] and lows[i] < lows[i-2] and lows[i] < lows[i+1] and lows[i] < lows[i+2]:
            support_levels.append(lows[i])
    return sorted(resistance_levels, reverse=True)[:n_levels], sorted(support_levels, reverse=True)[:n_levels]

def is_near_level(price: float, levels: List[float], candles: List[Candle]) -> bool:
    """Verifica se um preço está próximo de algum dos níveis fornecidos."""
    if not levels or not candles:
        return False
    avg_candle_size = sum(c.max - c.min for c in candles[-10:]) / 10
    proximity = avg_candle_size * 0.25
    for level in levels:
        if abs(price - level) <= proximity:
            return True
    return False

def detect_candle_pattern(last: Candle, prev: Candle) -> Optional[str]:
    """
    Detecta padrões de candlestick de reversão de 2 velas.
    Retorna o nome do padrão ou None.
    """
    # Engolfo de Alta (Bullish Engulfing)
    if (prev.close < prev.open and last.close > last.open and
            last.close > prev.open and last.open < prev.close):
        return "BULLISH_ENGULFING"

    # Engolfo de Baixa (Bearish Engulfing)
    if (prev.close > prev.open and last.close < last.open and
            last.close < prev.open and last.open > prev.close):
        return "BEARISH_ENGULFING"

    # Martelo (Hammer) - Sinal de fundo
    body_size = abs(last.close - last.open)
    lower_wick = last.open - last.min if last.close > last.open else last.close - last.min
    upper_wick = last.max - last.close if last.close > last.open else last.max - last.open
    if body_size > 0 and lower_wick > body_size * 2 and upper_wick < body_size:
        return "HAMMER"

    # Estrela Cadente (Shooting Star) - Sinal de topo
    if body_size > 0 and upper_wick > body_size * 2 and lower_wick < body_size:
        return "SHOOTING_STAR"

    return None
