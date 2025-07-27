import pandas as pd
from typing import List, Dict, Optional

# --- Funções de Análise e Indicadores ---

def calculate_atr(candles: list, period: int = 14) -> Optional[float]:
    """Calcula o Average True Range (ATR) para uma lista de velas."""
    if len(candles) < period:
        return None
    
    highs = pd.Series([c['max'] for c in candles])
    lows = pd.Series([c['min'] for c in candles])
    closes = pd.Series([c['close'] for c in candles])
    
    tr1 = highs - lows
    tr2 = abs(highs - closes.shift())
    tr3 = abs(lows - closes.shift())
    
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = true_range.ewm(alpha=1/period, adjust=False).mean()
    
    return atr.iloc[-1]

def get_sr_zones(candles: list, n: int = 5) -> (List[float], List[float]):
    """Encontra zonas de suporte e resistência com base nos fractais."""
    if len(candles) < 5:
        return [], []
    
    highs = [c['max'] for c in candles]
    lows = [c['min'] for c in candles]
    
    resistances = []
    supports = []

    for i in range(2, len(candles) - 2):
        # Fractal de Alta (Resistência)
        if highs[i] > highs[i-1] and highs[i] > highs[i-2] and highs[i] > highs[i+1] and highs[i] > highs[i+2]:
            resistances.append(highs[i])
        # Fractal de Baixa (Suporte)
        if lows[i] < lows[i-1] and lows[i] < lows[i-2] and lows[i] < lows[i+1] and lows[i] < lows[i+2]:
            supports.append(lows[i])
            
    # Retorna as 'n' zonas mais recentes
    return sorted(resistances, reverse=True)[:n], sorted(supports, reverse=True)[:n]

def check_ma_trend(candles: list, fast_period: int = 9, slow_period: int = 21) -> Optional[str]:
    """Verifica a tendência principal usando duas médias móveis exponenciais."""
    if len(candles) < slow_period:
        return None
    
    closes = pd.Series([c['close'] for c in candles])
    ema_fast = closes.ewm(span=fast_period, adjust=False).mean()
    ema_slow = closes.ewm(span=slow_period, adjust=False).mean()
    
    if ema_fast.iloc[-1] > ema_slow.iloc[-1]:
        return 'call'  # Tendência de alta
    else:
        return 'put'  # Tendência de baixa

def validate_reversal_candle(candle: dict, direction: str) -> bool:
    """Valida a qualidade da vela de sinal para uma reversão."""
    body = abs(candle['close'] - candle['open'])
    wick_range = candle['max'] - candle['min']
    if wick_range == 0: return False

    body_ratio = body / wick_range
    if body_ratio < 0.4: return False # Exige um corpo com pelo menos 40% do tamanho total

    if direction == 'call': # Para compra
        return candle['close'] > candle['open'] # Vela verde
    elif direction == 'put': # Para venda
        return candle['close'] < candle['open'] # Vela vermelha
    return False

# --- Estratégias de Negociação ---

def strategy_mql_pullback(candles: list) -> Optional[str]:
    """Estratégia de Pullback em zonas de Suporte/Resistência a favor da tendência."""
    if len(candles) < 25: return None
    
    trend = check_ma_trend(candles)
    if not trend: return None

    resistances, supports = get_sr_zones(candles[:-1]) # Usa velas passadas para S/R
    
    signal_candle = candles[-1]

    if trend == 'call' and supports:
        for support_level in supports:
            if signal_candle['min'] <= support_level and signal_candle['close'] > support_level:
                return 'call'
    
    if trend == 'put' and resistances:
        for resistance_level in resistances:
            if signal_candle['max'] >= resistance_level and signal_candle['close'] < resistance_level:
                return 'put'

    return None

def strategy_reversal_pattern(candles: list) -> Optional[str]:
    """Estratégia de Engolfo em zonas de S/R a favor da tendência, com filtros de qualidade."""
    if len(candles) < 25: return None

    trend = check_ma_trend(candles)
    if not trend: return None
    
    resistances, supports = get_sr_zones(candles[:-2]) # S/R baseado em velas mais antigas
    
    # Velas relevantes para o padrão
    prev_candle_2 = candles[-3]
    prev_candle_1 = candles[-2]
    signal_candle = candles[-1]
    
    # --- Filtro de Qualidade 1: Contexto (Mini-tendência de reversão) ---
    is_reversal_context = False
    if trend == 'call': # Procurando um Engolfo de Alta
        # Exige que as 2 velas anteriores sejam de baixa (vermelhas)
        if prev_candle_1['close'] < prev_candle_1['open'] and prev_candle_2['close'] < prev_candle_2['open']:
            is_reversal_context = True
    elif trend == 'put': # Procurando um Engolfo de Baixa
        # Exige que as 2 velas anteriores sejam de alta (verdes)
        if prev_candle_1['close'] > prev_candle_1['open'] and prev_candle_2['close'] > prev_candle_2['open']:
            is_reversal_context = True

    if not is_reversal_context:
        return None # Aborta se não houver um contexto claro de reversão

    # --- Filtro de Qualidade 2: Força do Engolfo ---
    is_strong_engulfing = False
    body_prev = abs(prev_candle_1['close'] - prev_candle_1['open'])
    body_signal = abs(signal_candle['close'] - signal_candle['open'])

    # Engolfo de Alta
    if trend == 'call' and signal_candle['close'] > signal_candle['open'] and prev_candle_1['close'] < prev_candle_1['open']:
        if signal_candle['close'] > prev_candle_1['max'] and signal_candle['open'] < prev_candle_1['min']:
            if body_signal > body_prev * 1.5: # Corpo da vela de sinal é 50% maior
                is_strong_engulfing = True
    
    # Engolfo de Baixa
    elif trend == 'put' and signal_candle['close'] < signal_candle['open'] and prev_candle_1['close'] > prev_candle_1['open']:
        if signal_candle['close'] < prev_candle_1['min'] and signal_candle['open'] > prev_candle_1['max']:
            if body_signal > body_prev * 1.5: # Corpo da vela de sinal é 50% maior
                is_strong_engulfing = True
    
    if not is_strong_engulfing:
        return None # Aborta se o engolfo não for forte o suficiente

    # --- Confluência Final com Suporte e Resistência ---
    if trend == 'call' and supports: # Engolfo de Alta
        for support_level in supports:
            if prev_candle_1['min'] <= support_level: # A vela engolfada tocou no suporte
                return 'call'

    if trend == 'put' and resistances: # Engolfo de Baixa
        for resistance_level in resistances:
            if prev_candle_1['max'] >= resistance_level: # A vela engolfada tocou na resistência
                return 'put'

    return None

def strategy_trend_flow(candles: list) -> Optional[str]:
    """Estratégia de fluxo a favor da tendência."""
    if len(candles) < 25: return None
    
    trend = check_ma_trend(candles)
    if not trend: return None
    
    # Verifica as últimas 3 velas
    last_three_candles = candles[-3:]
    
    if trend == 'call':
        if all(c['close'] > c['open'] for c in last_three_candles): # 3 velas verdes
            return 'call'
            
    if trend == 'put':
        if all(c['close'] < c['open'] for c in last_three_candles): # 3 velas vermelhas
            return 'put'

    return None

def detect_double_top_bottom(candles: list) -> Optional[str]:
    """Detecta padrões de Topo ou Fundo Duplo."""
    if len(candles) < 20: return None
    
    closes = pd.Series([c['close'] for c in candles])
    
    # Lógica simplificada para encontrar picos e vales
    peak_indices = (closes.shift(1) < closes) & (closes.shift(-1) < closes)
    valley_indices = (closes.shift(1) > closes) & (closes.shift(-1) > closes)
    
    peaks = closes[peak_indices].tail(2)
    valleys = closes[valley_indices].tail(2)

    # Topo Duplo
    if len(peaks) == 2:
        price_diff = abs(peaks.iloc[0] - peaks.iloc[1])
        if price_diff / peaks.iloc[0] < 0.001: # Picos com preços muito próximos (0.1%)
            return 'put'
    
    # Fundo Duplo
    if len(valleys) == 2:
        price_diff = abs(valleys.iloc[0] - valleys.iloc[1])
        if price_diff / valleys.iloc[0] < 0.001: # Vales com preços muito próximos
            return 'call'
    
    return None

def strategy_exhaustion_reversal(candles: list) -> Optional[str]:
    """Estratégia que combina exaustão do preço com padrões de reversão."""
    if len(candles) < 25: return None
    
    trend = check_ma_trend(candles)
    if not trend: return None

    # 1. Verifica Exaustão (3+ velas da mesma cor contra a tendência)
    exhaustion_direction = None
    if trend == 'call': # Tendência de alta, procura exaustão de venda
        if all(c['close'] < c['open'] for c in candles[-4:-1]): # 3 velas vermelhas seguidas
            exhaustion_direction = 'call' # Espera uma reversão para compra
            
    elif trend == 'put': # Tendência de baixa, procura exaustão de compra
        if all(c['close'] > c['open'] for c in candles[-4:-1]): # 3 velas verdes seguidas
            exhaustion_direction = 'put' # Espera uma reversão para venda
    
    if not exhaustion_direction: return None

    # 2. Confirma com Padrão de Reversão (Engolfo) ou Duplo Topo/Fundo
    double_pattern = detect_double_top_bottom(candles)
    if double_pattern == exhaustion_direction:
        return double_pattern # Sinal forte
    
    # Usa a lógica de engolfo, mas sem checar a tendência novamente
    signal_candle = candles[-1]
    prev_candle_1 = candles[-2]
    if exhaustion_direction == 'call':
        if signal_candle['close'] > signal_candle['open'] and prev_candle_1['close'] < prev_candle_1['open']:
            if signal_candle['close'] > prev_candle_1['max'] and signal_candle['open'] < prev_candle_1['min']:
                return 'call'
    
    if exhaustion_direction == 'put':
        if signal_candle['close'] < signal_candle['open'] and prev_candle_1['close'] > prev_candle_1['open']:
            if signal_candle['close'] < prev_candle_1['min'] and signal_candle['open'] > prev_candle_1['max']:
                return 'put'

    return None
