import pandas as pd
import pandas_ta as ta
from typing import Optional, List, Dict

# ===============================================
# FUNÇÕES DE ANÁLISE DE SUPORTE E RESISTÊNCIA (S/R)
# ===============================================

def get_m15_sr_zones(candles: List[Dict], window: int = 5) -> tuple:
    """Calcula zonas de S/R com base em velas de M15."""
    if not candles: return [], []
    df = pd.DataFrame(candles)
    # Assegura que as colunas 'max' e 'min' existem
    if 'max' not in df.columns or 'min' not in df.columns:
        return [], []
        
    df['is_resistance'] = (df['max'] >= df['max'].rolling(window, center=True, min_periods=1).max()).astype(int)
    df['is_support'] = (df['min'] <= df['min'].rolling(window, center=True, min_periods=1).min()).astype(int)
    resistances = df[df['is_resistance'] == 1]['max'].unique().tolist()
    supports = df[df['is_support'] == 1]['min'].unique().tolist()
    return sorted(resistances, reverse=True), sorted(supports)

# ===============================================
# FUNÇÕES DE INDICADORES TÉCNICOS
# ===============================================

def calculate_atr(candles: List[Dict], period: int = 14) -> Optional[float]:
    """Calcula o Average True Range (ATR)."""
    if len(candles) < period: return None
    df = pd.DataFrame(candles)
    df.rename(columns={'max': 'high', 'min': 'low'}, inplace=True)
    if not all(x in df.columns for x in ['high', 'low', 'close']): return None
    atr_series = ta.atr(df['high'], df['low'], df['close'], length=period)
    return atr_series.iloc[-1] if not atr_series.empty else None

def check_rsi_condition(candles: List[Dict], period: int = 14, overbought: int = 70, oversold: int = 30) -> Optional[str]:
    """Verifica se o RSI está em sobrecompra ou sobrevenda."""
    if len(candles) < period: return None
    df = pd.DataFrame(candles)
    if 'close' not in df.columns: return None
    rsi_series = ta.rsi(df['close'], length=period)
    if rsi_series.empty: return None
    last_rsi = rsi_series.iloc[-1]
    if last_rsi >= overbought: return 'put'
    if last_rsi <= oversold: return 'call'
    return None

def check_ma_trend(candles: List[Dict], fast_period: int = 9, slow_period: int = 21) -> Optional[str]:
    """Verifica a tendência usando duas médias móveis (rápida e lenta)."""
    if len(candles) < slow_period: return None
    df = pd.DataFrame(candles)
    if 'close' not in df.columns: return None
    df['fast_ma'] = ta.sma(df['close'], length=fast_period)
    df['slow_ma'] = ta.sma(df['close'], length=slow_period)
    if df['fast_ma'].empty or df['slow_ma'].empty or df['fast_ma'].iloc[-1] is None or df['slow_ma'].iloc[-1] is None: return None
    last_fast = df['fast_ma'].iloc[-1]
    last_slow = df['slow_ma'].iloc[-1]
    if last_fast > last_slow: return 'call' # Tendência de alta
    if last_fast < last_slow: return 'put'  # Tendência de baixa
    return None

# ===============================================
# FUNÇÕES DE VALIDAÇÃO DE VELAS E PADRÕES
# ===============================================

def check_candlestick_pattern(candles: List[Dict]) -> Optional[str]:
    """Verifica padrões de vela de reversão (Engolfo)."""
    if len(candles) < 2: return None
    df = pd.DataFrame(candles)
    
    # Engolfo de Alta (Bullish Engulfing)
    if (df['close'].iloc[-2] < df['open'].iloc[-2] and 
        df['close'].iloc[-1] > df['open'].iloc[-1] and 
        df['close'].iloc[-1] >= df['open'].iloc[-2] and 
        df['open'].iloc[-1] <= df['close'].iloc[-2]):
        return 'call'
        
    # Engolfo de Baixa (Bearish Engulfing)
    if (df['close'].iloc[-2] > df['open'].iloc[-2] and 
        df['close'].iloc[-1] < df['open'].iloc[-1] and 
        df['close'].iloc[-1] <= df['open'].iloc[-2] and 
        df['open'].iloc[-1] >= df['close'].iloc[-2]):
        return 'put'
        
    return None

def validate_reversal_candle(candle: dict, direction: str) -> bool:
    """Valida a qualidade da vela de sinal."""
    is_call = direction == 'call'
    open_price, high, low, close = candle['open'], candle['max'], candle['min'], candle['close']
    
    if is_call and close <= open_price: return False
    if not is_call and close >= open_price: return False

    body_size = abs(close - open_price)
    total_range = high - low
    if total_range == 0: return False
    if (body_size / total_range) < 0.25: return False

    upper_wick = high - max(open_price, close)
    lower_wick = min(open_price, close) - low
    if is_call and (upper_wick / total_range) > 0.4: return False
    if not is_call and (lower_wick / total_range) > 0.4: return False

    return True

# ===============================================
# FUNÇÕES DE ESTRATÉGIA COMPLETAS
# ===============================================

def strategy_reversal_pattern(candles: List[Dict]) -> Optional[str]:
    """
    Estratégia baseada em padrões de engolfo que ocorrem em zonas de S/R,
    com confirmação de tendência. (VERSÃO MELHORADA)
    """
    if len(candles) < 50: return None

    # 1. Confirmação de Tendência
    trend = check_ma_trend(candles)
    if not trend: return None

    # 2. Confirmação de Padrão de Engolfo
    pattern = check_candlestick_pattern(candles)
    if not pattern: return None

    # 3. O padrão deve estar alinhado com a tendência
    if pattern != trend:
        return None

    # 4. Confirmação de Localização (S/R)
    resistances, supports = get_m15_sr_zones(candles[-100:])
    engulfing_candle = candles[-1]

    if pattern == 'call': # Engolfo de Alta
        for sup in supports:
            # A vela de engolfo deve ter tocado o suporte
            if engulfing_candle['min'] <= sup:
                return 'call' # SINAL VÁLIDO

    if pattern == 'put': # Engolfo de Baixa
        for res in resistances:
            # A vela de engolfo deve ter tocado a resistência
            if engulfing_candle['max'] >= res:
                return 'put' # SINAL VÁLIDO

    # Se o padrão não ocorreu numa zona de S/R, o sinal é inválido.
    return None

def strategy_trend_flow(candles: List[Dict]) -> Optional[str]:
    """Estratégia de continuação de tendência (fluxo)."""
    if len(candles) < 3: return None
    trend = check_ma_trend(candles)
    if not trend: return None
    
    last_three_candles = candles[-3:]
    
    if trend == 'call' and all(c['close'] > c['open'] for c in last_three_candles):
        return 'call'
    if trend == 'put' and all(c['close'] < c['open'] for c in last_three_candles):
        return 'put'
    return None

def strategy_mql_pullback(candles: List[Dict]) -> Optional[str]:
    """Estratégia de pullback em zonas de S/R a favor da tendência."""
    trend = check_ma_trend(candles)
    if not trend: return None
    
    resistances, supports = get_m15_sr_zones(candles[-100:])
    last_candle = candles[-1]
    
    if trend == 'call':
        for sup in supports:
            if last_candle['min'] <= sup and last_candle['close'] > sup:
                return 'call'
    
    if trend == 'put':
        for res in resistances:
            if last_candle['max'] >= res and last_candle['close'] < res:
                return 'put'
    return None
