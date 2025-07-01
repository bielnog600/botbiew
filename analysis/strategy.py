# analysis/strategy.py
from typing import Protocol, List, Optional
from core.data_models import Candle
from analysis.technical import get_sma_slope, detect_sr_levels, is_near_level

class TradingStrategy(Protocol):
    """Define a interface para todas as estratégias de negociação."""
    name: str
    def analyze(self, candles: List[Candle]) -> Optional[str]:
        ...

class FlowStrategy(TradingStrategy):
    """
    Estratégia de Fluxo: Entra a favor de uma sequência de velas
    na mesma direção da nano-tendência.
    """
    name = "flow"

    def analyze(self, candles: List[Candle]) -> Optional[str]:
        if len(candles) < 15:
            return None

        closes = [c.close for c in candles]
        slope = get_sma_slope(closes, period=14)
        last_three = candles[-3:]

        if slope > 0.00001 and all(c.close > c.open for c in last_three):
            return "call"
        if slope < -0.00001 and all(c.close < c.open for c in last_three):
            return "put"
        return None

class EngulfingPatternStrategy(TradingStrategy):
    """
    Estratégia de Padrão de Engolfo: Busca por velas que engolfam
    a anterior, sinalizando uma forte reversão.
    """
    name = "engulfing_pattern"

    def analyze(self, candles: List[Candle]) -> Optional[str]:
        if len(candles) < 2:
            return None
        
        last = candles[-1]
        prev = candles[-2]

        # Engolfo de Alta (Bullish Engulfing)
        is_bullish_engulfing = (prev.close < prev.open and 
                                last.close > last.open and
                                last.close > prev.open and
                                last.open < prev.close)
        if is_bullish_engulfing:
            return "call"

        # Engolfo de Baixa (Bearish Engulfing)
        is_bearish_engulfing = (prev.close > prev.open and
                                last.close < last.open and
                                last.close < prev.open and
                                last.open > prev.close)
        if is_bearish_engulfing:
            return "put"
            
        return None

class PullbackSRStrategy(TradingStrategy):
    """
    Estratégia de Pullback em Suporte/Resistência: Opera a favor
    da tendência quando o preço toca e respeita um nível de S/R.
    """
    name = "pullback_sr"

    def analyze(self, candles: List[Candle]) -> Optional[str]:
        if len(candles) < 20:
            return None

        closes = [c.close for c in candles]
        slope = get_sma_slope(closes, period=14)
        resistance, support = detect_sr_levels(candles[:-1], n_levels=3) # Usa velas passadas para S/R
        last = candles[-1]

        # Pullback de alta em um suporte
        if slope > 0.00001 and is_near_level(last.min, support, candles):
            # Confirmação: vela atual fechou em alta
            if last.close > last.open:
                return "call"

        # Pullback de baixa em uma resistência
        if slope < -0.00001 and is_near_level(last.max, resistance, candles):
            # Confirmação: vela atual fechou em baixa
            if last.close < last.open:
                return "put"

        return None

class ThreeTowersStrategy(TradingStrategy):
    """
    Estratégia 3 Torres: Busca por um padrão de exaustão e rejeição
    de preço próximo a uma zona forte de Suporte ou Resistência.
    """
    name = "three_towers"

    def analyze(self, candles: List[Candle]) -> Optional[str]:
        if len(candles) < 20:
            return None

        resistance, support = detect_sr_levels(candles[:-3], n_levels=2) # Níveis mais fortes
        c1, c2, c3 = candles[-3], candles[-2], candles[-1]

        # 3 Torres de Baixa (Venda)
        # Condição: Próximo a uma resistência
        if is_near_level(c1.max, resistance, candles):
            # c1: Vela de força compradora
            # c2: Vela de rejeição com pavio superior
            # c3: Vela de confirmação vendedora
            is_rejection_candle = (c2.max > c1.max) and ((c2.max - c2.close) > abs(c2.close - c2.open) * 2)
            if c1.close > c1.open and is_rejection_candle and c3.close < c3.open:
                return "put"

        # 3 Torres de Alta (Compra)
        # Condição: Próximo a um suporte
        if is_near_level(c1.min, support, candles):
            # c1: Vela de força vendedora
            # c2: Vela de rejeição com pavio inferior
            # c3: Vela de confirmação compradora
            is_rejection_candle = (c2.min < c1.min) and ((c2.open - c2.min) > abs(c2.close - c2.open) * 2)
            if c1.close < c1.open and is_rejection_candle and c3.close > c3.open:
                return "call"

        return None

# Lista de todas as estratégias disponíveis para o bot
# O bot irá testá-las nesta ordem para cada vela.
STRATEGIES: List[TradingStrategy] = [
    FlowStrategy(),
    PullbackSRStrategy(),
    EngulfingPatternStrategy(),
    ThreeTowersStrategy(),
]
