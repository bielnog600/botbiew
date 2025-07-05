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

# ATUALIZADO: Função com um vocabulário de padrões de vela muito maior.
def check_candlestick_pattern(candles: List[Candle]) -> Optional[str]:
    """Identifica um conjunto expandido de padrões de vela de reversão com lógica interna."""
    if len(candles) < 3: # Alguns padrões precisam de 3 velas
        return None

    c1 = candles[-3] # Vela -3
    c2 = candles[-2] # Vela anterior
    c3 = candles[-1] # Vela atual (de entrada)

    # Lógica para Engolfo de Alta (Bullish Engulfing)
    if c2.close < c2.open and c3.close > c3.open and c3.open <= c2.close and c3.close >= c2.open:
        return 'call'

    # Lógica para Engolfo de Baixa (Bearish Engulfing)
    if c2.close > c2.open and c3.close < c3.open and c3.open >= c2.close and c3.close <= c2.open:
        return 'put'

    # Lógica para Martelo (Hammer) - sinal de alta
    body = abs(c3.close - c3.open)
    if body > 0:
        lower_wick = min(c3.open, c3.close) - c3.min
        upper_wick = c3.max - max(c3.open, c3.close)
        if lower_wick >= 2 * body and upper_wick < body:
            return 'call'

    # Lógica para Estrela Cadente (Shooting Star) - sinal de baixa
    if body > 0:
        lower_wick = min(c3.open, c3.close) - c3.min
        upper_wick = c3.max - max(c3.open, c3.close)
        if upper_wick >= 2 * body and lower_wick < body:
            return 'put'
            
    # Lógica para Doji - sinal de indecisão (pode ser usado como confirmação)
    total_range = c3.max - c3.min
    if total_range > 0 and body / total_range < 0.1:
        # Se a vela anterior foi de baixa, um Doji pode ser reversão para alta
        if c2.close < c2.open:
            return 'call'
        # Se a vela anterior foi de alta, um Doji pode ser reversão para baixa
        if c2.close > c2.open:
            return 'put'

    # Lógica para Estrela da Manhã (Morning Star) - sinal de alta
    if (c1.close < c1.open and abs(c1.close - c1.open) > 0 and # 1. Vela grande de baixa
        c2.close < c1.close and # 2. Gap de baixa para a segunda vela (doji ou pequena)
        c3.close > c3.open and c3.open > c2.close and c3.close > (c1.open + c1.close) / 2): # 3. Vela de alta que recupera mais de metade da primeira
        return 'call'

    # Lógica para Estrela da Noite (Evening Star) - sinal de baixa
    if (c1.close > c1.open and abs(c1.close - c1.open) > 0 and # 1. Vela grande de alta
        c2.close > c1.close and # 2. Gap de alta para a segunda vela (doji ou pequena)
        c3.close < c3.open and c3.open < c2.close and c3.close < (c1.open + c1.close) / 2): # 3. Vela de baixa que recupera mais de metade da primeira
        return 'put'

    # Lógica para Piercing Line - sinal de alta
    if (c2.close < c2.open and # 1. Vela anterior de baixa
        c3.close > c3.open and # 2. Vela atual de alta
        c3.open < c2.close and # 3. Abre abaixo do fecho anterior
        c3.close > (c2.open + c2.close) / 2): # 4. Fecha acima de 50% da vela anterior
        return 'call'

    # Lógica para Dark Cloud Cover - sinal de baixa
    if (c2.close > c2.open and # 1. Vela anterior de alta
        c3.close < c3.open and # 2. Vela atual de baixa
        c3.open > c2.close and # 3. Abre acima do fecho anterior
        c3.close < (c2.open + c2.close) / 2): # 4. Fecha abaixo de 50% da vela anterior
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
