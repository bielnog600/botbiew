# analysis/technical_indicators.py

# IMPORTAÇÕES CORRETAS
import pandas as pd
import pandas_ta as ta
from typing import List, Dict, Optional

# A classe Candle pode ser mantida, pois ajuda a estruturar os dados
class Candle:
    def __init__(self, data):
        # Usamos .get() para evitar erros se uma chave não existir
        self.open = data.get('open')
        self.max = data.get('max')
        self.min = data.get('min')
        self.close = data.get('close')
        self.volume = data.get('volume')

# --- Funções dos Indicadores com Lógica Profissional ---

def _convert_candles_to_dataframe(candles: List[Candle]) -> pd.DataFrame:
    """Função auxiliar para converter a lista de candles em um DataFrame do Pandas."""
    if not candles:
        return pd.DataFrame()
    
    df = pd.DataFrame([vars(c) for c in candles])
    # Renomear colunas para o padrão do pandas_ta (high, low, open, close)
    df.rename(columns={'max': 'high', 'min': 'low'}, inplace=True)
    # Garante que os tipos de dados são numéricos para os cálculos
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    return df

def calculate_ema(candles: List[Candle], period: int) -> Optional[float]:
    """
    CORRIGIDO: Calcula a Média Móvel Exponencial (EMA) usando pandas_ta.
    """
    if len(candles) < period:
        return None
    df = _convert_candles_to_dataframe(candles)
    ema_series = ta.ema(df['close'], length=period)
    if ema_series is None or ema_series.empty:
        return None
    return ema_series.iloc[-1] # Retorna o último valor da EMA

def calculate_atr(candles: List[Candle], period: int) -> Optional[float]:
    """
    CORRIGIDO: Calcula o Average True Range (ATR) usando pandas_ta.
    """
    if len(candles) < period:
        return None
    df = _convert_candles_to_dataframe(candles)
    atr_series = ta.atr(df['high'], df['low'], df['close'], length=period)
    if atr_series is None or atr_series.empty:
        return None
    return atr_series.iloc[-1] # Retorna o último valor do ATR

def check_rsi_condition(candles: List[Candle], overbought=70, oversold=30, period=14) -> Optional[str]:
    """
    CORRIGIDO: Verifica se o RSI está em sobrecompra ou sobrevenda usando pandas_ta.
    """
    if len(candles) < period:
        return None
    df = _convert_candles_to_dataframe(candles)
    rsi_series = ta.rsi(df['close'], length=period)
    if rsi_series is None or rsi_series.empty:
        return None
    
    rsi_value = rsi_series.iloc[-1]
    if rsi_value > overbought:
        return 'put' # Sobrecomprado, sinal de possível reversão para baixo
    if rsi_value < oversold:
        return 'call' # Sobrevendido, sinal de possível reversão para alta
    return None

def check_candlestick_pattern(candles: List[Candle]) -> Optional[str]:
    """
    CORRIGIDO: Identifica padrões de candlestick de reversão usando pandas_ta.
    Esta versão é precisa e confiável.
    """
    if len(candles) < 20:
        return None

    df = _convert_candles_to_dataframe(candles)
    
    # Pedir para o pandas_ta encontrar TODOS os padrões conhecidos
    df.ta.cdl_pattern(name="all", append=True)
    
    last_candle_patterns = df.iloc[-1]

    # Padrões de Reversão de ALTA (Bullish) - retornam 'call'
    if (last_candle_patterns.get('CDLENGULFING', 0) == 100 or
        last_candle_patterns.get('CDLHAMMER', 0) == 100 or
        last_candle_patterns.get('CDLMORNINGSTAR', 0) == 100 or
        last_candle_patterns.get('CDLPIERCING', 0) == 100):
        return 'call'

    # Padrões de Reversão de BAIXA (Bearish) - retornam 'put'
    if (last_candle_patterns.get('CDLENGULFING', 0) == -100 or
        last_candle_patterns.get('CDLSHOOTINGSTAR', 0) == -100 or
        last_candle_patterns.get('CDLEVENINGSTAR', 0) == -100 or
        last_candle_patterns.get('CDLDARKCLOUDCOVER', 0) == -100):
        return 'put'
        
    return None

def check_price_near_sr(last_candle: Candle, zones: Dict, tolerance=0.0005) -> Optional[str]:
    """
    Esta função já era baseada em lógica de preço, então pode ser mantida.
    """
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
