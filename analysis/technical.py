# analysis/technical.py
from typing import List, Tuple

# Para que o editor de código entenda o tipo 'Candle',
# podemos importar ou definir uma estrutura simples.
# Se você tiver o TradeSignal em 'core.data_models', pode importar de lá.
class Candle:
    def __init__(self, data):
        self.open = data.get('open')
        self.max = data.get('max')
        self.min = data.get('min')
        self.close = data.get('close')
        self.volume = data.get('volume')

def _find_sr_levels(candles: List[Candle]) -> Tuple[List[float], List[float]]:
    """
    Função base para encontrar níveis de suporte e resistência
    usando a lógica de pontos de pivô.
    
    Args:
        candles: Uma lista de objetos Candle.
        
    Returns:
        Uma tupla contendo uma lista de resistências e uma lista de suportes.
    """
    resistances = []
    supports = []

    # Precisamos de pelo menos 3 velas para encontrar um pivô (esquerda, meio, direita)
    if len(candles) < 3:
        return [], []

    # Iteramos pelas velas, pulando a primeira e a última
    for i in range(1, len(candles) - 1):
        left_candle = candles[i-1]
        middle_candle = candles[i]
        right_candle = candles[i+1]

        # Verifica por um pivô de alta (ponto de resistência)
        if middle_candle.max > left_candle.max and middle_candle.max > right_candle.max:
            resistances.append(middle_candle.max)

        # Verifica por um pivô de baixa (ponto de suporte)
        if middle_candle.min < left_candle.min and middle_candle.min < right_candle.min:
            supports.append(middle_candle.min)

    # Remove duplicatas e ordena os níveis
    # A resistência é ordenada do maior para o menor
    # O suporte é ordenado do menor para o maior
    unique_resistances = sorted(list(set(resistances)), reverse=True)
    unique_supports = sorted(list(set(supports)))

    return unique_resistances, unique_supports

def get_m15_sr_zones(m15_candles: List[Candle]) -> Tuple[List[float], List[float]]:
    """
    Calcula as zonas de Suporte e Resistência com base nos candles de M15.
    
    Args:
        m15_candles: Uma lista de candles de M15.
        
    Returns:
        Uma tupla (resistências, suportes).
    """
    return _find_sr_levels(m15_candles)

# NOVO: Função para obter S/R de H1, necessária para a análise de M5
def get_h1_sr_zones(h1_candles: List[Candle]) -> Tuple[List[float], List[float]]:
    """
    Calcula as zonas de Suporte e Resistência com base nos candles de H1 (1 Hora).
    A lógica de cálculo é a mesma de M15, apenas aplicada a um timeframe maior.
    
    Args:
        h1_candles: Uma lista de candles de H1.
        
    Returns:
        Uma tupla (resistências, suportes).
    """
    # A lógica é reutilizada, garantindo consistência
    return _find_sr_levels(h1_candles)
