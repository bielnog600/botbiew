# analysis/strategy.py
from typing import Protocol, List, Optional, Dict
from core.data_models import Candle
from analysis.technical import (
    is_rejection_candle,
    is_engulfing
)

class TradingStrategy(Protocol):
    """Define a interface para todas as estratégias de negociação."""
    name: str
    def analyze(self, m1_candles: List[Candle], m15_sr_zones: Dict) -> Optional[str]:
        ...

class M15ConfluenceEngulfStrategy(TradingStrategy):
    """
    Estratégia de Engolfo com Confluência em Zonas de S/R de M15.
    1. Contexto: Identifica uma zona de S/R em M15.
    2. Rejeição: Espera uma vela M1 tocar essa zona e mostrar rejeição.
    3. Confirmação: Entra após uma vela de engolfo que confirma a reversão.
    """
    name = "m15_confluence_engulf"

    def analyze(self, m1_candles: List[Candle], m15_sr_zones: Dict) -> Optional[str]:
        if len(m1_candles) < 2:
            return None

        resistance_zone = m15_sr_zones.get('resistance')
        support_zone = m15_sr_zones.get('support')
        
        # A vela de setup é a penúltima, a de confirmação é a última
        setup_candle = m1_candles[-2]
        confirmation_candle = m1_candles[-1]

        # --- LÓGICA DE VENDA (PUT) ---
        if resistance_zone:
            # Condição 1: A vela de setup tocou a resistência de M15
            touched_resistance = setup_candle.max >= resistance_zone
            # Condição 2: A vela de setup mostrou rejeição de topo
            rejection_type = is_rejection_candle(setup_candle)
            # Condição 3: A vela seguinte é um engolfo de baixa
            engulfing_type = is_engulfing(confirmation_candle, setup_candle)

            if touched_resistance and rejection_type == "TOP" and engulfing_type == "BEARISH":
                return "put"

        # --- LÓGICA DE COMPRA (CALL) ---
        if support_zone:
            # Condição 1: A vela de setup tocou o suporte de M15
            touched_support = setup_candle.min <= support_zone
            # Condição 2: A vela de setup mostrou rejeição de fundo
            rejection_type = is_rejection_candle(setup_candle)
            # Condição 3: A vela seguinte é um engolfo de alta
            engulfing_type = is_engulfing(confirmation_candle, setup_candle)

            if touched_support and rejection_type == "BOTTOM" and engulfing_type == "BULLISH":
                return "call"

        return None

# Lista de estratégias ativas. Focada na nossa nova estratégia principal.
STRATEGIES: List[TradingStrategy] = [
    M15ConfluenceEngulfStrategy(),
]
