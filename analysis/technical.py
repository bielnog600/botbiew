# analysis/technical.py
from typing import List, Tuple, Optional
from core.data_models import Candle

def get_m15_sr_zones(m15_candles: List[Candle]) -> Tuple[Optional[float], Optional[float]]:
    """Identifica as zonas de Suporte e Resistência com base nos pavios das últimas velas M15."""
    if not m15_candles:
        return None, None
    resistance = max(c.max for c in m15_candles)
    support = min(c.min for c in m15_candles)
    return resistance, support

def is_near_level(price: float, zone: Optional[float], candles: List[Candle]) -> bool:
    """Verifica se um preço está próximo de um nível de S/R."""
    if zone is None or not candles:
        return False
    avg_candle_size = sum(c.max - c.min for c in candles[-10:]) / 10
    if avg_candle_size == 0:
        avg_candle_size = price * 0.0001
    proximity = avg_candle_size * 0.30
    return abs(price - zone) <= proximity

def is_engulfing(last: Candle, prev: Candle) -> Optional[str]:
    """Verifica se a última vela engolfa a anterior."""
    if prev.is_bearish and last.is_bullish and last.close > prev.open and last.open < prev.close:
        return "BULLISH"
    if prev.is_bullish and last.is_bearish and last.close < prev.open and last.open > prev.close:
        return "BEARISH"
    return None
