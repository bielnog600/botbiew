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

# CORRIGIDO: Esta função agora usa a nossa própria lógica para identificar os padrões,
# removendo completamente a dependência da pandas-ta para esta tarefa.
def check_candlestick_pattern(candles: List[Candle]) -> Optional[str]:
    """Identifica padrões de vela de reversão com lógica interna."""
    if len(candles) < 2:
        return None

    prev = candles[-2]
    curr = candles[-1]

    # Lógica para Engolfo de Alta (Bullish Engulfing)
    # 1. Vela anterior é de baixa.
    # 2. Vela atual é de alta.
    # 3. Corpo da vela atual "engole" o corpo da vela anterior.
    if (prev.close < prev.open and curr.close > curr.open and
        curr.open <= prev.close and curr.close >= prev.open):
        return 'call'

    # Lógica para Engolfo de Baixa (Bearish Engulfing)
    # 1. Vela anterior é de alta.
    # 2. Vela atual é de baixa.
    # 3. Corpo da vela atual "engole" o corpo da vela anterior.
    if (prev.close > prev.open and curr.close < curr.open and
        curr.open >= prev.close and curr.close <= prev.open):
        return 'put'

    # Lógica para Martelo (Hammer) - sinal de alta
    body_size = abs(curr.close - curr.open)
    lower_wick = min(curr.open, curr.close) - curr.min
    upper_wick = curr.max - max(curr.open, curr.close)
    if body_size > 0 and lower_wick >= 2 * body_size and upper_wick < body_size:
        return 'call'

    # Lógica para Estrela Cadente (Shooting Star) - sinal de baixa
    if body_size > 0 and upper_wick >= 2 * body_size and lower_wick < body_size:
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
