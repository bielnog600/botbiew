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
    """Função auxiliar para converter a lista de candles em um DataFrame do Pandas."""
    if not candles:
        return pd.DataFrame()
    
    df = pd.DataFrame([vars(c) for c in candles])
    df.rename(columns={'max': 'high', 'min': 'low'}, inplace=True)
    
    for col in ['open', 'high', 'low', 'close']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    return df

# --- Funções dos Indicadores (com lógica profissional) ---

def calculate_ema(candles: List[Candle], period: int) -> Optional[float]:
    """Calcula a Média Móvel Exponencial (EMA) usando pandas_ta."""
    if len(candles) < period:
        return None
    df = _convert_candles_to_dataframe(candles)
    if df.empty or 'close' not in df.columns: return None
    ema_series = ta.ema(df['close'], length=period)
    if ema_series is None or ema_series.empty:
        return None
    return ema_series.iloc[-1]

def calculate_atr(candles: List[Candle], period: int) -> Optional[float]:
    """Calcula o Average True Range (ATR) usando pandas_ta."""
    if len(candles) < period:
        return None
    df = _convert_candles_to_dataframe(candles)
    if df.empty or 'high' not in df.columns: return None
    atr_series = ta.atr(df['high'], df['low'], df['close'], length=period)
    if atr_series is None or atr_series.empty:
        return None
    return atr_series.iloc[-1]

def check_rsi_condition(candles: List[Candle], overbought=70, oversold=30, period=14) -> Optional[str]:
    """Verifica se o RSI está em sobrecompra ou sobrevenda usando pandas_ta."""
    if len(candles) < period:
        return None
    df = _convert_candles_to_dataframe(candles)
    if df.empty or 'close' not in df.columns: return None
    rsi_series = ta.rsi(df['close'], length=period)
    if rsi_series is None or rsi_series.empty:
        return None
    
    rsi_value = rsi_series.iloc[-1]
    if rsi_value > overbought:
        return 'put'
    if rsi_value < oversold:
        return 'call'
    return None

# CORRIGIDO: Esta função agora usa a sintaxe correta do pandas-ta.
def check_candlestick_pattern(candles: List[Candle]) -> Optional[str]:
    """Identifica padrões de vela de reversão usando chamadas de função diretas."""
    if len(candles) < 2:
        return None

    df = _convert_candles_to_dataframe(candles)
    if df.empty or len(df.columns) < 4:
        return None

    # Analisa padrões individualmente. Estas funções não precisam da TA-Lib.
    # O 'talib=False' força o uso da implementação interna em Python.
    engulfing = ta.engulfing(open_=df['open'], high=df['high'], low=df['low'], close=df['close'], talib=False)
    hammer = ta.hammer(open_=df['open'], high=df['high'], low=df['low'], close=df['close'], talib=False)
    shooting_star = ta.shootingstar(open_=df['open'], high=df['high'], low=df['low'], close=df['close'], talib=False)

    # Verifica o último candle
    is_engulfing_bullish = engulfing is not None and not engulfing.empty and engulfing.iloc[-1] == 100
    is_hammer = hammer is not None and not hammer.empty and hammer.iloc[-1] == 100
    
    is_engulfing_bearish = engulfing is not None and not engulfing.empty and engulfing.iloc[-1] == -100
    is_shooting_star = shooting_star is not None and not shooting_star.empty and shooting_star.iloc[-1] == -100

    if is_engulfing_bullish or is_hammer:
        return 'call'
    
    if is_engulfing_bearish or is_shooting_star:
        return 'put'
        
    return None

def check_price_near_sr(last_candle: Candle, zones: Dict, tolerance=0.0005) -> Optional[str]:
    """Verifica se o preço está próximo a uma zona de S/R."""
    if last_candle is None or last_candle.close is None:
        return None
        
    price = last_candle.close
    for r in zones.get('resistance', []):
        if abs(price - r) / r < tolerance:
            return 'put'
    for s in zones.get('support', []):
        if abs(price - s) / s < tolerance:
            return 'call'
    return None
