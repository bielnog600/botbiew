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
    """
    Calcula o Average True Range (ATR) para medir a volatilidade.
    Esta função foi re-adicionada para corrigir o erro.
    """
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
# FUNÇÕES DE VALIDAÇÃO E PADRÕES AVANÇADOS
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

def find_recent_peaks_and_troughs(candles: List[Dict], window: int = 5) -> tuple:
    """Encontra os picos (máximas) e vales (mínimas) recentes no preço."""
    df = pd.DataFrame(candles)
    peaks = df[df['max'] >= df['max'].rolling(window, center=True, min_periods=1).max()]
    troughs = df[df['min'] <= df['min'].rolling(window, center=True, min_periods=1).min()]
    return peaks, troughs

def detect_double_top_bottom(candles: List[Dict]) -> Optional[str]:
    """Deteta padrões de Topo Duplo ou Fundo Duplo."""
    if len(candles) < 20: return None
    peaks, troughs = find_recent_peaks_and_troughs(candles[-20:]) # Analisa as últimas 20 velas
    
    # Topo Duplo (padrão 'M')
    if len(peaks) >= 2:
        last_peak = peaks.iloc[-1]
        prev_peak = peaks.iloc[-2]
        # Verifica se os dois picos estão a um nível de preço semelhante
        if abs(last_peak['max'] - prev_peak['max']) / last_peak['max'] < 0.001: # Tolerância de 0.1%
            # Verifica se a vela atual está a fechar abaixo do vale entre os picos
            valley = troughs[troughs.index > prev_peak.name]
            if not valley.empty and candles[-1]['close'] < valley.iloc[0]['min']:
                return 'put'

    # Fundo Duplo (padrão 'W')
    if len(troughs) >= 2:
        last_trough = troughs.iloc[-1]
        prev_trough = troughs.iloc[-2]
        if abs(last_trough['min'] - prev_trough['min']) / last_trough['min'] < 0.001:
            peak_between = peaks[peaks.index > prev_trough.name]
            if not peak_between.empty and candles[-1]['close'] > peak_between.iloc[0]['max']:
                return 'call'
    return None

# ===============================================
# ESTRATÉGIAS COMPLETAS
# ===============================================

def strategy_reversal_pattern(candles: List[Dict]) -> Optional[str]:
    """Estratégia de Engolfo em zonas de S/R, a favor da tendência."""
    if len(candles) < 50: return None
    trend = check_ma_trend(candles)
    if not trend: return None
    pattern = check_candlestick_pattern(candles)
    if not pattern or pattern != trend: return None
    resistances, supports = get_m15_sr_zones(candles[-100:])
    engulfing_candle = candles[-1]
    if pattern == 'call':
        if any(engulfing_candle['min'] <= sup for sup in supports): return 'call'
    if pattern == 'put':
        if any(engulfing_candle['max'] >= res for res in resistances): return 'put'
    return None

def strategy_trend_flow(candles: List[Dict]) -> Optional[str]:
    """Estratégia de continuação de tendência (fluxo)."""
    if len(candles) < 3: return None
    trend = check_ma_trend(candles)
    if not trend: return None
    last_three_candles = candles[-3:]
    if trend == 'call' and all(c['close'] > c['open'] for c in last_three_candles): return 'call'
    if trend == 'put' and all(c['close'] < c['open'] for c in last_three_candles): return 'put'
    return None

def strategy_mql_pullback(candles: List[Dict]) -> Optional[str]:
    """Estratégia de pullback em zonas de S/R a favor da tendência."""
    trend = check_ma_trend(candles)
    if not trend: return None
    resistances, supports = get_m15_sr_zones(candles[-100:])
    last_candle = candles[-1]
    if trend == 'call':
        if any(last_candle['min'] <= sup and last_candle['close'] > sup for sup in supports): return 'call'
    if trend == 'put':
        if any(last_candle['max'] >= res and last_candle['close'] < res for res in resistances): return 'put'
    return None

def strategy_exhaustion_reversal(candles: List[Dict]) -> Optional[str]:
    """
    NOVA ESTRATÉGIA: Procura por Topos/Fundos Duplos como sinal principal de reversão.
    Esta é uma estratégia de alta seletividade.
    """
    return detect_double_top_bottom(candles)
