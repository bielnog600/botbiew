# analysis/technical.py
from typing import List, Tuple

# Se você tiver uma definição central de Candle em 'core.data_models',
# é melhor importá-la de lá para evitar duplicação.
# from core.data_models import Candle
class Candle:
    def __init__(self, data):
        self.open = data.get('open')
        self.max = data.get('max')
        self.min = data.get('min')
        self.close = data.get('close')
        # CORRIGIDO: Removida a referência ao volume, que não é usado e pode causar erros.
        # self.volume = data.get('volume') 

def _find_sr_levels(candles: List[Candle]) -> Tuple[List[float], List[float]]:
    """
    Função base para encontrar níveis de suporte e resistência
    usando a lógica de pontos de pivô.
    """
    resistances = []
    supports = []

    if len(candles) < 3:
        return [], []

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

    unique_resistances = sorted(list(set(resistances)), reverse=True)
    unique_supports = sorted(list(set(supports)))

    return unique_resistances, unique_supports

def get_m15_sr_zones(m15_candles: List[Candle]) -> Tuple[List[float], List[float]]:
    """
    Calcula as zonas de Suporte e Resistência com base nos candles de M15.
    """
    return _find_sr_levels(m15_candles)

def get_h1_sr_zones(h1_candles: List[Candle]) -> Tuple[List[float], List[float]]:
    """
    Calcula as zonas de Suporte e Resistência com base nos candles de H1 (1 Hora).
    """
    return _find_sr_levels(h1_candles)
