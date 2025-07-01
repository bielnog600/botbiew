# analysis/strategy.py
from typing import Protocol, List, Optional
from core.data_models import Candle
from analysis.technical import (
    detect_sr_levels, is_near_level, is_pinbar, 
    is_engulfing, is_inside_bar, is_strong_candle
)

class TradingStrategy(Protocol):
    """Define a interface para todas as estratégias de negociação."""
    name: str
    def analyze(self, candles: List[Candle]) -> Optional[str]:
        ...

# --- ESTRATÉGIAS BASEADAS EM PADRÕES DE CANDLE ---

class EngulfingStrategy(TradingStrategy):
    """🟢 1. Engolfo Relâmpago: Um candle forte “engole” totalmente o corpo do anterior."""
    name = "engulfing"

    def analyze(self, candles: List[Candle]) -> Optional[str]:
        if len(candles) < 2: return None
        
        engulfing_type = is_engulfing(candles[-1], candles[-2])
        if engulfing_type == "BULLISH":
            return "call"
        if engulfing_type == "BEARISH":
            return "put"
        return None

class PinbarRejectionStrategy(TradingStrategy):
    """🟢 3. Pin Bar de Rejeição: Opera um Pin Bar que ocorre perto de uma zona de S/R."""
    name = "pinbar_rejection"

    def analyze(self, candles: List[Candle]) -> Optional[str]:
        if len(candles) < 10: return None

        last = candles[-1]
        resistance, support = detect_sr_levels(candles[:-1], n_levels=3)
        pinbar_type = is_pinbar(last)

        if pinbar_type == "HAMMER" and is_near_level(last.min, support, candles):
            return "call"
        if pinbar_type == "SHOOTING_STAR" and is_near_level(last.max, resistance, candles):
            return "put"
        return None

# --- ESTRATÉGIAS BASEADAS EM CONTEXTO E SEQUÊNCIA ---

class InsideBarBreakoutStrategy(TradingStrategy):
    """🟢 2. Inside Bar + Rompimento Forte: Opera o rompimento de um Inside Bar."""
    name = "inside_bar_breakout"

    def analyze(self, candles: List[Candle]) -> Optional[str]:
        if len(candles) < 3: return None

        c1, c2, c3 = candles[-3], candles[-2], candles[-1] # c2 é o inside bar, c3 é o rompimento

        if is_inside_bar(c2, c1) and is_strong_candle(c3):
            if c3.close > c1.max: # Rompimento para cima
                return "call"
            if c3.close < c1.min: # Rompimento para baixo
                return "put"
        return None

class FlowExhaustionStrategy(TradingStrategy):
    """🟢 4. Fluxo de 3 Velas + Exaustão: Opera a reversão após um fluxo e uma vela de fraqueza."""
    name = "flow_exhaustion"

    def analyze(self, candles: List[Candle]) -> Optional[str]:
        if len(candles) < 4: return None
        
        c1, c2, c3, c4 = candles[-4], candles[-3], candles[-2], candles[-1]
        last_three_flow = [c1, c2, c3]

        # Exaustão de Venda (após 3 velas vermelhas, surge uma verde fraca)
        if all(is_strong_candle(c) and c.close < c.open for c in last_three_flow):
            if not is_strong_candle(c4) and c4.close > c4.open:
                return "call" # Sinal de compra contra a exaustão

        # Exaustão de Compra (após 3 velas verdes, surge uma vermelha fraca)
        if all(is_strong_candle(c) and c.close > c.open for c in last_three_flow):
            if not is_strong_candle(c4) and c4.close < c4.open:
                return "put" # Sinal de venda contra a exaustão

        return None

class DoubleWickStrategy(TradingStrategy):
    """🟢 6. Duplo Pavio no Mesmo Nível: Opera a confirmação de um S/R por dois pavios."""
    name = "double_wick_rejection"

    def analyze(self, candles: List[Candle]) -> Optional[str]:
        if len(candles) < 10: return None
        
        recent_candles = candles[-10:]
        last = candles[-1]
        
        # Procura por duplo pavio superior (Resistência)
        highs = [c.max for c in recent_candles[:-1]]
        avg_high = sum(highs) / len(highs)
        tolerance = (max(highs) - min(highs)) / 2 or (avg_high * 0.0005)
        
        top_touches = [h for h in highs if abs(h - max(highs)) <= tolerance]
        if len(top_touches) >= 2 and last.close < last.open:
            return "put"

        # Procura por duplo pavio inferior (Suporte)
        lows = [c.min for c in recent_candles[:-1]]
        avg_low = sum(lows) / len(lows)
        tolerance = (max(lows) - min(lows)) / 2 or (avg_low * 0.0005)

        bottom_touches = [l for l in lows if abs(l - min(lows)) <= tolerance]
        if len(bottom_touches) >= 2 and last.close > last.open:
            return "call"
            
        return None

# --- LISTA DE ESTRATÉGIAS ATIVAS ---
# O bot irá testá-las nesta ordem para cada vela.
# A ordem pode ser otimizada (ex: padrões mais rápidos primeiro).
STRATEGIES: List[TradingStrategy] = [
    EngulfingStrategy(),
    PinbarRejectionStrategy(),
    InsideBarBreakoutStrategy(),
    DoubleWickStrategy(),
    FlowExhaustionStrategy(),
]
