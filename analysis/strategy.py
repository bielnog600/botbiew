# analysis/strategy.py
from typing import Protocol, List, Optional, Tuple
from core.data_models import Candle, TradeSignal
from analysis.technical import get_sma_slope

class TradingStrategy(Protocol):
    """Define a interface para todas as estratégias de negociação."""
    name: str
    def analyze(self, candles: List[Candle]) -> Optional[str]:
        ...

class FlowStrategy:
    name = "flow"

    def analyze(self, candles: List[Candle]) -> Optional[str]:
        if len(candles) < 15:
            return None

        closes = [c.close for c in candles]
        slope = get_sma_slope(closes, period=14)
        last_three = candles[-3:]

        if slope > 0 and all(c.close > c.open for c in last_three):
            return "call"
        if slope < 0 and all(c.close < c.open for c in last_three):
            return "put"
        return None

# Adicione outras estratégias (MQL, Patterns) aqui, seguindo o mesmo padrão.
# Exemplo: class MQLPullbackStrategy: ...

# Lista de todas as estratégias disponíveis para o bot
STRATEGIES = [FlowStrategy()]
