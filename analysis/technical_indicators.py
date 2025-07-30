import pandas as pd
import pandas_ta as ta
from typing import Optional, List, Dict

# ===============================================
# FUNÇÕES DE ANÁLISE DE SUPORTE E RESISTÊNCIA (S/R)
# ===============================================

def get_m15_sr_zones(candles: List[Dict], window: int = 5) -> tuple:
    if not candles: return [], []
    df = pd.DataFrame(candles)
    if 'max' not in df.columns or 'min' not in df.columns: return [], []
    df['is_resistance'] = (df['max'] >= df['max'].rolling(window, center=True, min_periods=1).max()).astype(int)
    df['is_support'] = (df['min'] <= df['min'].rolling(window, center=True, min_periods=1).min()).astype(int)
    resistances = df[df['is_resistance'] == 1]['max'].unique().tolist()
    supports = df[df['is_support'] == 1]['min'].unique().tolist()
    return sorted(resistances, reverse=True), sorted(supports)

# ===============================================
# FUNÇÕES DE INDICADORES TÉCNICOS
# ===============================================

def calculate_atr(candles: List[Dict], period: int = 14) -> Optional[float]:
    if len(candles) < period: return None
    df = pd.DataFrame(candles)
    df.rename(columns={'max': 'high', 'min': 'low'}, inplace=True)
    if not all(x in df.columns for x in ['high', 'low', 'close']): return None
    atr_series = ta.atr(df['high'], df['low'], df['close'], length=period)
    return atr_series.iloc[-1] if not atr_series.empty else None

def check_ma_trend(candles: List[Dict], fast_period: int = 9, slow_period: int = 21) -> Optional[str]:
    if len(candles) < slow_period: return None
    df = pd.DataFrame(candles)
    if 'close' not in df.columns: return None
    df['fast_ma'] = ta.sma(df['close'], length=fast_period)
    df['slow_ma'] = ta.sma(df['close'], length=slow_period)
    if df['fast_ma'].empty or df['slow_ma'].empty or pd.isna(df['fast_ma'].iloc[-1]) or pd.isna(df['slow_ma'].iloc[-1]): return None
    last_fast = df['fast_ma'].iloc[-1]
    last_slow = df['slow_ma'].iloc[-1]
    if last_fast > last_slow: return 'call'
    if last_fast < last_slow: return 'put'
    return None

# ===============================================
# FUNÇÕES DE VALIDAÇÃO E PADRÕES
# ===============================================

def check_candlestick_pattern(candles: List[Dict]) -> Optional[str]:
    if len(candles) < 2: return None
    df = pd.DataFrame(candles)
    if (df['close'].iloc[-2] < df['open'].iloc[-2] and 
        df['close'].iloc[-1] > df['open'].iloc[-1] and 
        df['close'].iloc[-1] >= df['open'].iloc[-2] and 
        df['open'].iloc[-1] <= df['close'].iloc[-2]):
        return 'call'
    if (df['close'].iloc[-2] > df['open'].iloc[-2] and 
        df['close'].iloc[-1] < df['open'].iloc[-1] and 
        df['close'].iloc[-1] <= df['open'].iloc[-2] and 
        df['open'].iloc[-1] >= df['close'].iloc[-2]):
        return 'put'
    return None

def validate_reversal_candle(candle: dict, direction: str) -> bool:
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

def detect_double_top_bottom(candles: List[Dict]) -> Optional[str]:
    if len(candles) < 20: return None
    df = pd.DataFrame(candles)
    peaks = df[df['max'] == df['max'].rolling(5, center=True).max()]
    troughs = df[df['min'] == df['min'].rolling(5, center=True).min()]
    if len(peaks) >= 2:
        last_peak, prev_peak = peaks.iloc[-1], peaks.iloc[-2]
        if abs(last_peak['max'] - prev_peak['max']) / last_peak['max'] < 0.001:
            valley = troughs[troughs.index > prev_peak.name]
            if not valley.empty and candles[-1]['close'] < valley.iloc[0]['min']: return 'put'
    if len(troughs) >= 2:
        last_trough, prev_trough = troughs.iloc[-1], troughs.iloc[-2]
        if abs(last_trough['min'] - prev_trough['min']) / last_trough['min'] < 0.001:
            peak_between = peaks[peaks.index > prev_trough.name]
            if not peak_between.empty and candles[-1]['close'] > peak_between.iloc[0]['max']: return 'call'
    return None

# ===============================================
# ESTRATÉGIAS COMPLETAS
# ===============================================

def strategy_reversal_pattern(candles: List[Dict]) -> Optional[str]:
    if len(candles) < 50: return None
    trend = check_ma_trend(candles)
    if not trend: return None
    pattern = check_candlestick_pattern(candles)
    if not pattern or pattern != trend: return None
    resistances, supports = get_m15_sr_zones(candles[-100:])
    engulfing_candle = candles[-1]
    if pattern == 'call' and any(engulfing_candle['min'] <= sup for sup in supports): return 'call'
    if pattern == 'put' and any(engulfing_candle['max'] >= res for res in resistances): return 'put'
    return None

def strategy_trend_flow(candles: List[Dict]) -> Optional[str]:
    if len(candles) < 3: return None
    trend = check_ma_trend(candles)
    if not trend: return None
    last_three_candles = candles[-3:]
    if trend == 'call' and all(c['close'] > c['open'] for c in last_three_candles): return 'call'
    if trend == 'put' and all(c['close'] < c['open'] for c in last_three_candles): return 'put'
    return None

def strategy_mql_pullback(candles: List[Dict]) -> Optional[str]:
    trend = check_ma_trend(candles)
    if not trend: return None
    resistances, supports = get_m15_sr_zones(candles[-100:])
    last_candle = candles[-1]
    if trend == 'call' and any(last_candle['min'] <= sup and last_candle['close'] > sup for sup in supports): return 'call'
    if trend == 'put' and any(last_candle['max'] >= res and last_candle['close'] < res for res in resistances): return 'put'
    return None

def strategy_exhaustion_reversal(candles: List[Dict]) -> Optional[str]:
    return detect_double_top_bottom(candles)

# --- NOVAS ESTRATÉGIAS ---

def strategy_bollinger_bands(candles: List[Dict], period: int = 20, std_dev: int = 2) -> Optional[str]:
    """
    Estratégia de reversão nas Bandas de Bollinger, a favor da tendência.
    """
    if len(candles) < period: return None
    
    trend = check_ma_trend(candles)
    if not trend: return None

    df = pd.DataFrame(candles)
    df.ta.bbands(length=period, std=std_dev, append=True)
    
    lower_band_col = f'BBL_{period}_{float(std_dev)}'
    upper_band_col = f'BBU_{period}_{float(std_dev)}'

    if lower_band_col not in df.columns or upper_band_col not in df.columns: return None

    last_candle = candles[-1]
    
    # Sinal de COMPRA: Toca na banda inferior durante uma tendência de ALTA
    if trend == 'call' and last_candle['min'] <= df[lower_band_col].iloc[-1]:
        return 'call'
        
    # Sinal de VENDA: Toca na banda superior durante uma tendência de BAIXA
    if trend == 'put' and last_candle['max'] >= df[upper_band_col].iloc[-1]:
        return 'put'
        
    return None

def strategy_macd_crossover(candles: List[Dict], fast: int = 12, slow: int = 26, signal: int = 9) -> Optional[str]:
    """
    Estratégia de cruzamento do MACD, a favor da tendência.
    """
    if len(candles) < slow: return None
    
    trend = check_ma_trend(candles)
    if not trend: return None
    
    df = pd.DataFrame(candles)
    df.ta.macd(fast=fast, slow=slow, signal=signal, append=True)
    
    macd_line_col = f'MACD_{fast}_{slow}_{signal}'
    signal_line_col = f'MACDs_{fast}_{slow}_{signal}'
    
    if macd_line_col not in df.columns or signal_line_col not in df.columns: return None
    
    # Cruzamento de ALTA (MACD cruza para cima da linha de sinal)
    if trend == 'call':
        if df[macd_line_col].iloc[-2] < df[signal_line_col].iloc[-2] and \
           df[macd_line_col].iloc[-1] > df[signal_line_col].iloc[-1]:
            return 'call'
            
    # Cruzamento de BAIXA (MACD cruza para baixo da linha de sinal)
    if trend == 'put':
        if df[macd_line_col].iloc[-2] > df[signal_line_col].iloc[-2] and \
           df[macd_line_col].iloc[-1] < df[signal_line_col].iloc[-1]:
            return 'put'
            
    return None
