from typing import List, Optional
from core.data_models import Candle

class FluxoDeVelas:
    name = "Fluxo de Velas"

    @staticmethod
    def analyze(candles: List[Candle], zones: dict) -> Optional[str]:
        # existing logic unchanged
        if len(candles) < 4:
            return None

        last4 = candles[-4:]
        colors = ["bullish" if c.close > c.open else "bearish" for c in last4]
        trend = colors[0]
        if any(col != trend for col in colors[:3]):
            return None

        entry = last4[3]
        body_size = abs(entry.close - entry.open)
        total_range = entry.max - entry.min
        if total_range == 0 or (body_size / total_range) < 0.6:
            return None

        if trend == "bullish" and entry.close > entry.open:
            return "call"
        if trend == "bearish" and entry.close < entry.open:
            return "put"
        return None

class Engolfo:
    name = "Engolfo"

    @staticmethod
    def analyze(candles: List[Candle], zones: dict) -> Optional[str]:
        if len(candles) < 2:
            return None

        prev, curr = candles[-2], candles[-1]
        prev_body = abs(prev.close - prev.open)
        curr_body = abs(curr.close - curr.open)

        # Bullish Engulfing
        if prev.close < prev.open and curr.close > curr.open:
            if curr_body > prev_body and curr.open < prev.close and curr.close > prev.open:
                return "call"

        # Bearish Engulfing
        if prev.close > prev.open and curr.close < curr.open:
            if curr_body > prev_body and curr.open > prev.close and curr.close < prev.open:
                return "put"
        return None

class NanoTendencia:
    name = "Nano Tendência"

    @staticmethod
    def analyze(candles: List[Candle], zones: dict) -> Optional[str]:
        # Requer pelo menos 6 candles: 5 para SMA e 3 de setup
        if len(candles) < 6:
            return None

        # Calcula SMA5 das últimas 5 closes antes das 3 candles finais
        sma_period = 5
        closes = [c.close for c in candles[-(sma_period+3):-3]]
        sma5 = sum(closes[-sma_period:]) / sma_period

        # Seleciona as primeiras 2 candles do setup e a de entrada
        c1, c2, entry = candles[-3], candles[-2], candles[-1]

        def valid_candle(c: Candle) -> bool:
            body = abs(c.close - c.open)
            wick_top = c.max - max(c.close, c.open)
            wick_bot = min(c.close, c.open) - c.min
            total = c.max - c.min
            # Corpo >=65% do range e sombras <=17.5% (1/4 do restante)
            return total > 0 and (body/total) >= 0.65 and (wick_top/total) <= 0.175 and (wick_bot/total) <= 0.175

        # Verifica corpo grande e posição em relação à SMA
        if valid_candle(c1) and valid_candle(c2) and valid_candle(entry):
            # duas candles abaixo SMA5 => tendência de baixa nano
            if c1.close < sma5 and c2.close < sma5 and entry.close < sma5:
                return "put"
            # duas candles acima SMA5 => tendência de alta nano
            if c1.close > sma5 and c2.close > sma5 and entry.close > sma5:
                return "call"
        return None

# Lista de estratégias usadas pelo bot, na ordem de prioridade
STRATEGIES = [
    FluxoDeVelas(),
    Engolfo(),
    NanoTendencia(),
]
