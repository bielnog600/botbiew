import pandas as pd
import pandas_ta as ta
from typing import Optional

# ===============================================
# FUNÇÕES DE ANÁLISE DE SUPORTE E RESISTÊNCIA (S/R)
# ===============================================

def get_m15_sr_zones(candles: list, window: int = 5) -> tuple:
    """Calcula zonas de S/R com base em velas de M15."""
    if not candles: return [], []
    df = pd.DataFrame(candles)
    df['is_resistance'] = (df['max'] >= df['max'].rolling(window, center=True).max()).astype(int)
    df['is_support'] = (df['min'] <= df['min'].rolling(window, center=True).min()).astype(int)
    resistances = df[df['is_resistance'] == 1]['max'].unique().tolist()
    supports = df[df['is_support'] == 1]['min'].unique().tolist()
    return sorted(resistances, reverse=True), sorted(supports)

def check_price_near_sr(candle: dict, zones: dict, proximity_factor: float = 0.0001) -> str:
    """Verifica se o preço de fecho está próximo de uma zona de S/R."""
    close_price = candle['close']
    for res_level in zones.get('resistance', []):
        if abs(close_price - res_level) <= proximity_factor:
            return 'put'
    for sup_level in zones.get('support', []):
        if abs(close_price - sup_level) <= proximity_factor:
            return 'call'
    return None

# ===============================================
# FUNÇÕES DE INDICADORES TÉCNICOS
# ===============================================

def calculate_atr(candles: list, period: int = 14) -> Optional[float]:
    """Calcula o Average True Range (ATR)."""
    if len(candles) < period: return None
    df = pd.DataFrame(candles)
    df.rename(columns={'max': 'high', 'min': 'low'}, inplace=True)
    atr_series = ta.atr(df['high'], df['low'], df['close'], length=period)
    return atr_series.iloc[-1] if not atr_series.empty else None

def check_rsi_condition(candles: list, period: int = 14, overbought: int = 70, oversold: int = 30) -> Optional[str]:
    """Verifica se o RSI está em sobrecompra ou sobrevenda."""
    if len(candles) < period: return None
    df = pd.DataFrame(candles)
    rsi_series = ta.rsi(df['close'], length=period)
    if rsi_series.empty: return None
    last_rsi = rsi_series.iloc[-1]
    if last_rsi >= overbought: return 'put'
    if last_rsi <= oversold: return 'call'
    return None

def check_ma_trend(candles: list, fast_period: int = 9, slow_period: int = 21) -> Optional[str]:
    """Verifica a tendência usando duas médias móveis (rápida e lenta)."""
    if len(candles) < slow_period: return None
    df = pd.DataFrame(candles)
    df['fast_ma'] = ta.sma(df['close'], length=fast_period)
    df['slow_ma'] = ta.sma(df['close'], length=slow_period)
    if df['fast_ma'].empty or df['slow_ma'].empty: return None
    last_fast = df['fast_ma'].iloc[-1]
    last_slow = df['slow_ma'].iloc[-1]
    if last_fast > last_slow: return 'call' # Tendência de alta
    if last_fast < last_slow: return 'put'  # Tendência de baixa
    return None

# ===============================================
# FUNÇÕES DE VALIDAÇÃO DE VELAS E PADRÕES
# ===============================================

def check_candlestick_pattern(candles: list) -> Optional[str]:
    """Verifica padrões de vela de reversão."""
    if len(candles) < 2: return None
    df = pd.DataFrame(candles)
    # Engolfo de Alta (Bullish Engulfing)
    if (df['close'].iloc[-2] < df['open'].iloc[-2] and 
        df['close'].iloc[-1] > df['open'].iloc[-1] and 
        df['close'].iloc[-1] > df['open'].iloc[-2] and 
        df['open'].iloc[-1] < df['close'].iloc[-2]):
        return 'call'
    # Engolfo de Baixa (Bearish Engulfing)
    if (df['close'].iloc[-2] > df['open'].iloc[-2] and 
        df['close'].iloc[-1] < df['open'].iloc[-1] and 
        df['close'].iloc[-1] < df['open'].iloc[-2] and 
        df['open'].iloc[-1] > df['close'].iloc[-2]):
        return 'put'
    return None

def validate_reversal_candle(candle: dict, direction: str) -> bool:
    """
    Valida a qualidade da vela de sinal.
    Uma boa vela de reversão tem cor a favor, corpo decente e pouco pavio contrário.
    """
    is_call = direction == 'call'
    open_price, high, low, close = candle['open'], candle['max'], candle['min'], candle['close']
    
    # 1. Cor da vela deve ser a favor da operação
    if is_call and close <= open_price: return False # Para CALL, a vela deve ser de alta (verde)
    if not is_call and close >= open_price: return False # Para PUT, a vela deve ser de baixa (vermelha)

    # 2. Corpo da vela não pode ser minúsculo (evitar Dojis)
    body_size = abs(close - open_price)
    total_range = high - low
    if total_range == 0: return False
    if (body_size / total_range) < 0.25: # Corpo deve ser pelo menos 25% do tamanho total
        return False

    # 3. Pavio contrário deve ser pequeno
    upper_wick = high - max(open_price, close)
    lower_wick = min(open_price, close) - low
    if is_call and (upper_wick / total_range) > 0.4: return False # Para CALL, não pode ter muito pavio em cima
    if not is_call and (lower_wick / total_range) > 0.4: return False # Para PUT, não pode ter muito pavio em baixo

    return True

# ===============================================
# NOVAS FUNÇÕES DE ESTRATÉGIA
# ===============================================

def strategy_reversal_pattern(candles: list) -> Optional[str]:
    """Estratégia baseada em padrões de reversão com confirmação de tendência."""
    trend = check_ma_trend(candles)
    if not trend: return None
    
    pattern = check_candlestick_pattern(candles)
    if pattern == 'call' and trend == 'call':
        return 'call'
    if pattern == 'put' and trend == 'put':
        return 'put'
    return None

def strategy_trend_flow(candles: list) -> Optional[str]:
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

def strategy_mql_pullback(candles: list) -> Optional[str]:
    """Estratégia de pullback em zonas de S/R a favor da tendência."""
    trend = check_ma_trend(candles)
    if not trend: return None
    
    # Usa as últimas 100 velas para S/R
    resistances, supports = get_m15_sr_zones(candles[-100:])
    last_candle = candles[-1]
    
    if trend == 'call':
        for sup in supports:
            # Se a vela tocou no suporte e fechou acima, é um sinal de compra
            if last_candle['min'] <= sup and last_candle['close'] > sup:
                return 'call'
    
    if trend == 'put':
        for res in resistances:
            # Se a vela tocou na resistência e fechou abaixo, é um sinal de venda
            if last_candle['max'] >= res and last_candle['close'] < res:
                return 'put'
    return None
