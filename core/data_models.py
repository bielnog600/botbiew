from pydantic import BaseModel, computed_field
from typing import Optional

class Candle(BaseModel):
    """Modelo de dados para uma vela (candle)."""
    open: float
    close: float
    max: float
    min: float

    @computed_field
    @property
    def is_bullish(self) -> bool:
        return self.close > self.open

    @computed_field
    @property
    def is_bearish(self) -> bool:
        return self.close < self.open

class TradeSignal(BaseModel):
    """Representa um sinal de negociação gerado por uma estratégia."""
    pair: str
    direction: str
    strategy: str
    setup_candle_open: Optional[float] = None
    setup_candle_high: Optional[float] = None
    setup_candle_low: Optional[float] = None
    setup_candle_close: Optional[float] = None
