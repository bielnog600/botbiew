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
    # FIX: Alterado de 'asset' para 'pair' para corresponder ao banco de dados.
    pair: str
    direction: str # 'call' ou 'put'
    strategy: str
    volatility_score: float

class ActiveTrade(BaseModel):
    """Representa uma operação ativa na plataforma."""
    order_id: str
    signal_id: int
    # FIX: Alterado de 'asset' para 'pair' para consistência.
    pair: str
    entry_value: float
