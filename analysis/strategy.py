# analysis/strategy.py
from typing import Protocol, List, Optional
from core.data_models import Candle
from analysis.technical import get_sma_slope, detect_sr_levels, is_near_level, detect_candle_pattern

class TradingStrategy(Protocol):
    """Define a interface para todas as estratégias de negociação."""
    name: str
    def analyze(self, candles: List[Candle]) -> Optional[str]:
        ...

class PriceActionStrategy(TradingStrategy):
    """
    Estratégia unificada de Price Action que busca a confluência de três fatores:
    1. Zona de Valor (Suporte/Resistência)
    2. Contexto (Nano-tendência)
    3. Gatilho (Padrão de Candlestick de Reversão)
    """
    name = "price_action_confluence"

    def analyze(self, candles: List[Candle]) -> Optional[str]:
        if len(candles) < 20:
            return None

        # 1. Identificação de Zonas de Valor
        # Usamos as velas passadas para não ter viés da vela atual
        resistance, support = detect_sr_levels(candles[:-1], n_levels=3)
        
        # 2. Análise de Contexto
        closes = [c.close for c in candles]
        slope = get_sma_slope(closes, period=14)
        is_uptrend = slope > 0.00001
        is_downtrend = slope < -0.00001

        # 3. Análise do Gatilho (Padrão de Candle)
        last_candle = candles[-1]
        prev_candle = candles[-2]
        pattern = detect_candle_pattern(last_candle, prev_candle)

        # --- LÓGICA DE DECISÃO ---

        # Cenário de COMPRA (CALL)
        # Condição: Preço perto de um suporte, em tendência de alta (ou neutra),
        # E ocorre um padrão de reversão de alta.
        if is_near_level(last_candle.min, support, candles) and not is_downtrend:
            if pattern in ["BULLISH_ENGULFING", "HAMMER"]:
                return "call"

        # Cenário de VENDA (PUT)
        # Condição: Preço perto de uma resistência, em tendência de baixa (ou neutra),
        # E ocorre um padrão de reversão de baixa.
        if is_near_level(last_candle.max, resistance, candles) and not is_uptrend:
            if pattern in ["BEARISH_ENGULFING", "SHOOTING_STAR"]:
                return "put"

        # Se nenhuma confluência for encontrada, não faz nada.
        return None

# Lista de todas as estratégias disponíveis para o bot
# Agora, temos apenas uma estratégia poderosa e unificada.
STRATEGIES: List[TradingStrategy] = [
    PriceActionStrategy(),
]
