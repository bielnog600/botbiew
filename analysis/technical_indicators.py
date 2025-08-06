import pandas as pd
import pandas_ta as ta
from typing import List, Dict, Optional

def _create_and_validate_dataframe(candles: List[Dict], required_columns: List[str]) -> Optional[pd.DataFrame]:
    """
    Função auxiliar para criar um DataFrame e validar se as colunas essenciais existem.
    Se uma coluna não existir, a função retorna None para evitar erros.
    """
    if not candles:
        return None
    df = pd.DataFrame(candles)
    # Garante que os dados são numéricos, convertendo erros em NaN (Not a Number)
    for col in required_columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        else:
            return None # Retorna None se uma coluna requerida não existir
    
    # Remove linhas que tenham qualquer valor nulo nas colunas requeridas
    df.dropna(subset=required_columns, inplace=True)
    
    if df.empty:
        return None
        
    return df

def calculate_atr(candles: List[Dict]) -> Optional[float]:
    df = _create_and_validate_dataframe(candles, ['high', 'low', 'close'])
    if df is None or len(df) < 15:
        return None
    
    df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=14)
    return df['atr'].iloc[-1] if not pd.isna(df['atr'].iloc[-1]) else None

def validate_reversal_candle(candle: Dict, direction: str) -> bool:
    if not all(key in candle for key in ['high', 'low', 'open', 'close']):
        return False

    body_size = abs(candle['close'] - candle['open'])
    if body_size == 0: return False
    
    if direction == 'call':
        upper_wick = candle['high'] - candle['close']
        lower_wick = candle['open'] - candle['low']
        return lower_wick > body_size * 1.5 and upper_wick < body_size * 0.7
    elif direction == 'put':
        upper_wick = candle['high'] - candle['open']
        lower_wick = candle['close'] - candle['low']
        return upper_wick > body_size * 1.5 and lower_wick < body_size * 0.7
    return False

# --- ESTRATÉGIAS ---

def strategy_mql_pullback(candles: List[Dict]) -> Optional[str]:
    df = _create_and_validate_dataframe(candles, ['close', 'low', 'high'])
    if df is None or len(df) < 51: return None

    df['ema21'] = ta.ema(df['close'], length=21)
    df['ema50'] = ta.ema(df['close'], length=50)
    df.dropna(inplace=True)
    if len(df) < 2: return None
    
    last = df.iloc[-1]
    prev = df.iloc[-2]

    if last['ema21'] > last['ema50'] and prev['ema21'] > prev['ema50']:
        if prev['close'] > prev['ema21'] and last['low'] <= last['ema21'] and last['close'] > last['ema21']:
            return 'call'
            
    if last['ema21'] < last['ema50'] and prev['ema21'] < prev['ema50']:
        if prev['close'] < prev['ema21'] and last['high'] >= last['ema21'] and last['close'] < last['ema21']:
            return 'put'
            
    return None

def strategy_reversal_pattern(candles: List[Dict]) -> Optional[str]:
    df = _create_and_validate_dataframe(candles, ['high', 'low', 'open', 'close'])
    if df is None: return None
    
    last = df.iloc[-1]
    body = abs(last['open'] - last['close'])
    if body == 0: return None
    
    upper_wick = last['high'] - max(last['open'], last['close'])
    lower_wick = min(last['open'], last['close']) - last['low']
    
    if upper_wick > 2 * body and lower_wick < 0.5 * body:
        return 'put'
    if lower_wick > 2 * body and upper_wick < 0.5 * body:
        return 'call'
        
    return None

def strategy_trend_flow(candles: List[Dict]) -> Optional[str]:
    df = _create_and_validate_dataframe(candles, ['close'])
    if df is None or len(df) < 101: return None

    df['ema100'] = ta.ema(df['close'], length=100)
    df['rsi'] = ta.rsi(df['close'], length=14)
    df.dropna(inplace=True)
    if df.empty: return None
    
    last = df.iloc[-1]
    
    if last['close'] > last['ema100'] and last['rsi'] > 55:
        return 'call'
    if last['close'] < last['ema100'] and last['rsi'] < 45:
        return 'put'
        
    return None

def strategy_exhaustion_reversal(candles: List[Dict]) -> Optional[str]:
    df = _create_and_validate_dataframe(candles, ['close'])
    if df is None or len(df) < 8: return None

    df['rsi'] = ta.rsi(df['close'], length=7)
    df.dropna(inplace=True)
    if df.empty: return None

    last = df.iloc[-1]
    
    if last['rsi'] > 90:
        return 'put'
    if last['rsi'] < 10:
        return 'call'
        
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
    
    if last['close'] > last['BBU_20_2.0']:
        return 'put'
    if last['close'] < last['BBL_20_2.0']:
        return 'call'
        
    return None

def strategy_macd_crossover(candles: List[Dict]) -> Optional[str]:
    df = _create_and_validate_dataframe(candles, ['close'])
    if df is None or len(df) < 27: return None

    macd = ta.macd(df['close'])
    if macd is None: return None
    df = pd.concat([df, macd], axis=1)
    df.dropna(inplace=True)
    if len(df) < 2: return None
    
    last = df.iloc[-1]
    prev = df.iloc[-2]
    
    if prev['MACD_12_26_9'] < prev['MACDs_12_26_9'] and last['MACD_12_26_9'] > last['MACDs_12_26_9']:
        return 'call'
    if prev['MACD_12_26_9'] > prev['MACDs_12_26_9'] and last['MACD_12_26_9'] < last['MACDs_12_26_9']:
        return 'put'
        
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
    
    is_uptrend = last['close'] > last['ema50']
    is_rsi_oversold = last['rsi'] < 30
    is_stoch_oversold = last['STOCHk_14_3_3'] < 20
    if is_uptrend and is_rsi_oversold and is_stoch_oversold:
        return 'call'
        
    is_downtrend = last['close'] < last['ema50']
    is_rsi_overbought = last['rsi'] > 70
    is_stoch_overbought = last['STOCHk_14_3_3'] > 80
    if is_downtrend and is_rsi_overbought and is_stoch_overbought:
        return 'put'
        
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
    
    is_uptrend = last['close'] > last['ema50']
    is_oversold_breakout = last['close'] < last['BBL_20_2.0']
    if is_uptrend and is_oversold_breakout:
        return 'call'
        
    is_downtrend = last['close'] < last['ema50']
    is_overbought_breakout = last['close'] > last['BBU_20_2.0']
    if is_downtrend and is_overbought_breakout:
        return 'put'
        
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
    
    last = df.iloc[-1]
    prev = df.iloc[-2]
    
    macd_crossed_up = prev['MACD_12_26_9'] < prev['MACDs_12_26_9'] and last['MACD_12_26_9'] > last['MACDs_12_26_9']
    rsi_has_room_to_grow = last['rsi'] < 55
    if macd_crossed_up and rsi_has_room_to_grow:
        return 'call'
        
    macd_crossed_down = prev['MACD_12_26_9'] > prev['MACDs_12_26_9'] and last['MACD_12_26_9'] < last['MACDs_12_26_9']
    rsi_has_room_to_fall = last['rsi'] > 45
    if macd_crossed_down and rsi_has_room_to_fall:
        return 'put'
        
    return None

# --- NOVAS ESTRATÉGIAS ADICIONADAS ---

def strategy_rejection_rsi_wick(candles: List[Dict]) -> Optional[str]:
    """
    Estratégia de Rejeição com RSI e Pavio.
    Busca por velas de reversão (martelos/estrelas cadentes) em zonas de RSI extremo.
    """
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

    # Sinal de PUT (Venda)
    is_rsi_overbought = last['rsi'] > 75
    is_shooting_star = upper_wick > 2 * body and lower_wick < 0.7 * body
    if is_rsi_overbought and is_shooting_star:
        return 'put'

    # Sinal de CALL (Compra)
    is_rsi_oversold = last['rsi'] < 25
    is_hammer = lower_wick > 2 * body and upper_wick < 0.7 * body
    if is_rsi_oversold and is_hammer:
        return 'call'

    return None

def strategy_ema_volume_crossover(candles: List[Dict]) -> Optional[str]:
    """
    Estratégia de Cruzamento de Médias Móveis com Confirmação de Volume.
    """
    df = _create_and_validate_dataframe(candles, ['close', 'volume'])
    if df is None or len(df) < 22: return None

    df['ema_fast'] = ta.ema(df['close'], length=9)
    df['ema_slow'] = ta.ema(df['close'], length=21)
    df['volume_sma'] = ta.sma(df['volume'], length=20)
    df.dropna(inplace=True)
    if len(df) < 2: return None

    last = df.iloc[-1]
    prev = df.iloc[-2]

    volume_confirmed = last['volume'] > last['volume_sma'] * 1.2 # Volume 20% acima da média

    # Sinal de CALL (Compra)
    fast_crosses_above_slow = prev['ema_fast'] < prev['ema_slow'] and last['ema_fast'] > last['ema_slow']
    if fast_crosses_above_slow and volume_confirmed:
        return 'call'

    # Sinal de PUT (Venda)
    fast_crosses_below_slow = prev['ema_fast'] > prev['ema_slow'] and last['ema_fast'] < last['ema_slow']
    if fast_crosses_below_slow and volume_confirmed:
        return 'put'

    return None
