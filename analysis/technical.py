# analysis/technical.py
from typing import List, Tuple, Optional
import pandas as pd
from core.data_models import Candle

# Suas funções de Média Móvel
def calculate_sma(closes: List[float], period: int) -> float:
    if len(closes) < period:
        return 0.0
    return sum(closes[-period:]) / period

def calculate_ema(closes: List[float], period: int) -> float:
    if len(closes) < period:
        return 0.0
    series = pd.Series(closes)
    return series.ewm(span=period, adjust=False).mean().iloc[-1]

# Sua função de S/R em M15
def get_m15_sr_zones(m15_candles: List[Candle]) -> Tuple[Optional[float], Optional[float]]:
    """Retorna (resistência, suporte) extraídas dos pavios das últimas velas M15."""
    if not m15_candles:
        return None, None
    resistance = max(c.max for c in m15_candles)
    support    = min(c.min for c in m15_candles)
    return resistance, support

# Adicionada de volta para a estratégia funcionar
def is_near_level(price: float, zone: Optional[float], candles: List[Candle]) -> bool:
    """Verifica se um preço está próximo de um nível de S/R."""
    if zone is None or not candles:
        return False
    avg_candle_size = sum(c.max - c.min for c in candles[-10:]) / 10
    if avg_candle_size == 0:
        avg_candle_size = price * 0.0001
    proximity = avg_candle_size * 0.30
    return abs(price - zone) <= proximity

# Sua função de Rejeição, mais robusta
def is_rejection_candle(
    candle: Candle,
    wick_ratio: float = 0.30,
    max_body_ratio: float = 0.40
) -> Optional[str]:
    """
    Detecta vela de rejeição.
    Retorna 'TOP' se o pavio superior for significativo e o corpo pequeno.
    Retorna 'BOTTOM' se o pavio inferior for significativo e o corpo pequeno.
    """
    total_range = candle.max - candle.min
    if total_range == 0: return None

    body_size   = abs(candle.close - candle.open)
    upper_wick  = candle.max - max(candle.open, candle.close)
    lower_wick  = min(candle.open, candle.close) - candle.min

    if (body_size / total_range) > max_body_ratio:
        return None

    if (upper_wick / total_range) >= wick_ratio:
        return "TOP"
    if (lower_wick / total_range) >= wick_ratio:
        return "BOTTOM"
    return None

# Sua função de Engolfo, mais precisa
def is_engulfing(last: Candle, prev: Candle) -> Optional[str]:
    """Verifica engolfo baseado exclusivamente nos CORPOS."""
    prev_high = max(prev.open, prev.close)
    prev_low  = min(prev.open, prev.close)
    last_high = max(last.open, last.close)
    last_low  = min(last.open, last.close)

    if prev.close < prev.open and last.close > last.open:
        if last_high > prev_high and last_low < prev_low:
            return "BULLISH"

    if prev.close > prev.open and last.close < last.open:
        if last_high > prev_high and last_low < prev_low:
            return "BEARISH"
            
    return None
