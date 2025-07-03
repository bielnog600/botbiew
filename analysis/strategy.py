# analysis/strategy.py
from typing import Protocol, List, Optional, Dict
from core.data_models import Candle
from analysis.technical import (
    is_rejection_candle,
    is_engulfing,
    is_near_level
)

class TradingStrategy(Protocol):
    name: str
    def analyze(self, m1_candles: List[Candle], m15_sr_zones: Dict[str, Optional[float]]) -> Optional[str]:
        ...

class M15ConfluenceEngulfStrategy(TradingStrategy):
    """
    Estratégia de Engolfo com Confluência em Zonas de S/R de M15,
    usando a lógica de análise refinada pelo utilizador.
    """
    name = "m15_confluence_engulf"

    def analyze(self, m1_candles: List[Candle], m15_sr_zones: Dict[str, Optional[float]]) -> Optional[str]:
        if len(m1_candles) < 3: # Precisa de pelo menos 2 velas para a análise + histórico
            return None

        setup_candle = m1_candles[-2]
        confirm_candle = m1_candles[-1]
        res_zone = m15_sr_zones.get("resistance")
        sup_zone = m15_sr_zones.get("support")

        # --- LÓGICA DE VENDA (PUT) ---
        if res_zone and is_near_level(setup_candle.max, res_zone, m1_candles):
            # Condições: A vela de setup é de alta, tem rejeição de topo, e a vela seguinte é um engolfo de baixa.
            if setup_candle.is_bullish and is_rejection_candle(setup_candle) == "TOP":
                if is_engulfing(confirm_candle, setup_candle) == "BEARISH":
                    return "put"

        # --- LÓGICA DE COMPRA (CALL) ---
        if sup_zone and is_near_level(setup_candle.min, sup_zone, m1_candles):
            # Condições: A vela de setup é de baixa, tem rejeição de fundo, e a vela seguinte é um engolfo de alta.
            if setup_candle.is_bearish and is_rejection_candle(setup_candle) == "BOTTOM":
                if is_engulfing(confirm_candle, setup_candle) == "BULLISH":
                    return "call"
        
        return None

# Lista de estratégias ativas
STRATEGIES: List[TradingStrategy] = [
    M15ConfluenceEngulfStrategy(),
]
