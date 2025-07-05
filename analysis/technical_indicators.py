# analysis/technical_indicators.py

import pandas as pd
import pandas_ta as ta
from typing import List, Dict, Optional

class Candle:
    def __init__(self, data):
        self.open = data.get('open')
        self.max = data.get('max')
        self.min = data.get('min')
        self.close = data.get('close')

def _convert_candles_to_dataframe(candles: List[Candle]) -> pd.DataFrame:
    if not candles: return pd.DataFrame()
    df = pd.DataFrame([vars(c) for c in candles])
    df.rename(columns={'max': 'high', 'min': 'low'}, inplace=True)
    for col in ['open', 'high', 'low', 'close']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    return df

# --- Funções dos Indicadores ---

def calculate_ema(candles: List[Candle], period: int) -> Optional[float]:
    if len(candles) < period: return None
    df = _convert_candles_to_dataframe(candles)
    if df.empty or 'close' not in df.columns or df['close'].isnull().any(): return None
    return ta.ema(df['close'], length=period).iloc[-1]

def calculate_atr(candles: List[Candle], period: int) -> Optional[float]:
    if len(candles) < period: return None
    df = _convert_candles_to_dataframe(candles)
    if df.empty or 'high' not in df.columns or df['high'].isnull().any(): return None
    return ta.atr(df['high'], df['low'], df['close'], length=period).iloc[-1]

def check_rsi_condition(candles: List[Candle], overbought=70, oversold=30, period=14) -> Optional[str]:
    if len(candles) < period: return None
    df = _convert_candles_to_dataframe(candles)
    if df.empty or 'close' not in df.columns or df['close'].isnull().any(): return None
    rsi_value = ta.rsi(df['close'], length=period).iloc[-1]
    if rsi_value > overbought: return 'put'
    if rsi_value < oversold: return 'call'
    return None

# NOVO: Função para validar a qualidade da vela de sinal
def validate_reversal_candle(candle: Candle, direction: str) -> bool:
    """
    Verifica se a vela de sinal é forte e não tem pavios contrários.
    - Para um CALL, não pode ter um grande pavio superior (pressão de venda).
    - Para um PUT, não pode ter um grande pavio inferior (pressão de compra).
    """
    if not all([candle.open, candle.close, candle.max, candle.min]):
        return False
        
    body_size = abs(candle.close - candle.open)
    total_range = candle.max - candle.min

    if total_range == 0: return False

    # Regra 1: Corpo deve ser pelo menos 50% do tamanho total da vela.
    if (body_size / total_range) < 0.6:
        return False

    upper_wick = candle.max - max(candle.open, candle.close)
    lower_wick = min(candle.open, candle.close) - candle.min

    # Regra 2: Rejeita sinais com forte pressão contrária.
    # O pavio contrário não pode ser maior que o corpo.
    if direction == 'call' and upper_wick > body_size:
        return False
    
    if direction == 'put' and lower_wick > body_size:
        return False

    return True

def check_candlestick_pattern(candles: List[Candle]) -> Optional[str]:
    """Identifica um conjunto expandido de padrões de vela de reversão."""
    if len(candles) < 3: return None
    c1, c2 = candles[-3], candles[-2]

    if c1.close < c1.open and c2.close > c2.open and c2.open <= c1.close and c2.close >= c1.open:
        return 'call'
    if c1.close > c1.open and c2.close < c2.open and c2.open >= c1.close and c2.close <= c1.open:
        return 'put'
        
    body = abs(c2.close - c2.open)
    if body > 0:
        lower_wick = min(c2.open, c2.close) - c2.min
        upper_wick = c2.max - max(c2.open, c2.close)
        if lower_wick >= 2 * body and upper_wick < body: return 'call' # Martelo
        if upper_wick >= 2 * body and lower_wick < body: return 'put' # Estrela Cadente
            
    return None

def check_price_near_sr(last_candle: Candle, zones: Dict, tolerance=0.0005) -> Optional[str]:
    if last_candle is None or last_candle.close is None: return None
    price = last_candle.close
    for r in zones.get('resistance', []):
        if r is None: continue
        if abs(price - r) / r < tolerance: return 'put'
    for s in zones.get('support', []):
        if s is None: continue
        if abs(price - s) / s < tolerance: return 'call'
    return None
