# analysis/technical.py
from typing import List, Tuple, Optional
import pandas as pd
from core.data_models import Candle

def calculate_sma(closes: List[float], period: int) -> float:
    if len(closes) < period: return 0.0
    return sum(closes[-period:]) / period

def calculate_ema(closes: List[float], period: int) -> float:
    if len(closes) < period: return 0.0
    series = pd.Series(closes)
    ema = series.ewm(span=period, adjust=False).mean()
    return ema.iloc[-1]

def get_m15_sr_zones(m15_candles: List[Candle]) -> Tuple[Optional[float], Optional[float]]:
    """
    Identifica as zonas de Suporte e Resistência com base nos pavios das últimas velas M15.
    Retorna (zona_de_resistencia, zona_de_suporte).
    """
    if not m15_candles:
        return None, None
    
    # A zona de resistência é a máxima mais alta dos últimos pavios.
    resistance = max(c.max for c in m15_candles)
    # A zona de suporte é a mínima mais baixa dos últimos pavios.
    support = min(c.min for c in m15_candles)
    
    return resistance, support

def is_rejection_candle(candle: Candle) -> Optional[str]:
    """
    Verifica se uma vela mostra forte rejeição.
    Retorna 'TOP' para rejeição de topo (pavio superior longo)
    ou 'BOTTOM' para rejeição de fundo (pavio inferior longo).
    """
    body_size = abs(candle.close - candle.open)
    if body_size == 0: return None # Doji não é uma vela de rejeição clara

    total_range = candle.max - candle.min
    if total_range == 0: return None

    upper_wick = candle.max - max(candle.open, candle.close)
    lower_wick = min(candle.open, candle.close) - candle.min

    # Rejeição de topo se o pavio superior for pelo menos 30% da vela
    if (upper_wick / total_range) >= 0.3:
        return "TOP"
    
    # Rejeição de fundo se o pavio inferior for pelo menos 30% da vela
    if (lower_wick / total_range) >= 0.3:
        return "BOTTOM"
        
    return None

def is_engulfing(last: Candle, prev: Candle) -> Optional[str]:
    """Verifica se a última vela engolfa a anterior."""
    # Engolfo de Alta
    if (prev.close < prev.open and last.close > last.open and
            last.close > prev.open and last.open < prev.close):
        return "BULLISH"
    # Engolfo de Baixa
    if (prev.close > prev.open and last.close < last.open and
            last.close < prev.open and last.open > prev.close):
        return "BEARISH"
    return None
