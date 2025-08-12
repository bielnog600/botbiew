import pandas as pd
import pandas_ta as ta
from typing import List, Dict, Optional

def _create_and_validate_dataframe(candles: List[Dict], required_columns: List[str]) -> Optional[pd.DataFrame]:
    """
    Função auxiliar para criar um DataFrame e validar se as colunas essenciais existem.
    Se uma coluna não existir, a função retorna None para evitar erros.
    """
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

# --- ESTRATÉGIAS ---

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

def strategy_fake_breakout(candles: List[Dict]) -> Optional[str]:
    df = _create_and_validate_dataframe(candles, ['high', 'low', 'open', 'close'])
    if df is None or len(df) < 22: return None
    df['rsi'] = ta.rsi(df['close'], length=14)
    df.dropna(inplace=True)
    if len(df) < 3: return None
    last, prev = df.iloc[-1], df.iloc[-2]
    lookback_df = df.iloc[-21:-1]
    support = lookback_df['low'].min()
    resistance = lookback_df['high'].max()
    rsi_is_neutral = 40 < last['rsi'] < 60
    if prev['high'] > resistance and last['close'] < prev['high'] and rsi_is_neutral: return 'put'
    if prev['low'] < support and last['close'] > prev['low'] and rsi_is_neutral: return 'call'
    return None

def strategy_inside_bar_rsi(candles: List[Dict]) -> Optional[str]:
    df = _create_and_validate_dataframe(candles, ['high', 'low', 'close'])
    if df is None or len(df) < 15: return None
    df['rsi'] = ta.rsi(df['close'], length=14)
    df.dropna(inplace=True)
    if len(df) < 2: return None
    last, prev = df.iloc[-1], df.iloc[-2]
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
    last, prev = df.iloc[-1], df.iloc[-2]
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
    df = _create_and_validate_dataframe(candles, ['close', 'open', 'high', 'low'])
    if df is None or len(df) < 21: return None
    bollinger = ta.bbands(df['close'], length=20, std=2)
    if bollinger is None: return None
    df = pd.concat([df, bollinger], axis=1)
    df['bbw'] = bollinger['BBB_20_2.0']
    df.dropna(inplace=True)
    if len(df) < 4: return None
    last = df.iloc[-1]
    prev3 = df.iloc[-4:-1]
    is_squeezed = (prev3['bbw'] < prev3['bbw'].rolling(20).min().iloc[-1] * 1.5).all()
    if not is_squeezed: return None
    body = abs(last['open'] - last['close'])
    candle_range = last['high'] - last['low']
    is_strong_candle = body / candle_range >= 0.6 if candle_range > 0 else False
    if is_strong_candle and last['close'] > last['BBU_20_2.0']: return 'call'
    if is_strong_candle and last['close'] < last['BBL_20_2.0']: return 'put'
    return None

def strategy_stochrsi_scalp(candles: List[Dict]) -> Optional[str]:
    df = _create_and_validate_dataframe(candles, ['close'])
    if df is None or len(df) < 30: return None
    stoch_rsi = ta.stochrsi(df['close'], length=14, rsi_length=14, k=3, d=3)
    if stoch_rsi is None: return None
    df = pd.concat([df, stoch_rsi], axis=1)
    df.dropna(inplace=True)
    if len(df) < 2: return None
    last, prev = df.iloc[-1], df.iloc[-2]
    if prev['STOCHRSIk_14_14_3_3'] < 20 and last['STOCHRSIk_14_14_3_3'] > 20: return 'call'
    if prev['STOCHRSIk_14_14_3_3'] > 80 and last['STOCHRSIk_14_14_3_3'] < 80: return 'put'
    return None

def strategy_awesome_saucer(candles: List[Dict]) -> Optional[str]:
    df = _create_and_validate_dataframe(candles, ['high', 'low'])
    if df is None or len(df) < 35: return None
    df['ao'] = ta.ao(df['high'], df['low'])
    df.dropna(inplace=True)
    if len(df) < 3: return None
    c1, c2, c3 = df['ao'].iloc[-3], df['ao'].iloc[-2], df['ao'].iloc[-1]
    if c1 > 0 and c2 > 0 and c3 > 0 and c1 > c2 and c3 > c2: return 'call'
    if c1 < 0 and c2 < 0 and c3 < 0 and c1 < c2 and c3 < c2: return 'put'
    return None

def strategy_keltner_reversion(candles: List[Dict]) -> Optional[str]:
    df = _create_and_validate_dataframe(candles, ['high', 'low', 'close'])
    if df is None or len(df) < 21: return None
    kc = ta.kc(df['high'], df['low'], df['close'], length=20)
    if kc is None: return None
    df = pd.concat([df, kc], axis=1)
    df.dropna(inplace=True)
    if df.empty: return None
    last = df.iloc[-1]
    if last['close'] < last['KCLe_20_2']: return 'call'
    if last['close'] > last['KCUe_20_2']: return 'put'
    return None

def strategy_heikinashi_trend(candles: List[Dict]) -> Optional[str]:
    df = _create_and_validate_dataframe(candles, ['open', 'high', 'low', 'close'])
    if df is None: return None
    ha_df = ta.ha(df['open'], df['high'], df['low'], df['close'])
    if ha_df is None: return None
    df = pd.concat([df, ha_df], axis=1)
    df.dropna(inplace=True)
    if len(df) < 3: return None
    last, prev = df.iloc[-1], df.iloc[-2]
    is_green = last['HA_close'] > last['HA_open']
    is_red = last['HA_close'] < last['HA_open']
    prev_is_green = prev['HA_close'] > prev['HA_open']
    prev_is_red = prev['HA_close'] < prev['HA_open']
    if is_green and prev_is_green and last['HA_open'] == last['HA_low']: return 'call'
    if is_red and prev_is_red and last['HA_open'] == last['HA_high']: return 'put'
    return None

def strategy_vortex_cross(candles: List[Dict]) -> Optional[str]:
    df = _create_and_validate_dataframe(candles, ['high', 'low', 'close'])
    if df is None or len(df) < 15: return None
    vortex = ta.vortex(df['high'], df['low'], df['close'], length=14)
    if vortex is None: return None
    df = pd.concat([df, vortex], axis=1)
    df.dropna(inplace=True)
    if len(df) < 2: return None
    last, prev = df.iloc[-1], df.iloc[-2]
    if prev['VTXP_14'] < prev['VTXM_14'] and last['VTXP_14'] > last['VTXM_14']: return 'call'
    if prev['VTXP_14'] > prev['VTXM_14'] and last['VTXP_14'] < last['VTXM_14']: return 'put'
    return None

def strategy_fractal_reversal(candles: List[Dict]) -> Optional[str]:
    df = _create_and_validate_dataframe(candles, ['high', 'low'])
    if df is None or len(df) < 5: return None
    if df['high'].iloc[-3] == df['high'].iloc[-5:].max(): return 'put'
    if df['low'].iloc[-3] == df['low'].iloc[-5:].min(): return 'call'
    return None

def strategy_bollinger_fractal_stoch(candles: List[Dict]) -> Optional[str]:
    df = _create_and_validate_dataframe(candles, ['high', 'low', 'close'])
    if df is None or len(df) < 21: return None
    bollinger = ta.bbands(df['close'], length=20, std=2)
    if bollinger is None: return None
    df = pd.concat([df, bollinger], axis=1)
    stoch = ta.stoch(df['high'], df['low'], df['close'], k=14, d=3, smooth_k=3)
    if stoch is None: return None
    df = pd.concat([df, stoch], axis=1)
    df.dropna(inplace=True)
    if len(df) < 5: return None
    last = df.iloc[-1]
    is_sell_fractal = df['high'].iloc[-3] == df['high'].iloc[-5:].max()
    is_buy_fractal = df['low'].iloc[-3] == df['low'].iloc[-5:].min()
    is_bb_oversold = last['close'] < last['BBL_20_2.0']
    is_stoch_oversold = last['STOCHk_14_3_3'] < 20
    if is_buy_fractal and is_bb_oversold and is_stoch_oversold: return 'call'
    is_bb_overbought = last['close'] > last['BBU_20_2.0']
    is_stoch_overbought = last['STOCHk_14_3_3'] > 80
    if is_sell_fractal and is_bb_overbought and is_stoch_overbought: return 'put'
    return None
