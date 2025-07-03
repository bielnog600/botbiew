# analysis/strategy.py
from typing import Protocol, List, Optional, Dict
from core.data_models import Candle
from analysis.technical import is_engulfing, is_near_level

class TradingStrategy(Protocol):
    name: str
    def analyze(self, m1_candles: List[Candle], m15_sr_zones: Dict[str, Optional[float]]) -> Optional[str]:
        ...

class M15ConfluenceEngulfStrategy(TradingStrategy):
    """
    Estratégia de Engolfo com Confluência em Zonas de S/R de M15.
    Lógica refinada pelo utilizador.
    """
    name = "m15_confluence_engulf"
    
    # Parâmetros da estratégia
    WICK_REQ_RATIO = 0.30  # Pavio deve ser pelo menos 30% do range
    BODY_LIMIT_RATIO = 0.40 # Corpo deve ser no máximo 40% do range

    def _is_valid_rejection(self, candle: Candle, *, top: bool) -> bool:
        """Verifica se uma vela é uma vela de rejeição válida."""
        rng = candle.max - candle.min
        if rng == 0: return False
        
        upper_wick = candle.max - max(candle.open, candle.close)
        lower_wick = min(candle.open, candle.close) - candle.min
        body = rng - (upper_wick + lower_wick)

        if top:
            return (upper_wick / rng >= self.WICK_REQ_RATIO) and (body / rng <= self.BODY_LIMIT_RATIO)
        else:
            return (lower_wick / rng >= self.WICK_REQ_RATIO) and (body / rng <= self.BODY_LIMIT_RATIO)

    def analyze(self, m1_candles: List[Candle], m15_sr_zones: Dict[str, Optional[float]]) -> Optional[str]:
        if len(m1_candles) < 3:
            return None

        setup_candle = m1_candles[-2]
        confirm_candle = m1_candles[-1]
        res_zone = m15_sr_zones.get("resistance")
        sup_zone = m15_sr_zones.get("support")

        # --- LÓGICA DE VENDA (PUT) ---
        if res_zone and is_near_level(setup_candle.max, res_zone, m1_candles):
            # Condições: setup é uma vela de alta, com rejeição de topo, e a vela seguinte é um engolfo de baixa.
            if setup_candle.is_bullish and self._is_valid_rejection(setup_candle, top=True):
                if is_engulfing(confirm_candle, setup_candle) == "BEARISH":
                    return "put"

        # --- LÓGICA DE COMPRA (CALL) ---
        if sup_zone and is_near_level(setup_candle.min, sup_zone, m1_candles):
            # Condições: setup é uma vela de baixa, com rejeição de fundo, e a vela seguinte é um engolfo de alta.
            if setup_candle.is_bearish and self._is_valid_rejection(setup_candle, top=False):
                if is_engulfing(confirm_candle, setup_candle) == "BULLISH":
                    return "call"
        
        return None

# Lista de estratégias ativas
STRATEGIES: List[TradingStrategy] = [
    M15ConfluenceEngulfStrategy(),
]
