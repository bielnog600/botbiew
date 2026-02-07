# analysis/technical.py
from typing import List, Tuple, Dict

# A classe Candle foi removida para trabalhar diretamente com dicionários
# que vêm da API, o que é mais robusto.

def _find_sr_levels(candles: List[Dict], window_size: int) -> Tuple[List[float], List[float]]:
    """
    Encontra níveis de S/R com base em pontos de pivô.
    'window_size' define o número de velas à esquerda e à direita para validar um pivô.
    """
    resistances = []
    supports = []

    if len(candles) < (2 * window_size + 1):
        return [], []

    for i in range(window_size, len(candles) - window_size):
        middle_candle = candles[i]
        
        # Garante que os dados da vela são válidos antes de comparar
        if not all(key in middle_candle for key in ['max', 'min']):
            continue

        try:
            # CORRIGIDO: Usa a sintaxe de dicionário ['max'] e ['min']
            is_pivot_high = all(middle_candle['max'] > candles[i-j]['max'] and middle_candle['max'] > candles[i+j]['max'] for j in range(1, window_size + 1))
            if is_pivot_high:
                resistances.append(middle_candle['max'])

            is_pivot_low = all(middle_candle['min'] < candles[i-j]['min'] and middle_candle['min'] < candles[i+j]['min'] for j in range(1, window_size + 1))
            if is_pivot_low:
                supports.append(middle_candle['min'])
        except (TypeError, KeyError):
            # Ignora esta vela se houver dados inválidos nas vizinhas
            continue

    unique_resistances = sorted(list(set(resistances)), reverse=True)
    unique_supports = sorted(list(set(supports)))

    return unique_resistances, unique_supports

def get_m15_sr_zones(m15_candles: List[Dict]) -> Tuple[List[float], List[float]]:
    """
    Calcula as zonas de Suporte e Resistência com base nos candles de M15.
    """
    return _find_sr_levels(m15_candles, window_size=5)

def get_h1_sr_zones(h1_candles: List[Dict]) -> Tuple[List[float], List[float]]:
    """
    Calcula as zonas de Suporte e Resistência com base nos candles de H1 (1 Hora).
    """
    return _find_sr_levels(h1_candles, window_size=8)
