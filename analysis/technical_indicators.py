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
    
    # Renomeia colunas se necessário (de 'max'/'min' para 'high'/'low')
    if 'max' in df.columns:
        df.rename(columns={'max': 'high'}, inplace=True)
    if 'min' in df.columns:
        df.rename(columns={'min': 'low'}, inplace=True)

    # Verifica se as colunas necessárias existem
    required_columns = ['high', 'low']
    if not all(col in df.columns for col in required_columns):
        return [], []

    # Encontra os fractais (pontos de viragem)
    # Um fractal de alta (resistência) é um candle com a máxima mais alta do que as duas velas anteriores e as duas seguintes.
    # Um fractal de baixa (suporte) é um candle com a mínima mais baixa do que as duas velas anteriores e as duas seguintes.
    
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
            
    # Retorna as últimas 5 zonas encontradas para manter o gráfico limpo
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

def check_price_near_sr(candle: dict, zones: Dict[str, List[float]], proximity_pips: int = 5) -> Optional[str]:
    """Verifica se o preço de um candle está perto de uma zona de Suporte ou Resistência."""
    try:
        price = candle['close']
        proximity = proximity_pips * 0.00001 # Converte pips para valor de preço

        for r_zone in zones.get('resistance', []):
            if r_zone >= price >= (r_zone - proximity):
                return 'put' # Preço perto de uma resistência -> sinal de venda

        for s_zone in zones.get('support', []):
            if s_zone <= price <= (s_zone + proximity):
                return 'call' # Preço perto de um suporte -> sinal de compra
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

    # Usa a função `cdl_pattern` da biblioteca pandas_ta para encontrar padrões
    # Esta função procura por vários padrões de uma vez.
    df.ta.cdl_pattern(name="all", append=True)
    
    last_row = df.iloc[-1]
    
    # Procura por sinais de alta (Bullish)
    bullish_signals = [col for col in df.columns if col.startswith('CDL_') and last_row[col] > 0]
    if bullish_signals:
        return 'call'

    # Procura por sinais de baixa (Bearish)
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
            return 'put' # RSI em sobrecompra -> sinal de venda
        if last_rsi <= oversold:
            return 'call' # RSI em sobrevenda -> sinal de compra
            
    return None

# Esta é a função que melhorámos recentemente.
def validate_reversal_candle(candle: dict, direction: str) -> bool:
    """
    Valida a qualidade da vela de sinal para uma operação de reversão.
    Esta função verifica a cor da vela e a proporção do corpo em relação ao pavio.

    Args:
        candle (dict): Um dicionário representando a vela, com chaves 'open', 'close', 'max', 'min'.
        direction (str): A direção do sinal ('call' ou 'put').

    Returns:
        bool: True se a vela for um bom sinal de reversão, False caso contrário.
    """
    try:
        o, c, h, l = candle['open'], candle['close'], candle['max'], candle['min']

        # 1. Validar a cor da vela
        is_bullish = c > o
        is_bearish = c < o

        if direction == 'call' and not is_bullish:
            # Para um sinal de COMPRA, a vela de confirmação deve ser de ALTA (verde).
            return False
        
        if direction == 'put' and not is_bearish:
            # Para um sinal de VENDA, a vela de confirmação deve ser de BAIXA (vermelha).
            return False

        # 2. Validar o tamanho do corpo (filtro de indecisão)
        total_range = h - l
        body_size = abs(o - c)

        if total_range == 0:
            # Evita divisão por zero e velas sem movimento.
            return False

        # O corpo deve ser pelo menos 30% do tamanho total da vela.
        # Isto filtra dojis e velas com pavios muito longos que indicam indecisão.
        min_body_ratio = 0.30 
        if (body_size / total_range) < min_body_ratio:
            return False
            
        # Se passou por todas as validações, é uma boa vela de sinal.
        return True

    except (KeyError, ZeroDivisionError):
        # Retorna False se a vela não tiver os dados necessários ou se o range for zero.
        return False
