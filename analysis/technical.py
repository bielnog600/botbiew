# analysis/technical.py
from typing import List, Tuple, Optional
from core.data_models import Candle

# --- Funções de Cálculo (SMA, Volatilidade) - Inalteradas ---
def calculate_sma(closes: List[float], period: int) -> float:
    if len(closes) < period: return 0.0
    return sum(closes[-period:]) / period

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

# --- Funções de Suporte e Resistência - Inalteradas ---
def detect_sr_levels(candles: List[Candle], n_levels: int = 5) -> Tuple[List[float], List[float]]:
    if len(candles) < 5: return [], []
    highs = [c.max for c in candles]
    lows = [c.min for c in candles]
    resistance_levels, support_levels = [], []
    for i in range(2, len(candles) - 2):
        if highs[i] > highs[i-1] and highs[i] > highs[i-2] and highs[i] > highs[i+1] and highs[i+2]:
            resistance_levels.append(highs[i])
        if lows[i] < lows[i-1] and lows[i] < lows[i-2] and lows[i] < lows[i+1] and lows[i+2]:
            support_levels.append(lows[i])
    return sorted(resistance_levels, reverse=True)[:n_levels], sorted(support_levels, reverse=True)[:n_levels]

def is_near_level(price: float, levels: List[float], candles: List[Candle]) -> bool:
    if not levels or not candles: return False
    avg_candle_size = sum(c.max - c.min for c in candles[-10:]) / 10
    proximity = avg_candle_size * 0.25
    for level in levels:
        if abs(price - level) <= proximity: return True
    return False

# --- NOVAS FUNÇÕES DE ANÁLISE DE PADRÕES ---

def is_strong_candle(candle: Candle) -> bool:
    """Verifica se uma vela é 'de força' (corpo grande, pavios pequenos)."""
    body_size = abs(candle.close - candle.open)
    total_range = candle.max - candle.min
    # Considera-se forte se o corpo for pelo menos 70% do tamanho total da vela.
    return body_size > 0 and body_size / total_range >= 0.7

def is_pinbar(candle: Candle) -> Optional[str]:
    """Verifica se uma vela é um Pin Bar (Martelo ou Estrela Cadente)."""
    body_size = abs(candle.close - candle.open)
    if body_size == 0: return None
    
    lower_wick = (candle.open if candle.close > candle.open else candle.close) - candle.min
    upper_wick = candle.max - (candle.close if candle.close > candle.open else candle.open)

    # Martelo (rejeição de baixa)
    if lower_wick > body_size * 2 and upper_wick < body_size * 0.5:
        return "HAMMER"
    # Estrela Cadente (rejeição de alta)
    if upper_wick > body_size * 2 and lower_wick < body_size * 0.5:
        return "SHOOTING_STAR"
    return None

def is_engulfing(last: Candle, prev: Candle) -> Optional[str]:
    """Verifica se a última vela engolfa a anterior."""
    if (prev.close < prev.open and last.close > last.open and
            last.close > prev.open and last.open < prev.close):
        return "BULLISH"
    if (prev.close > prev.open and last.close < last.open and
            last.close < prev.open and last.open > prev.close):
        return "BEARISH"
    return None

def is_inside_bar(last: Candle, prev: Candle) -> bool:
    """Verifica se a última vela é um Inside Bar."""
    return prev.max > last.max and prev.min < last.min
