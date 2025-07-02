# core/data_models.py
from pydantic import BaseModel
from typing import Optional

class Candle(BaseModel):
    """Modelo de dados para uma vela (candle)."""
    open: float
    close: float
    max: float
    min: float

class TradeSignal(BaseModel):
    """Representa um sinal de negociação gerado por uma estratégia."""
    pair: str
    direction: str
    strategy: str
    volatility_score: Optional[float] = None
    setup_candle_open: Optional[float] = None
    setup_candle_high: Optional[float] = None
    setup_candle_low: Optional[float] = None
    setup_candle_close: Optional[float] = None

class ActiveTrade(BaseModel):
    """Representa uma operação ativa na plataforma."""
    order_id: str
    signal_id: int
    pair: str
    entry_value: float
    # FIX: Adicionado o campo para guardar o saldo antes da operação.
    balance_before: float
