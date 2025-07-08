# analysis/technical.py
from typing import List, Tuple

class Candle:
    def __init__(self, data):
        self.open = data.get('open')
        self.max = data.get('max')
        self.min = data.get('min')
        self.close = data.get('close')

# ATUALIZADO: Função agora aceita um 'window_size' para definir a força do pivô
def _find_sr_levels(candles: List[Candle], window_size: int) -> Tuple[List[float], List[float]]:
    """
    Encontra níveis de S/R com base em pontos de pivô.
    'window_size' define o número de velas à esquerda e à direita para validar um pivô.
    Um valor maior resulta em menos níveis, porém mais fortes.
    """
    resistances = []
    supports = []

    if len(candles) < (2 * window_size + 1):
        return [], []

    # O loop agora respeita a janela para não dar erro de índice
    for i in range(window_size, len(candles) - window_size):
        middle_candle = candles[i]
        
        # Verifica se é um pivô de alta (resistência)
        is_pivot_high = all(middle_candle.max > candles[i-j].max and middle_candle.max > candles[i+j].max for j in range(1, window_size + 1))
        if is_pivot_high:
            resistances.append(middle_candle.max)

        # Verifica se é um pivô de baixa (suporte)
        is_pivot_low = all(middle_candle.min < candles[i-j].min and middle_candle.min < candles[i+j].min for j in range(1, window_size + 1))
        if is_pivot_low:
            supports.append(middle_candle.min)

    unique_resistances = sorted(list(set(resistances)), reverse=True)
    unique_supports = sorted(list(set(supports)))

    return unique_resistances, unique_supports

# ATUALIZADO: Agora você pode configurar a força do S/R para cada timeframe aqui
def get_m15_sr_zones(m15_candles: List[Candle]) -> Tuple[List[float], List[float]]:
    """
    Calcula as zonas de S/R para M15.
    Altere o 'window_size' para ajustar a sensibilidade.
    Valores recomendados: 3 a 7
    """
    return _find_sr_levels(m15_candles, window_size=5)

def get_h1_sr_zones(h1_candles: List[Candle]) -> Tuple[List[float], List[float]]:
    """
    Calcula as zonas de S/R para H1.
    Altere o 'window_size' para ajustar a sensibilidade.
    Valores recomendados: 5 a 10
    """
    return _find_sr_levels(h1_candles, window_size=8)
