# analysis/strategy.py
from typing import Protocol, List, Optional, Dict
from core.data_models import Candle
from analysis.technical import (
    get_m15_sr_zones,
    touches_zone,
    is_engulfing,
    calculate_ema,
    is_strong_candle
)

class TradingStrategy(Protocol):
    name: str
    def analyze(self, m1_candles: List[Candle], m15_sr_zones: Dict[str, Optional[float]]) -> Optional[str]:
        ...

class M15ConfluenceEngulfStrategy(TradingStrategy):
    name = "m15_confluence_engulf"
    WICK_REQ_RATIO = 0.30
    BODY_LIMIT_RATIO = 0.40

    def _is_valid_rejection(self, candle: Candle) -> bool:
        rng = candle.max - candle.min
        if rng == 0: return False
        upper_wick = candle.max - max(candle.open, candle.close)
        lower_wick = min(candle.open, candle.close) - candle.min
        body = rng - (upper_wick + lower_wick)
        
        is_top_rejection = (upper_wick / rng >= self.WICK_REQ_RATIO) and (body / rng <= self.BODY_LIMIT_RATIO)
        is_bottom_rejection = (lower_wick / rng >= self.WICK_REQ_RATIO) and (body / rng <= self.BODY_LIMIT_RATIO)
        
        return is_top_rejection or is_bottom_rejection

    def analyze(self, m1_candles: List[Candle], m15_sr_zones: Dict[str, Optional[float]]) -> Optional[str]:
        if len(m1_candles) < 3: return None

        setup_candle = m1_candles[-2]
        confirm_candle = m1_candles[-1]
        res_zone = m15_sr_zones.get("resistance")
        sup_zone = m15_sr_zones.get("support")

        if res_zone and touches_zone(setup_candle.max, res_zone) and setup_candle.is_bullish and self._is_valid_rejection(setup_candle):
            if is_engulfing(confirm_candle, setup_candle) == "BEARISH":
                return "put"

        if sup_zone and touches_zone(setup_candle.min, sup_zone) and setup_candle.is_bearish and self._is_valid_rejection(setup_candle):
            if is_engulfing(confirm_candle, setup_candle) == "BULLISH":
                return "call"
        
        return None

class RestCandleEngulfStrategy(TradingStrategy):
    name = "rest_candle_engulf"
    rest_body_max = 0.25
    trend_len = 3
    engulf_conf_len = 2

    def analyze(self, m1_candles: List[Candle], *_):
        if len(m1_candles) < self.trend_len + self.engulf_conf_len:
            return None

        trend = m1_candles[-(self.trend_len + self.engulf_conf_len):-self.engulf_conf_len]
        if not all(c.is_bullish for c in trend) and not all(c.is_bearish for c in trend):
            return None

        rest = m1_candles[-2]
        conf = m1_candles[-1]
        rng = rest.max - rest.min
        body = abs(rest.close - rest.open)
        if rng == 0 or body / rng > self.rest_body_max:
            return None

        eng_type = is_engulfing(conf, rest)
        if all(c.is_bullish for c in trend) and eng_type == "BULLISH":
            return "call"
        if all(c.is_bearish for c in trend) and eng_type == "BEARISH":
            return "put"
        return None

class EmaPullbackStrategy(TradingStrategy):
    name = "ema20_pullback"
    ema_period = 20
    min_impulse = 4

    def analyze(self, m1_candles: List[Candle], *_):
        if len(m1_candles) < self.ema_period + self.min_impulse + 1:
            return None

        closes = [c.close for c in m1_candles]
        ema = calculate_ema(closes, self.ema_period)
        setup = m1_candles[-2]
        if not (setup.min <= ema <= setup.max):
            return None

        impulse = m1_candles[-(self.min_impulse + 2):-2]
        if not all(c.is_bullish for c in impulse) and not all(c.is_bearish for c in impulse):
            return None

        confirm = m1_candles[-1]
        if all(c.is_bullish for c in impulse) and confirm.is_bullish:
            return "call"
        if all(c.is_bearish for c in impulse) and confirm.is_bearish:
            return "put"
        return None

class ThreeBarMomentumStrategy(TradingStrategy):
    name = "three_bar_momentum"
    streak = 3

    def analyze(self, m1_candles: List[Candle], m15_sr_zones: Dict[str, Optional[float]]) -> Optional[str]:
        if len(m1_candles) < self.streak:
            return None

        last_n = m1_candles[-self.streak:]
        if all(c.is_bullish for c in last_n):
            if touches_zone(last_n[-1].max, m15_sr_zones.get("resistance")):
                return None
            return "call"
        elif all(c.is_bearish for c in last_n):
            if touches_zone(last_n[-1].min, m15_sr_zones.get("support")):
                return None
            return "put"
        return None

# Lista de todas as estratégias disponíveis para o bot
STRATEGIES: List[TradingStrategy] = [
    M15ConfluenceEngulfStrategy(),
    RestCandleEngulfStrategy(),
    EmaPullbackStrategy(),
    ThreeBarMomentumStrategy(),
]
