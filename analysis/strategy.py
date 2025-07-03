from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from core.data_models import Candle

class Strategy(ABC):
    """Interface para todas as estratégias de trading."""
    name: str

    @abstractmethod
    def analyze(
        self,
        m1_candles: List[Candle],
        m15_zones: Dict[str, List[float]]
    ) -> Optional[str]:
        """
        Analisa as candles de 1min e zonas de 15min,
        retornando 'CALL', 'PUT' ou None se não houver sinal.
        """
        pass

class ThreeBarMomentum(Strategy):
    name = 'three_bar_momentum'

    def analyze(
        self,
        m1_candles: List[Candle],
        m15_zones: Dict[str, List[float]]
    ) -> Optional[str]:
        # Exemplo: se as últimas três candles forem bullish, sinal de CALL
        if len(m1_candles) < 3:
            return None
        last3 = m1_candles[-3:]
        if all(candle.is_bullish for candle in last3):
            return 'CALL'
        if all(candle.is_bearish for candle in last3):
            return 'PUT'
        return None

class M15ConfluenceEngulf(Strategy):
    name = 'm15_confluence_engulf'

    def analyze(
        self,
        m1_candles: List[Candle],
        m15_zones: Dict[str, List[float]]
    ) -> Optional[str]:
        # Exemplo simples: se última candle engolfar suportes de M15
        if not m1_candles:
            return None
        last = m1_candles[-1]
        resistance = m15_zones.get('resistance', [])
        support = m15_zones.get('support', [])
        # Exemplo fictício de confluência
        if last.is_bullish and last.open < support[-1] < last.close:
            return 'CALL'
        if last.is_bearish and last.open > resistance[-1] > last.close:
            return 'PUT'
        return None

# Registro das estratégias disponíveis
STRATEGIES: List[Strategy] = [
    ThreeBarMomentum(),
    M15ConfluenceEngulf(),
]
