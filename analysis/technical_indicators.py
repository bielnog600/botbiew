import pandas as pd
import pandas_ta as ta
from typing import List, Dict, Optional

def _create_and_validate_dataframe(candles: List[Dict], required_columns: List[str]) -> Optional[pd.DataFrame]:
    if not candles: return None
    df = pd.DataFrame(candles)
    for col in required_columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        else:
            return None
    df.dropna(subset=required_columns, inplace=True)
    return df if not df.empty else None

def calculate_atr(candles: List[Dict]) -> Optional[float]:
    df = _create_and_validate_dataframe(candles, ['high', 'low', 'close'])
    if df is None or len(df) < 15: return None
    df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=14)
    return df['atr'].iloc[-1] if not pd.isna(df['atr'].iloc[-1]) else None

# --- ESTRATÉGIAS ANTERIORES (SEM ALTERAÇÃO) ---
def strategy_mql_pullback(candles: List[Dict]) -> Optional[str]:
    df = _create_and_validate_dataframe(candles, ['close', 'low', 'high'])
    if df is None or len(df) < 51: return None
    df['ema21'] = ta.ema(df['close'], length=21)
    df['ema50'] = ta.ema(df['close'], length=50)
    df.dropna(inplace=True)
    if len(df) < 2: return None
    last, prev = df.iloc[-1], df.iloc[-2]
    if last['ema21'] > last['ema50'] and prev['ema21'] > prev['ema50']:
        if prev['close'] > prev['ema21'] and last['low'] <= last['ema21'] and last['close'] > last['ema21']: return 'call'
    if last['ema21'] < last['ema50'] and prev['ema21'] < prev['ema50']:
        if prev['close'] < prev['ema21'] and last['high'] >= last['ema21'] and last['close'] < last['ema21']: return 'put'
    return None

def strategy_reversal_pattern(candles: List[Dict]) -> Optional[str]:
    df = _create_and_validate_dataframe(candles, ['high', 'low', 'open', 'close'])
    if df is None: return None
    last = df.iloc[-1]
    body = abs(last['open'] - last['close'])
    if body == 0: return None
    upper_wick = last['high'] - max(last['open'], last['close'])
    lower_wick = min(last['open'], last['close']) - last['low']
    if upper_wick > 2 * body and lower_wick < 0.5 * body: return 'put'
    if lower_wick > 2 * body and upper_wick < 0.5 * body: return 'call'
    return None

def strategy_trend_flow(candles: List[Dict]) -> Optional[str]:
    df = _create_and_validate_dataframe(candles, ['close'])
    if df is None or len(df) < 101: return None
    df['ema100'] = ta.ema(df['close'], length=100)
    df['rsi'] = ta.rsi(df['close'], length=14)
    df.dropna(inplace=True)
    if df.empty: return None
    last = df.iloc[-1]
    if last['close'] > last['ema100'] and last['rsi'] > 55: return 'call'
    if last['close'] < last['ema100'] and last['rsi'] < 45: return 'put'
    return None

def strategy_exhaustion_reversal(candles: List[Dict]) -> Optional[str]:
    df = _create_and_validate_dataframe(candles, ['close'])
    if df is None or len(df) < 8: return None
    df['rsi'] = ta.rsi(df['close'], length=7)
    df.dropna(inplace=True)
    if df.empty: return None
    last = df.iloc[-1]
    if last['rsi'] > 90: return 'put'
    if last['rsi'] < 10: return 'call'
    return None

def strategy_bollinger_bands(candles: List[Dict]) -> Optional[str]:
    df = _create_and_validate_dataframe(candles, ['close'])
    if df is None or len(df) < 21: return None
    bollinger = ta.bbands(df['close'], length=20, std=2)
    if bollinger is None: return None
    df = pd.concat([df, bollinger], axis=1)
    df.dropna(inplace=True)
    if df.empty: return None
    last = df.iloc[-1]
    if last['close'] > last['BBU_20_2.0']: return 'put'
    if last['close'] < last['BBL_20_2.0']: return 'call'
    return None

def strategy_macd_crossover(candles: List[Dict]) -> Optional[str]:
    df = _create_and_validate_dataframe(candles, ['close'])
    if df is None or len(df) < 27: return None
    macd = ta.macd(df['close'])
    if macd is None: return None
    df = pd.concat([df, macd], axis=1)
    df.dropna(inplace=True)
    if len(df) < 2: return None
    last, prev = df.iloc[-1], df.iloc[-2]
    if prev['MACD_12_26_9'] < prev['MACDs_12_26_9'] and last['MACD_12_26_9'] > last['MACDs_12_26_9']: return 'call'
    if prev['MACD_12_26_9'] > prev['MACDs_12_26_9'] and last['MACD_12_26_9'] < last['MACDs_12_26_9']: return 'put'
    return None

def strategy_triple_confirmation(candles: List[Dict]) -> Optional[str]:
    df = _create_and_validate_dataframe(candles, ['high', 'low', 'close'])
    if df is None or len(df) < 51: return None
    df['ema50'] = ta.ema(df['close'], length=50)
    df['rsi'] = ta.rsi(df['close'], length=14)
    stoch = ta.stoch(df['high'], df['low'], df['close'], k=14, d=3, smooth_k=3)
    if stoch is None: return None
    df = pd.concat([df, stoch], axis=1)
    df.dropna(inplace=True)
    if df.empty: return None
    last = df.iloc[-1]
    if last['close'] > last['ema50'] and last['rsi'] < 30 and last['STOCHk_14_3_3'] < 20: return 'call'
    if last['close'] < last['ema50'] and last['rsi'] > 70 and last['STOCHk_14_3_3'] > 80: return 'put'
    return None

def strategy_bb_ema_filter(candles: List[Dict]) -> Optional[str]:
    df = _create_and_validate_dataframe(candles, ['close'])
    if df is None or len(df) < 51: return None
    df['ema50'] = ta.ema(df['close'], length=50)
    bollinger = ta.bbands(df['close'], length=20, std=2)
    if bollinger is None: return None
    df = pd.concat([df, bollinger], axis=1)
    df.dropna(inplace=True)
    if df.empty: return None
    last = df.iloc[-1]
    if last['close'] > last['ema50'] and last['close'] < last['BBL_20_2.0']: return 'call'
    if last['close'] < last['ema50'] and last['close'] > last['BBU_20_2.0']: return 'put'
    return None

def strategy_macd_rsi_confirm(candles: List[Dict]) -> Optional[str]:
    df = _create_and_validate_dataframe(candles, ['close'])
    if df is None or len(df) < 30: return None
    df['rsi'] = ta.rsi(df['close'], length=14)
    macd = ta.macd(df['close'])
    if macd is None: return None
    df = pd.concat([df, macd], axis=1)
    df.dropna(inplace=True)
    if len(df) < 2: return None
    last, prev = df.iloc[-1], df.iloc[-2]
    if prev['MACD_12_26_9'] < prev['MACDs_12_26_9'] and last['MACD_12_26_9'] > last['MACDs_12_26_9'] and last['rsi'] < 55: return 'call'
    if prev['MACD_12_26_9'] > prev['MACDs_12_26_9'] and last['MACD_12_26_9'] < last['MACDs_12_26_9'] and last['rsi'] > 45: return 'put'
    return None

def strategy_rejection_rsi_wick(candles: List[Dict]) -> Optional[str]:
    df = _create_and_validate_dataframe(candles, ['high', 'low', 'open', 'close'])
    if df is None or len(df) < 15: return None
    df['rsi'] = ta.rsi(df['close'], length=14)
    df.dropna(inplace=True)
    if df.empty: return None
    last = df.iloc[-1]
    body = abs(last['open'] - last['close'])
    if body == 0: return None
    upper_wick = last['high'] - max(last['open'], last['close'])
    lower_wick = min(last['open'], last['close']) - last['low']
    if last['rsi'] > 75 and upper_wick > 2 * body and lower_wick < 0.7 * body: return 'put'
    if last['rsi'] < 25 and lower_wick > 2 * body and upper_wick < 0.7 * body: return 'call'
    return None

def strategy_ema_volume_crossover(candles: List[Dict]) -> Optional[str]:
    df = _create_and_validate_dataframe(candles, ['close', 'volume'])
    if df is None or len(df) < 22: return None
    df['ema_fast'] = ta.ema(df['close'], length=9)
    df['ema_slow'] = ta.ema(df['close'], length=21)
    df['volume_sma'] = ta.sma(df['volume'], length=20)
    df.dropna(inplace=True)
    if len(df) < 2: return None
    last, prev = df.iloc[-1], df.iloc[-2]
    volume_confirmed = last['volume'] > last['volume_sma'] * 1.2
    if prev['ema_fast'] < prev['ema_slow'] and last['ema_fast'] > last['ema_slow'] and volume_confirmed: return 'call'
    if prev['ema_fast'] > prev['ema_slow'] and last['ema_fast'] < last['ema_slow'] and volume_confirmed: return 'put'
    return None

# --- NOVAS ESTRATÉGIAS PROFISSIONAIS ---

def strategy_fake_breakout(candles: List[Dict]) -> Optional[str]:
    df = _create_and_validate_dataframe(candles, ['high', 'low', 'open', 'close'])
    if df is None or len(df) < 22: return None
    df['rsi'] = ta.rsi(df['close'], length=14)
    df.dropna(inplace=True)
    if len(df) < 3: return None

    last = df.iloc[-1]
    prev = df.iloc[-2]
    
    # Define suporte e resistência com base nos últimos 20 candles
    lookback_df = df.iloc[-21:-1]
    support = lookback_df['low'].min()
    resistance = lookback_df['high'].max()
    
    rsi_is_neutral = 40 < last['rsi'] < 60

    # Falso rompimento de resistência (sinal de PUT)
    if prev['high'] > resistance and last['close'] < prev['high'] and rsi_is_neutral:
        return 'put'

    # Falso rompimento de suporte (sinal de CALL)
    if prev['low'] < support and last['close'] > prev['low'] and rsi_is_neutral:
        return 'call'

    return None

def strategy_inside_bar_rsi(candles: List[Dict]) -> Optional[str]:
    df = _create_and_validate_dataframe(candles, ['high', 'low', 'close'])
    if df is None or len(df) < 15: return None
    df['rsi'] = ta.rsi(df['close'], length=14)
    df.dropna(inplace=True)
    if len(df) < 2: return None

    last = df.iloc[-1]
    prev = df.iloc[-2]

    is_inside_bar = last['high'] < prev['high'] and last['low'] > prev['low']
    if not is_inside_bar: return None

    if last['rsi'] > 70: return 'put'
    if last['rsi'] < 30: return 'call'
    
    return None

def strategy_engulfing_trend(candles: List[Dict]) -> Optional[str]:
    df = _create_and_validate_dataframe(candles, ['open', 'close'])
    if df is None or len(df) < 22: return None

    df['ema9'] = ta.ema(df['close'], length=9)
    df['ema21'] = ta.ema(df['close'], length=21)
    df['rsi'] = ta.rsi(df['close'], length=14)
    df.dropna(inplace=True)
    if len(df) < 2: return None

    last = df.iloc[-1]
    prev = df.iloc[-2]

    is_bullish_engulfing = last['close'] > prev['open'] and last['open'] < prev['close'] and last['close'] > prev['close'] and last['open'] < prev['open']
    is_bearish_engulfing = last['open'] > prev['close'] and last['close'] < prev['open'] and last['close'] < prev['close'] and last['open'] > prev['open']
    
    is_uptrend = last['ema9'] > last['ema21']
    is_downtrend = last['ema9'] < last['ema21']

    rsi_confirms_up = 50 < last['rsi'] < 70
    rsi_confirms_down = 30 < last['rsi'] < 50

    if is_bullish_engulfing and is_uptrend and rsi_confirms_up: return 'call'
    if is_bearish_engulfing and is_downtrend and rsi_confirms_down: return 'put'
    
    return None

def strategy_bollinger_squeeze(candles: List[Dict]) -> Optional[str]:
    df = _create_and_validate_dataframe(candles, ['close'])
    if df is None or len(df) < 21: return None

    bollinger = ta.bbands(df['close'], length=20, std=2)
    if bollinger is None: return None
    df = pd.concat([df, bollinger], axis=1)
    
    # Calcula a largura da banda
    df['bbw'] = bollinger['BBB_20_2.0']
    df.dropna(inplace=True)
    if len(df) < 4: return None

    last = df.iloc[-1]
    prev3 = df.iloc[-4:-1] # Últimos 3 candles antes do atual

    is_squeezed = (prev3['bbw'] < prev3['bbw'].rolling(20).min().iloc[-1] * 1.5).all()
    if not is_squeezed: return None

    body = abs(last['open'] - last['close'])
    candle_range = last['high'] - last['low']
    is_strong_candle = body / candle_range >= 0.6 if candle_range > 0 else False

    if is_strong_candle and last['close'] > last['BBU_20_2.0']: return 'call'
    if is_strong_candle and last['close'] < last['BBL_20_2.0']: return 'put'

    return None
