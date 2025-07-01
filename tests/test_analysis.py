# tests/test_analysis.py
import pytest
from analysis.technical import calculate_volatility, get_sma_slope
from analysis.strategy import FlowStrategy
from core.data_models import Candle

# Exemplo de dados de velas para os testes
@pytest.fixture
def sample_candles_trending_up():
    """Gera uma lista de velas com tendência de alta."""
    return [Candle(open=1+i*0.1, close=1.1+i*0.1, max=1.2+i*0.1, min=0.9+i*0.1) for i in range(20)]

@pytest.fixture
def sample_candles_volatile():
    """Gera uma lista de velas voláteis com pavios longos."""
    return [Candle(open=1.05, close=1.1, max=1.5, min=0.5) for _ in range(10)]

def test_sma_slope_positive(sample_candles_trending_up):
    """Testa se a inclinação da SMA é positiva em uma tendência de alta."""
    closes = [c.close for c in sample_candles_trending_up]
    slope = get_sma_slope(closes, period=14)
    assert slope > 0

def test_volatility_calculation(sample_candles_volatile):
    """Testa se a pontuação de volatilidade é alta para velas com pavios longos."""
    volatility = calculate_volatility(sample_candles_volatile, lookback=10)
    # (1.5-0.5) = 1.0 range, (1.1-1.05) = 0.05 body. Wick = 0.95. Score = 0.95 / 1.0 = 0.95
    assert volatility == pytest.approx(0.95)

def test_flow_strategy_buy_signal(sample_candles_trending_up):
    """Testa se a estratégia de fluxo gera um sinal de compra corretamente."""
    strategy = FlowStrategy()
    direction = strategy.analyze(sample_candles_trending_up)
    assert direction == "call"

def test_flow_strategy_no_signal_with_empty_candles():
    """Testa se a estratégia não gera sinal com uma lista de velas vazia."""
    strategy = FlowStrategy()
    direction = strategy.analyze([])
    assert direction is None
