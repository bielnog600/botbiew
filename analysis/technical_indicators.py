# analysis/technical_indicators.py

import pandas as pd
import pandas_ta as ta
from typing import List, Dict, Optional

# A classe Candle deve ser definida ou importada de um local central, como core.data_models
# Para evitar erros de definição múltipla, é melhor importá-la se já existir em outro lugar.
# from core.data_models import Candle
class Candle:
    def __init__(self, data):
        self.open = data.get('open')
        self.max = data.get('max')
        self.min = data.get('min')
        self.close = data.get('close')

def _convert_candles_to_dataframe(candles: List[Candle]) -> pd.DataFrame:
    """Função auxiliar para converter a lista de candles em um DataFrame do Pandas."""
    if not candles:
        return pd.DataFrame()
    
    df = pd.DataFrame([vars(c) for c in candles])
    df.rename(columns={'max': 'high', 'min': 'low'}, inplace=True)
    
    for col in ['open', 'high', 'low', 'close']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    return df

# --- Funções dos Indicadores ---

def calculate_ema(candles: List[Candle], period: int) -> Optional[float]:
    """Calcula a Média Móvel Exponencial (EMA) usando pandas_ta."""
    if len(candles) < period:
        return None
    df = _convert_candles_to_dataframe(candles)
    if df.empty or 'close' not in df.columns or df['close'].isnull().any(): return None
    ema_series = ta.ema(df['close'], length=period)
    if ema_series is None or ema_series.empty:
        return None
    return ema_series.iloc[-1]

def calculate_atr(candles: List[Candle], period: int) -> Optional[float]:
    """Calcula o Average True Range (ATR) usando pandas_ta."""
    if len(candles) < period:
        return None
    df = _convert_candles_to_dataframe(candles)
    if df.empty or 'high' not in df.columns or df['high'].isnull().any(): return None
    atr_series = ta.atr(df['high'], df['low'], df['close'], length=period)
    if atr_series is None or atr_series.empty:
        return None
    return atr_series.iloc[-1]

def check_rsi_condition(candles: List[Candle], overbought=70, oversold=30, period=14) -> Optional[str]:
    """Verifica se o RSI está em sobrecompra ou sobrevenda usando pandas_ta."""
    if len(candles) < period:
        return None
    df = _convert_candles_to_dataframe(candles)
    if df.empty or 'close' not in df.columns or df['close'].isnull().any(): return None
    rsi_series = ta.rsi(df['close'], length=period)
    if rsi_series is None or rsi_series.empty:
        return None
    
    rsi_value = rsi_series.iloc[-1]
    if rsi_value > overbought:
        return 'put'
    if rsi_value < oversold:
        return 'call'
    return None

def validate_signal_candle(candle: Candle) -> bool:
    """
    Verifica se a vela tem um corpo forte e pavios pequenos.
    Retorna True se a vela for de alta qualidade, False caso contrário.
    """
    if not all([candle.open, candle.close, candle.max, candle.min]):
        return False
        
    body_size = abs(candle.close - candle.open)
    total_range = candle.max - candle.min

    if total_range == 0:
        return False

    is_strong_body = (body_size / total_range) >= 0.60
    return is_strong_body

def check_candlestick_pattern(candles: List[Candle]) -> Optional[str]:
    """Identifica um conjunto expandido de padrões de vela de reversão com lógica interna."""
    if len(candles) < 3:
        return None

    c1, c2, c3 = candles[-3], candles[-2], candles[-1]

    # A análise agora foca na vela ANTERIOR (c2) como a vela de sinal
    if not validate_signal_candle(c2):
        return None

    # Lógica para Engolfo de Alta (Bullish Engulfing)
    if c1.close < c1.open and c2.close > c2.open and c2.open <= c1.close and c2.close >= c1.open:
        return 'call'

    # Lógica para Engolfo de Baixa (Bearish Engulfing)
    if c1.close > c1.open and c2.close < c2.open and c2.open >= c1.close and c2.close <= c1.open:
        return 'put'

    # Lógica para Martelo (Hammer)
    body = abs(c2.close - c2.open)
    if body > 0:
        lower_wick = min(c2.open, c2.close) - c2.min
        upper_wick = c2.max - max(c2.open, c2.close)
        if lower_wick >= 2 * body and upper_wick < body:
            return 'call'

    # Lógica para Estrela Cadente (Shooting Star)
    if body > 0:
        lower_wick = min(c2.open, c2.close) - c2.min
        upper_wick = c2.max - max(c2.open, c2.close)
        if upper_wick >= 2 * body and lower_wick < body:
            return 'put'

    return None

def check_price_near_sr(last_candle: Candle, zones: Dict, tolerance=0.0005) -> Optional[str]:
    """Verifica se o preço está próximo a uma zona de S/R."""
    if last_candle is None or last_candle.close is None:
        return None
        
    price = last_candle.close
    for r in zones.get('resistance', []):
        if r is None: continue
        if abs(price - r) / r < tolerance:
            return 'put'
    for s in zones.get('support', []):
        if s is None: continue
        if abs(price - s) / s < tolerance:
            return 'call'
    return None
