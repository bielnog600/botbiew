# analysis/technical.py
from typing import List, Tuple, Optional, Union
import pandas as pd
from core.data_models import Candle

# --- Funções de Cálculo (SMA, EMA) ---
def calculate_sma(closes: List[float], period: int) -> float:
    if len(closes) < period: return 0.0
    return sum(closes[-period:]) / period

def calculate_ema(closes: List[float], period: int) -> float:
    if len(closes) < period: return 0.0
    series = pd.Series(closes)
    return series.ewm(span=period, adjust=False).mean().iloc[-1]

# --- Funções de Suporte e Resistência ---
def get_m15_sr_zones(m15_candles: List[Candle]) -> Tuple[Optional[float], Optional[float]]:
    if not m15_candles: return None, None
    resistance = max(c.max for c in m15_candles)
    support    = min(c.min for c in m15_candles)
    return resistance, support

# Sua função para verificar a proximidade de uma zona
def touches_zone(price: float, zone: Optional[float], tol: float = 0.00005) -> bool:
    """Verifica se um preço toca (±tol) uma zona."""
    if zone is None:
        return False
    return abs(price - zone) <= tol

# --- Funções de Análise de Padrões de Candle ---

def is_strong_candle(candle: Candle) -> bool:
    """Verifica se uma vela é 'de força' (corpo grande, pavios pequenos)."""
    body_size = abs(candle.close - candle.open)
    total_range = candle.max - candle.min
    if total_range == 0: return False
    return body_size / total_range >= 0.7

def is_engulfing(last: Candle, prev: Candle) -> Optional[str]:
    """Verifica engolfo baseado nos corpos."""
    prev_high = max(prev.open, prev.close)
    prev_low  = min(prev.open, prev.close)
    last_high = max(last.open, last.close)
    last_low  = min(last.open, last.close)

    if prev.is_bearish and last.is_bullish and last_high > prev_high and last_low < prev_low:
        return "BULLISH"
    if prev.is_bullish and last.is_bearish and last_high > prev_high and last_low < prev_low:
        return "BEARISH"
    return None
