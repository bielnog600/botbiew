import pytest
from analysis.strategy import ThreeBarMomentum, M15ConfluenceEngulf
from core.data_models import Candle

# Fixtures for candles
@pytest.fixture
def bullish_candle():
    return Candle(open=1.0, close=1.2, max=1.2, min=1.0)

@pytest.fixture
def bearish_candle():
    return Candle(open=1.2, close=1.0, max=1.2, min=1.0)

# Tests for ThreeBarMomentum
@pytest.mark.parametrize("candles, expected", [
    ([Candle(open=1, close=2, max=2, min=1) for _ in range(3)], 'CALL'),
    ([Candle(open=2, close=1, max=2, min=1) for _ in range(3)], 'PUT'),
    ([Candle(open=1, close=2, max=2, min=1), Candle(open=2, close=1, max=2, min=1), Candle(open=1, close=2, max=2, min=1)], None),
])
def test_three_bar_momentum(candles, expected):
    strat = ThreeBarMomentum()
    result = strat.analyze(candles, {})
    assert result == expected

# Tests for M15ConfluenceEngulf
@pytest.mark.parametrize("last_candle, zones, expected", [
    # Bullish engulfing support
    (
        Candle(open=0.9, close=1.1, max=1.1, min=0.9),
        {'resistance': [2.0], 'support': [1.0]},
        'CALL'
    ),
    # Bearish engulfing resistance
    (
        Candle(open=1.1, close=0.9, max=1.1, min=0.9),
        {'resistance': [1.0], 'support': [0.5]},
        'PUT'
    ),
    # No confluence
    (
        Candle(open=1.0, close=1.05, max=1.05, min=1.0),
        {'resistance': [1.2], 'support': [0.8]},
        None
    ),
])
def test_m15_confluence_engulf(last_candle, zones, expected):
    strat = M15ConfluenceEngulf()
    # Provide dummy m1 list ending with last_candle
    result = strat.analyze([last_candle], zones)
    assert result == expected
