from typing import List, Tuple
from core.data_models import Candle


def get_m15_sr_zones(m15_candles: List[Candle]) -> Tuple[List[float], List[float]]:
    """
    Calcula zonas de Suporte e Resistência a partir de candles de 15 minutos.
    Retorna duas listas: (resistance_levels, support_levels).
    Exemplo simples: picos e vales recentes.
    """
    highs = [candle.max for candle in m15_candles]
    lows = [candle.min for candle in m15_candles]
    # Pegue os dois níveis mais altos como resistências, e dois mais baixos como suportes
    sorted_highs = sorted(set(highs), reverse=True)
    sorted_lows = sorted(set(lows))
    resistance = sorted_highs[:2]
    support = sorted_lows[:2]
    return resistance, support
