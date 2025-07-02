# analysis/technical.py
from typing import List, Tuple, Optional
import pandas as pd
from core.data_models import Candle

# ---------- MME / MMS ----------
def calculate_sma(closes: List[float], period: int) -> float:
    if len(closes) < period:
        return 0.0
    return sum(closes[-period:]) / period

def calculate_ema(closes: List[float], period: int) -> float:
    if len(closes) < period:
        return 0.0
    series = pd.Series(closes)
    return series.ewm(span=period, adjust=False).mean().iloc[-1]

# ---------- S/R em M15 ----------
def get_m15_sr_zones(m15_candles: List[Candle]) -> Tuple[Optional[float], Optional[float]]:
    """Retorna (resistência, suporte) extraídas dos pavios das últimas velas M15."""
    if not m15_candles:
        return None, None
    resistance = max(c.max for c in m15_candles)
    support    = min(c.min for c in m15_candles)
    return resistance, support

# ---------- Rejeição ----------
def is_rejection_candle(
    candle: Candle,
    wick_ratio: float = 0.30,
    max_body_ratio: float = 0.40
) -> Optional[str]:
    """
    Detecta vela de rejeição.
    Retorna 'TOP'  se o pavio superior ≥ wick_ratio e corpo ≤ max_body_ratio.
    Retorna 'BOTTOM' se o pavio inferior ≥ wick_ratio e corpo ≤ max_body_ratio.
    Caso contrário, retorna None.
    """
    total_range = candle.max - candle.min
    if total_range == 0:
        return None

    body_size   = abs(candle.close - candle.open)
    upper_wick  = candle.max - max(candle.open, candle.close)
    lower_wick  = min(candle.open, candle.close) - candle.min

    # Corpo não pode ser grande
    if (body_size / total_range) > max_body_ratio:
        return None

    if (upper_wick / total_range) >= wick_ratio:
        return "TOP"
    if (lower_wick / total_range) >= wick_ratio:
        return "BOTTOM"
    return None

# ---------- Engolfo ----------
def is_engulfing(last: Candle, prev: Candle) -> Optional[str]:
    """
    Verifica engolfo baseado exclusivamente nos CORPOS.
    Retorna 'BULLISH' (engolfo de alta) ou 'BEARISH' (engolfo de baixa).
    """
    # Corpo da vela anterior
    prev_high = max(prev.open, prev.close)
    prev_low  = min(prev.open, prev.close)
    # Corpo da vela atual
    last_high = max(last.open, last.close)
    last_low  = min(last.open, last.close)

    # Engolfo de Alta: anterior vermelha, atual verde engolindo corpo
    if prev.close < prev.open and last.close > last.open:
        if last_high > prev_high and last_low < prev_low:
            return "BULLISH"

    # Engolfo de Baixa: anterior verde, atual vermelha engolindo corpo
    if prev.close > prev.open and last.close < last.open:
        if last_high > prev_high and last_low < prev_low:
            return "BEARISH"

    return None
