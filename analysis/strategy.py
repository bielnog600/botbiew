# analysis/strategy.py
from typing import Protocol, List, Optional, Dict, Tuple, Union
from core.data_models import Candle
from analysis.technical import is_rejection_candle, is_engulfing

Price = float
Zone   = Union[Price, Tuple[Price, Price]]

def touches_zone(price: float, zone: Zone, tol: float = 0.00005) -> bool:
    """Verifica se um preço toca (±tol) uma zona que pode ser float ou (low, high)."""
    if isinstance(zone, tuple):
        low, high = zone
        return low - tol <= price <= high + tol
    return abs(price - zone) <= tol

def average_wick_ratio(candles: List[Candle]) -> float:
    """Retorna média (pavio_total / tamanho_total) das velas fornecidas."""
    ratios = []
    for c in candles:
        wick = (c.max - max(c.open, c.close)) + (min(c.open, c.close) - c.min)
        ratios.append(wick / (c.max - c.min) if c.max != c.min else 0)
    return sum(ratios) / len(ratios)

class TradingStrategy(Protocol):
    name: str
    def analyze(self, m1_candles: List[Candle], m15_sr_zones: Dict[str, Zone]) -> Optional[Dict]: ...

class M15ConfluenceEngulfStrategy:
    name = "m15_confluence_engulf"
    wick_req   = 0.30   # 30 %
    body_limit = 0.40   # ≤40 % do range para ser “corpo pequeno”
    max_volatility_ratio = 0.60  # média pavio/total nas 3 velas ≤ 60 %

    def analyze(
        self, m1_candles: List[Candle], m15_sr_zones: Dict[str, Zone]
    ) -> Optional[Dict]:
        if len(m1_candles) < 5:
            return None

        # Filtro de volatilidade
        if average_wick_ratio(m1_candles[-4:-1]) > self.max_volatility_ratio:
            return None

        setup     = m1_candles[-2]
        confirm   = m1_candles[-1]
        res_zone  = m15_sr_zones.get("resistance")
        sup_zone  = m15_sr_zones.get("support")

        # --- VENDA (PUT) ---
        if res_zone and touches_zone(setup.max, res_zone):
            if setup.is_bullish and self._valid_rejection(setup, top=True):
                if is_engulfing(confirm, setup) == "BEARISH":
                    return {
                        "signal": "put",
                        "reason": "bearish_engulf_m15_res",
                        "at_price": confirm.open,
                    }

        # --- COMPRA (CALL) ---
        if sup_zone and touches_zone(setup.min, sup_zone):
            if setup.is_bearish and self._valid_rejection(setup, top=False):
                if is_engulfing(confirm, setup) == "BULLISH":
                    return {
                        "signal": "call",
                        "reason": "bullish_engulf_m15_sup",
                        "at_price": confirm.open,
                    }
        return None

    # ------------- helpers -----------------
    def _valid_rejection(self, candle: Candle, *, top: bool) -> bool:
        """Checa pavio ≥30 % e corpo ≤40 % do range total."""
        rng  = candle.max - candle.min
        if rng == 0:
            return False
        upper_wick = candle.max - max(candle.open, candle.close)
        lower_wick = min(candle.open, candle.close) - candle.min
        body       = rng - (upper_wick + lower_wick)

        if top:
            return (upper_wick / rng >= self.wick_req) and (body / rng <= self.body_limit)
        else:
            return (lower_wick / rng >= self.wick_req) and (body / rng <= self.body_limit)


# Estratégias ativas
STRATEGIES: List[TradingStrategy] = [
    M15ConfluenceEngulfStrategy(),
]
