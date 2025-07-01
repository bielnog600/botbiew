# analysis/technical.py
from typing import List, Tuple
from core.data_models import Candle

def calculate_sma(closes: List[float], period: int) -> float:
    """Calcula a Média Móvel Simples."""
    if len(closes) < period:
        return 0.0
    return sum(closes[-period:]) / period

def get_sma_slope(closes: List[float], period: int) -> float:
    """Calcula a inclinação da SMA, indicando a nano-tendência."""
    if len(closes) < period + 2: # Precisa de pelo menos dois pontos para a inclinação
        return 0.0
    
    # Usamos slices para evitar recalcular a lista inteira
    sma1 = sum(closes[-(period+1):-1]) / period
    sma2 = sum(closes[-period:]) / period
    
    # Retorna a diferença, que representa a inclinação
    return sma2 - sma1

def calculate_volatility(candles: List[Candle], lookback: int) -> float:
    """
    Calcula uma pontuação de volatilidade (0-1).
    Valores mais altos indicam mais "nervosismo" (pavios longos).
    """
    if len(candles) < lookback:
        return 1.0

    recent_candles = candles[-lookback:]
    total_range = 0
    total_body = 0

    for c in recent_candles:
        candle_range = c.max - c.min
        if candle_range > 0:
            total_range += candle_range
            total_body += abs(c.close - c.open)

    if total_range == 0:
        return 0.0

    wick_proportion = (total_range - total_body) / total_range
    return wick_proportion

def detect_sr_levels(candles: List[Candle], n_levels: int = 5) -> Tuple[List[float], List[float]]:
    """
    Detecta os níveis de Suporte e Resistência mais recentes usando fractais.
    Retorna (resistance_levels, support_levels).
    """
    if len(candles) < 5:
        return [], []

    highs = [c.max for c in candles]
    lows = [c.min for c in candles]
    
    resistance_levels = []
    support_levels = []

    # Itera pelas velas, ignorando as duas primeiras e as duas últimas
    for i in range(2, len(candles) - 2):
        # Fractal de Topo (Resistência)
        if highs[i] > highs[i-1] and highs[i] > highs[i-2] and highs[i] > highs[i+1] and highs[i] > highs[i+2]:
            resistance_levels.append(highs[i])
        
        # Fractal de Fundo (Suporte)
        if lows[i] < lows[i-1] and lows[i] < lows[i-2] and lows[i] < lows[i+1] and lows[i] < lows[i+2]:
            support_levels.append(lows[i])
            
    # Retorna os 'n' níveis mais recentes (os últimos encontrados)
    return sorted(resistance_levels, reverse=True)[:n_levels], sorted(support_levels, reverse=True)[:n_levels]

def is_near_level(price: float, levels: List[float], candles: List[Candle]) -> bool:
    """
    Verifica se um preço está próximo de algum dos níveis fornecidos.
    A proximidade é definida dinamicamente com base no tamanho médio das velas.
    """
    if not levels or not candles:
        return False
    
    # Calcula o "Average True Range" (ATR) simplificado para definir a proximidade
    avg_candle_size = sum(c.max - c.min for c in candles[-10:]) / 10
    proximity = avg_candle_size * 0.25 # 25% do tamanho médio da vela

    for level in levels:
        if abs(price - level) <= proximity:
            return True
    return False
