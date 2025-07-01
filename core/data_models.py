# core/data_models.py
from pydantic import BaseModel
from typing import Optional

class Candle(BaseModel):
    """
    Modelo de dados para uma vela (candle).
    """
    open: float
    close: float
    max: float # Corrigido de 'high' para 'max'
    min: float # Corrigido de 'low' para 'min'

class TradeSignal(BaseModel):
    """
    Representa um sinal de negociação gerado por uma estratégia.
    """
    asset: str
    direction: str # 'call' ou 'put'
    strategy: str
    volatility_score: float

class ActiveTrade(BaseModel):
    """
    Representa uma operação ativa na plataforma.
    """
    order_id: str
    signal_id: int
    asset: str
