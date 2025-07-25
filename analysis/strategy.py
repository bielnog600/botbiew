import pandas as pd
from typing import List, Dict, Optional

# Nota: Estas funções foram adaptadas do seu script botsock.py e otimizadas.

def sma_slope(closes: List[float], period: int) -> Optional[bool]:
    """
    Verifica se a inclinação da Média Móvel Simples (SMA) é positiva.
    Retorna True para inclinação de alta, False para baixa, None se for impossível calcular.
    """
    if len(closes) < period + 1:
        return None
    
    # Calcula a SMA para os dois últimos pontos para determinar a inclinação
    sma_penultimate = sum(closes[-(period + 1):-1]) / period
    sma_last = sum(closes[-period:]) / period

    if sma_last > sma_penultimate:
        return True  # Inclinação de alta (uptrend)
    elif sma_last < sma_penultimate:
        return False # Inclinação de baixa (downtrend)
    return None # Sem inclinação (flat)

def detect_fractals(candles: List[Dict], max_levels: int = 5) -> tuple[list, list]:
    """Detecta os últimos 'max_levels' fractais de alta (resistência) e baixa (suporte)."""
    highs = [v['max'] for v in candles]
    lows = [v['min'] for v in candles]
    
    resistances = []
    supports = []
    
    # Percorre as velas do fim para o início para encontrar os fractais mais recentes primeiro
    for i in range(len(candles) - 3, 2, -1):
        # Fractal de alta: máxima é maior que as 2 velas vizinhas de cada lado
        if highs[i] > max(highs[i-2:i] + highs[i+1:i+3]):
            if len(resistances) < max_levels:
                resistances.append(highs[i])

        # Fractal de baixa: mínima é menor que as 2 velas vizinhas de cada lado
        if lows[i] < min(lows[i-2:i] + lows[i+1:i+3]):
            if len(supports) < max_levels:
                supports.append(lows[i])
        
        if len(resistances) >= max_levels and len(supports) >= max_levels:
            break # Para a busca se já encontrou o número suficiente de níveis
            
    return resistances, supports

def strategy_mql_pullback(candles: List[Dict]) -> Optional[str]:
    """
    Estratégia de Pullback em zonas de fractais, a favor de uma micro-tendência de SMA.
    """
    params = {'MAPeriod': 5, 'MaxLevels': 5, 'Proximity': 7.0, 'Point': 1e-5}
    closes = [v['close'] for v in candles]

    if len(candles) < params['MAPeriod'] + 2:
        return None
        
    is_uptrend = sma_slope(closes, params['MAPeriod'])
    if is_uptrend is None:
        return None

    res_levels, sup_levels = detect_fractals(candles, params['MaxLevels'])
    last_candle = candles[-1]

    if is_uptrend and sup_levels:
        # Tendência de alta, procura pullback em suporte
        target_price = sup_levels[0] + params['Proximity'] * params['Point']
        if last_candle['min'] <= target_price and last_candle['close'] >= sup_levels[0]:
            return 'call'
            
    if not is_uptrend and res_levels:
        # Tendência de baixa, procura pullback em resistência
        target_price = res_levels[0] - params['Proximity'] * params['Point']
        if last_candle['max'] >= target_price and last_candle['close'] <= res_levels[0]:
            return 'put'
            
    return None

def strategy_reversal_pattern(candles: List[Dict]) -> Optional[str]:
    """
    Estratégia que procura por padrões de Engolfo de Alta/Baixa.
    """
    if len(candles) < 2:
        return None
        
    penultimate = candles[-2]
    last = candles[-1]
    
    # Engolfo de Alta: vela de alta "engole" a vela de baixa anterior
    is_bullish_engulfing = (penultimate['close'] < penultimate['open'] and 
                           last['close'] > last['open'] and 
                           last['close'] > penultimate['open'] and 
                           last['open'] < penultimate['close'])
    if is_bullish_engulfing:
        return 'call'
        
    # Engolfo de Baixa: vela de baixa "engole" a vela de alta anterior
    is_bearish_engulfing = (penultimate['close'] > penultimate['open'] and 
                           last['close'] < last['open'] and 
                           last['close'] < penultimate['open'] and 
                           last['open'] > penultimate['close'])
    if is_bearish_engulfing:
        return 'put'
        
    return None

def strategy_trend_flow(candles: List[Dict]) -> Optional[str]:
    """
    Estratégia de fluxo que opera a favor de 3 velas consecutivas da mesma cor.
    """
    if len(candles) < 3:
        return None
        
    last_three = candles[-3:]
    
    # Verifica se as 3 últimas velas são de alta
    if all(v['close'] > v['open'] for v in last_three):
        return 'call'
        
    # Verifica se as 3 últimas velas são de baixa
    if all(v['close'] < v['open'] for v in last_three):
        return 'put'
        
    return None
