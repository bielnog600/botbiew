import pandas as pd
import pandas_ta as ta
from typing import List, Dict, Optional

# Classe auxiliar para lidar com os dados das velas
class Candle:
    def __init__(self, data):
        self.open = data.get('open')
        self.max = data.get('max')
        self.min = data.get('min')
        self.close = data.get('close')

def _convert_candles_to_dataframe(candles: List[Candle]) -> pd.DataFrame:
    """Converte uma lista de objetos Candle para um DataFrame do Pandas."""
    if not candles: return pd.DataFrame()
    df = pd.DataFrame([vars(c) for c in candles])
    df.rename(columns={'max': 'high', 'min': 'low'}, inplace=True)
    for col in ['open', 'high', 'low', 'close']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    return df

# --- Funções dos Indicadores ---

def calculate_ema(candles: List[Candle], period: int) -> Optional[float]:
    if not candles or len(candles) < period: return None
    df = _convert_candles_to_dataframe(candles)
    if df.empty or 'close' not in df.columns or df['close'].isnull().any(): return None
    return ta.ema(df['close'], length=period).iloc[-1]

def calculate_atr(candles: List[Candle], period: int) -> Optional[float]:
    if not candles or len(candles) < period: return None
    df = _convert_candles_to_dataframe(candles)
    if df.empty or 'high' not in df.columns or df['high'].isnull().any(): return None
    return ta.atr(df['high'], df['low'], df['close'], length=period).iloc[-1]

def check_rsi_condition(candles: List[Candle], overbought=70, oversold=30, period=14) -> Optional[str]:
    if not candles or len(candles) < period: return None
    df = _convert_candles_to_dataframe(candles)
    if df.empty or 'close' not in df.columns or df['close'].isnull().any(): return None
    rsi_value = ta.rsi(df['close'], length=period).iloc[-1]
    if rsi_value > overbought: return 'put'
    if rsi_value < oversold: return 'call'
    return None

def validate_reversal_candle(candle: Candle, direction: str) -> bool:
    """Verifica se a vela de sinal tem corpo forte e não tem pavios contrários."""
    if not all([candle.open, candle.close, candle.max, candle.min]): return False
    body_size = abs(candle.close - candle.open)
    total_range = candle.max - candle.min
    if total_range == 0: return False
    
    # Regra 1: Corpo deve ser pelo menos 50% do range total da vela
    if (body_size / total_range) < 0.5: return False
    
    upper_wick = candle.max - max(candle.open, candle.close)
    lower_wick = min(candle.open, candle.close) - candle.min
    
    # Regra 2: Rejeita sinais com forte pressão contrária
    if direction == 'call' and upper_wick > body_size: return False
    if direction == 'put' and lower_wick > body_size: return False
    
    return True

def check_candlestick_pattern(candles: List[Candle]) -> Optional[str]:
    """Identifica um conjunto de padrões de vela de reversão."""
    if len(candles) < 3: return None
    
    df = _convert_candles_to_dataframe(candles)
    if df.empty: return None

    # Usa a extensão 'ta' do pandas_ta para analisar os padrões
    df.ta.cdl_pattern(name=["engulfing", "hammer", "shootingstar", "doji", "morningstar", "eveningstar", "piercing", "darkcloud", "tweezertop", "tweezerbottom"], append=True)
    
    # Pega os resultados da última vela analisada
    last = df.iloc[-1]

    # Sinais de Compra (CALL)
    if last.get('CDL_ENGULFING', 0) == 100 or \
       last.get('CDL_HAMMER', 0) == 100 or \
       last.get('CDL_MORNINGSTAR', 0) == 100 or \
       last.get('CDL_PIERCING', 0) == 100 or \
       last.get('CDL_TWEEZERBOTTOM', 0) == 100 or \
       last.get('CDL_DOJI', 0) != 0: # Doji é sinal de indecisão, pode ser usado para ambos
        return 'call'
        
    # Sinais de Venda (PUT)
    if last.get('CDL_ENGULFING', 0) == -100 or \
       last.get('CDL_SHOOTINGSTAR', 0) == 100 or \
       last.get('CDL_EVENINGSTAR', 0) == 100 or \
       last.get('CDL_DARKCLOUD', 0) == 100 or \
       last.get('CDL_TWEEZERTOP', 0) == 100 or \
       last.get('CDL_DOJI', 0) != 0:
        return 'put'
        
    return None

def check_price_near_sr(last_candle: Candle, zones: Dict, tolerance=0.0005) -> Optional[str]:
    if last_candle is None or last_candle.close is None: return None
    price = last_candle.close
    for r in zones.get('resistance', []):
        if r is None: continue
        if abs(price - r) / r < tolerance: return 'put'
    for s in zones.get('support', []):
        if s is None: continue
        if abs(price - s) / s < tolerance: return 'call'
    return None

def check_m5_price_action(candles: List[Candle], zones: Dict) -> Optional[Dict]:
    """Analisa a vela anterior em busca de um sinal de Pinbar em zonas de S/R."""
    if len(candles) < 2: return None
    signal_candle = candles[-2]

    # Análise para COMPRA (CALL) em Suporte
    if check_price_near_sr(signal_candle, {'support': zones.get('support', [])}) == 'call':
        body_size = abs(signal_candle.close - signal_candle.open)
        if body_size > 0:
            lower_wick = min(signal_candle.open, signal_candle.close) - signal_candle.min
            if lower_wick >= 1.5 * body_size:
                return {'direction': 'call', 'confluences': ['SR_Zone_Support', 'Pinbar_Bullish']}

    # Análise para VENDA (PUT) em Resistência
    if check_price_near_sr(signal_candle, {'resistance': zones.get('resistance', [])}) == 'put':
        body_size = abs(signal_candle.close - signal_candle.open)
        if body_size > 0:
            upper_wick = signal_candle.max - max(signal_candle.open, signal_candle.close)
            if upper_wick >= 1.5 * body_size:
                return {'direction': 'put', 'confluences': ['SR_Zone_Resistance', 'Pinbar_Bearish']}
    return None
