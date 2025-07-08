# analysis/technical.py
from typing import List, Tuple

# A classe Candle é a nossa estrutura de dados padrão.
# Ela converte um dicionário de dados em um objeto fácil de usar.
class Candle:
    def __init__(self, data):
        self.open = data.get('open')
        self.max = data.get('max')
        self.min = data.get('min')
        self.close = data.get('close')

# ATUALIZADO: Função agora converte os dados brutos em objetos Candle antes de analisar
def _find_sr_levels(candles_raw: List[dict], window_size: int) -> Tuple[List[float], List[float]]:
    """
    Encontra níveis de S/R com base em pontos de pivô.
    'window_size' define o número de velas à esquerda e à direita para validar um pivô.
    """
    # 1. CONVERSÃO: Transforma a lista de dicionários em uma lista de objetos Candle.
    # Isto garante que o resto da função funcione corretamente.
    candles = [Candle(c) for c in candles_raw]

    resistances = []
    supports = []

    # 2. Verifica se temos velas suficientes para a análise
    if len(candles) < (2 * window_size + 1):
        return [], []

    # 3. Itera pelas velas para encontrar pivôs
    for i in range(window_size, len(candles) - window_size):
        middle_candle = candles[i]
        
        # Garante que os dados da vela são válidos antes de comparar
        if not all([middle_candle.max, middle_candle.min]):
            continue

        # Verifica se é um pivô de alta (resistência)
        try:
            is_pivot_high = all(middle_candle.max > candles[i-j].max and middle_candle.max > candles[i+j].max for j in range(1, window_size + 1))
            if is_pivot_high:
                resistances.append(middle_candle.max)
        except (TypeError, AttributeError):
            continue # Ignora esta vela se houver dados inválidos nas vizinhas

        # Verifica se é um pivô de baixa (suporte)
        try:
            is_pivot_low = all(middle_candle.min < candles[i-j].min and middle_candle.min < candles[i+j].min for j in range(1, window_size + 1))
            if is_pivot_low:
                supports.append(middle_candle.min)
        except (TypeError, AttributeError):
            continue # Ignora esta vela se houver dados inválidos nas vizinhas

    unique_resistances = sorted(list(set(resistances)), reverse=True)
    unique_supports = sorted(list(set(supports)))

    return unique_resistances, unique_supports

def get_m15_sr_zones(m15_candles: List[dict]) -> Tuple[List[float], List[float]]:
    """
    Calcula as zonas de Suporte e Resistência com base nos candles de M15.
    """
    return _find_sr_levels(m15_candles, window_size=5)

def get_h1_sr_zones(h1_candles: List[dict]) -> Tuple[List[float], List[float]]:
    """
    Calcula as zonas de Suporte e Resistência com base nos candles de H1 (1 Hora).
    """
    return _find_sr_levels(h1_candles, window_size=8)
