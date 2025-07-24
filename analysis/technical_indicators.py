import pandas as pd
import pandas_ta as ta
from typing import List, Dict, Optional, Tuple

def get_m15_sr_zones(candles_m15: List[Dict]) -> Tuple[List[float], List[float]]:
    """
    Calcula zonas de suporte e resistência com base em velas de M15.
    Utiliza fractais para identificar os pontos de S/R.
    """
    if not candles_m15 or len(candles_m15) < 5:
        return [], []
    
    df = pd.DataFrame(candles_m15)
    
    if 'max' in df.columns:
        df.rename(columns={'max': 'high'}, inplace=True)
    if 'min' in df.columns:
        df.rename(columns={'min': 'low'}, inplace=True)

    required_columns = ['high', 'low']
    if not all(col in df.columns for col in required_columns):
        return [], []

    resistances = []
    for i in range(2, len(df) - 2):
        is_resistance = df['high'].iloc[i] > df['high'].iloc[i-1] and \
                        df['high'].iloc[i] > df['high'].iloc[i-2] and \
                        df['high'].iloc[i] > df['high'].iloc[i+1] and \
                        df['high'].iloc[i] > df['high'].iloc[i+2]
        if is_resistance:
            resistances.append(df['high'].iloc[i])

    supports = []
    for i in range(2, len(df) - 2):
        is_support = df['low'].iloc[i] < df['low'].iloc[i-1] and \
                     df['low'].iloc[i] < df['low'].iloc[i-2] and \
                     df['low'].iloc[i] < df['low'].iloc[i+1] and \
                     df['low'].iloc[i] < df['low'].iloc[i+2]
        if is_support:
            supports.append(df['low'].iloc[i])
            
    return sorted(resistances, reverse=True)[:5], sorted(supports, reverse=True)[:5]

def calculate_atr(candles: List[Dict], period: int = 14) -> Optional[float]:
    """Calcula o Average True Range (ATR) para medir a volatilidade."""
    if not candles or len(candles) < period:
        return None
    
    df = pd.DataFrame(candles)
    if 'max' in df.columns: df.rename(columns={'max': 'high'}, inplace=True)
    if 'min' in df.columns: df.rename(columns={'min': 'low'}, inplace=True)

    required_columns = ['high', 'low', 'close']
    if not all(col in df.columns for col in required_columns):
        return None
        
    df.ta.atr(length=period, append=True)
    atr_column_name = f'ATRr_{period}'
    if atr_column_name in df.columns:
        return df[atr_column_name].iloc[-1]
    return None

def check_ma_trend(candles: List[Dict], fast_period: int = 9, slow_period: int = 21) -> Optional[str]:
    """
    Verifica a tendência principal usando o cruzamento de duas médias móveis.
    Retorna 'uptrend', 'downtrend' ou None se a tendência for indefinida.
    """
    if not candles or len(candles) < slow_period:
        return None
        
    df = pd.DataFrame(candles)
    required_columns = ['close']
    if not all(col in df.columns for col in required_columns): return None

    # Calcula as duas médias móveis
    df.ta.sma(length=fast_period, append=True)
    df.ta.sma(length=slow_period, append=True)
    
    fast_ma_col = f'SMA_{fast_period}'
    slow_ma_col = f'SMA_{slow_period}'

    if fast_ma_col in df.columns and slow_ma_col in df.columns:
        last_fast_ma = df[fast_ma_col].iloc[-1]
        last_slow_ma = df[slow_ma_col].iloc[-1]

        if last_fast_ma > last_slow_ma:
            return 'uptrend'  # Tendência de alta
        elif last_fast_ma < last_slow_ma:
            return 'downtrend' # Tendência de baixa
            
    return None # Tendência indefinida ou erro

def check_price_near_sr(candle: dict, zones: Dict[str, List[float]], proximity_pips: int = 5) -> Optional[str]:
    """Verifica se o preço de um candle está perto de uma zona de Suporte ou Resistência."""
    try:
        price = candle['close']
        proximity = proximity_pips * 0.00001

        for r_zone in zones.get('resistance', []):
            if r_zone >= price >= (r_zone - proximity):
                return 'put'

        for s_zone in zones.get('support', []):
            if s_zone <= price <= (s_zone + proximity):
                return 'call'
    except KeyError:
        return None
    return None

def check_candlestick_pattern(candles: List[Dict]) -> Optional[str]:
    """Identifica padrões de candlestick de reversão usando pandas_ta."""
    if len(candles) < 2:
        return None
    
    df = pd.DataFrame(candles)
    if 'max' in df.columns: df.rename(columns={'max': 'high'}, inplace=True)
    if 'min' in df.columns: df.rename(columns={'min': 'low'}, inplace=True)

    required_columns = ['open', 'high', 'low', 'close']
    if not all(col in df.columns for col in required_columns): return None

    df.ta.cdl_pattern(name="all", append=True)
    
    last_row = df.iloc[-1]
    
    bullish_signals = [col for col in df.columns if col.startswith('CDL_') and last_row[col] > 0]
    if bullish_signals:
        return 'call'

    bearish_signals = [col for col in df.columns if col.startswith('CDL_') and last_row[col] < 0]
    if bearish_signals:
        return 'put'

    return None

def check_rsi_condition(candles: List[Dict], period: int = 14, overbought: int = 70, oversold: int = 30) -> Optional[str]:
    """Verifica a condição do RSI (sobrecompra/sobrevenda)."""
    if len(candles) < period:
        return None
        
    df = pd.DataFrame(candles)
    required_columns = ['close']
    if not all(col in df.columns for col in required_columns): return None
        
    df.ta.rsi(length=period, append=True)
    rsi_col = f'RSI_{period}'
    
    if rsi_col in df.columns:
        last_rsi = df[rsi_col].iloc[-1]
        if last_rsi >= overbought:
            return 'put'
        if last_rsi <= oversold:
            return 'call'
            
    return None

def validate_reversal_candle(candle: dict, direction: str) -> bool:
    """Valida a qualidade da vela de sinal para uma operação de reversão."""
    try:
        o, c, h, l = candle['open'], candle['close'], candle['max'], candle['min']

        is_bullish = c > o
        is_bearish = c < o

        if direction == 'call' and not is_bullish:
            return False
        
        if direction == 'put' and not is_bearish:
            return False

        total_range = h - l
        body_size = abs(o - c)

        if total_range == 0:
            return False

        min_body_ratio = 0.30 
        if (body_size / total_range) < min_body_ratio:
            return False
            
        return True

    except (KeyError, ZeroDivisionError):
        return False
