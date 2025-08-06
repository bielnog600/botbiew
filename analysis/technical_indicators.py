import pandas as pd
import pandas_ta as ta
from typing import List, Dict, Optional

def calculate_atr(candles: List[Dict]) -> Optional[float]:
    if not candles or len(candles) < 15:
        return None
    df = pd.DataFrame(candles)
    df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=14)
    return df['atr'].iloc[-1] if not pd.isna(df['atr'].iloc[-1]) else None

def validate_reversal_candle(candle: Dict, direction: str) -> bool:
    body_size = abs(candle['close'] - candle['open'])
    if body_size == 0: return False
    
    if direction == 'call': # Sinal de compra (reversão de baixa)
        upper_wick = candle['high'] - candle['close']
        lower_wick = candle['open'] - candle['low']
        return lower_wick > body_size * 1.5 and upper_wick < body_size * 0.7
    elif direction == 'put': # Sinal de venda (reversão de alta)
        upper_wick = candle['high'] - candle['open']
        lower_wick = candle['close'] - candle['low']
        return upper_wick > body_size * 1.5 and lower_wick < body_size * 0.7
    return False

# --- ESTRATÉGIAS EXISTENTES ---

def strategy_mql_pullback(candles: List[Dict]) -> Optional[str]:
    df = pd.DataFrame(candles)
    df['ema21'] = ta.ema(df['close'], length=21)
    df['ema50'] = ta.ema(df['close'], length=50)
    
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
    df = pd.DataFrame(candles)
    last = df.iloc[-1]
    
    body = abs(last['open'] - last['close'])
    upper_wick = last['high'] - max(last['open'], last['close'])
    lower_wick = min(last['open'], last['close']) - last['low']
    if upper_wick > 2 * body and lower_wick < 0.5 * body:
        return 'put'

    if lower_wick > 2 * body and upper_wick < 0.5 * body:
        return 'call'
        
    return None

def strategy_trend_flow(candles: List[Dict]) -> Optional[str]:
    df = pd.DataFrame(candles)
    df['ema100'] = ta.ema(df['close'], length=100)
    df['rsi'] = ta.rsi(df['close'], length=14)
    
    last = df.iloc[-1]
    
    if last['close'] > last['ema100'] and last['rsi'] > 55:
        return 'call'
    if last['close'] < last['ema100'] and last['rsi'] < 45:
        return 'put'
        
    return None

def strategy_exhaustion_reversal(candles: List[Dict]) -> Optional[str]:
    df = pd.DataFrame(candles)
    df['rsi'] = ta.rsi(df['close'], length=7)
    
    last = df.iloc[-1]
    
    if last['rsi'] > 90:
        return 'put'
    if last['rsi'] < 10:
        return 'call'
        
    return None

def strategy_bollinger_bands(candles: List[Dict]) -> Optional[str]:
    df = pd.DataFrame(candles)
    bollinger = ta.bbands(df['close'], length=20, std=2)
    df['bb_upper'] = bollinger['BBU_20_2.0']
    df['bb_lower'] = bollinger['BBL_20_2.0']
    
    last = df.iloc[-1]
    
    if last['close'] > last['bb_upper']:
        return 'put'
    if last['close'] < last['bb_lower']:
        return 'call'
        
    return None

def strategy_macd_crossover(candles: List[Dict]) -> Optional[str]:
    df = pd.DataFrame(candles)
    macd = ta.macd(df['close'])
    df['macd_line'] = macd['MACD_12_26_9']
    df['signal_line'] = macd['MACDs_12_26_9']
    
    last = df.iloc[-1]
    prev = df.iloc[-2]
    
    if prev['macd_line'] < prev['signal_line'] and last['macd_line'] > last['signal_line']:
        return 'call'
    if prev['macd_line'] > prev['signal_line'] and last['macd_line'] < last['signal_line']:
        return 'put'
        
    return None

def strategy_triple_confirmation(candles: List[Dict]) -> Optional[str]:
    if len(candles) < 51: return None
    df = pd.DataFrame(candles)
    df['ema50'] = ta.ema(df['close'], length=50)
    df['rsi'] = ta.rsi(df['close'], length=14)
    stoch = ta.stoch(df['high'], df['low'], df['close'], k=14, d=3, smooth_k=3)
    df['stoch_k'] = stoch['STOCHk_14_3_3']
    last = df.iloc[-1]
    
    is_uptrend = last['close'] > last['ema50']
    is_rsi_oversold = last['rsi'] < 30
    is_stoch_oversold = last['stoch_k'] < 20
    if is_uptrend and is_rsi_oversold and is_stoch_oversold:
        return 'call'
        
    is_downtrend = last['close'] < last['ema50']
    is_rsi_overbought = last['rsi'] > 70
    is_stoch_overbought = last['stoch_k'] > 80
    if is_downtrend and is_rsi_overbought and is_stoch_overbought:
        return 'put'
        
    return None

# --- NOVAS ESTRATÉGIAS DE CONFLUÊNCIA ---

def strategy_bb_ema_filter(candles: List[Dict]) -> Optional[str]:
    """
    Estratégia de Fuga de Bollinger com Filtro de Tendência EMA.
    Opera reversões apenas a favor da tendência principal.
    """
    if len(candles) < 51: return None
    df = pd.DataFrame(candles)
    
    # Indicadores
    df['ema50'] = ta.ema(df['close'], length=50)
    bollinger = ta.bbands(df['close'], length=20, std=2)
    df['bb_upper'] = bollinger['BBU_20_2.0']
    df['bb_lower'] = bollinger['BBL_20_2.0']
    
    last = df.iloc[-1]
    
    # Condições de CALL
    is_uptrend = last['close'] > last['ema50']
    is_oversold_breakout = last['close'] < last['bb_lower']
    if is_uptrend and is_oversold_breakout:
        return 'call'
        
    # Condições de PUT
    is_downtrend = last['close'] < last['ema50']
    is_overbought_breakout = last['close'] > last['bb_upper']
    if is_downtrend and is_overbought_breakout:
        return 'put'
        
    return None

def strategy_macd_rsi_confirm(candles: List[Dict]) -> Optional[str]:
    """
    Estratégia de Cruzamento MACD com confirmação de força do RSI.
    Evita operar cruzamentos em mercados já sobre-esticados.
    """
    if len(candles) < 30: return None
    df = pd.DataFrame(candles)
    
    # Indicadores
    df['rsi'] = ta.rsi(df['close'], length=14)
    macd = ta.macd(df['close'])
    df['macd_line'] = macd['MACD_12_26_9']
    df['signal_line'] = macd['MACDs_12_26_9']
    
    last = df.iloc[-1]
    prev = df.iloc[-2]
    
    # Condições de CALL
    macd_crossed_up = prev['macd_line'] < prev['signal_line'] and last['macd_line'] > last['signal_line']
    rsi_has_room_to_grow = last['rsi'] < 55
    if macd_crossed_up and rsi_has_room_to_grow:
        return 'call'
        
    # Condições de PUT
    macd_crossed_down = prev['macd_line'] > prev['signal_line'] and last['macd_line'] < last['signal_line']
    rsi_has_room_to_fall = last['rsi'] > 45
    if macd_crossed_down and rsi_has_room_to_fall:
        return 'put'
        
    return None
