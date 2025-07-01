# analysis/strategy.py
from typing import Protocol, List, Optional
from core.data_models import Candle
from analysis.technical import (
    detect_sr_levels, is_near_level, get_candle_pattern
)

class TradingStrategy(Protocol):
    """Define a interface para todas as estratégias de negociação."""
    name: str
    def analyze(self, candles: List[Candle]) -> Optional[str]:
        ...

class PriceActionConfluenceStrategy(TradingStrategy):
    """
    Estratégia unificada que busca a CONFLUÊNCIA de múltiplos fatores de Price Action.
    Opera apenas quando um padrão de gatilho ocorre numa zona de valor.
    """
    name = "price_action_confluence"

    def analyze(self, candles: List[Candle]) -> Optional[str]:
        if len(candles) < 20:
            return None

        # 1. CONTEXTO: Identifica as Zonas de Valor (Suporte e Resistência)
        # Usamos as velas passadas para não ter viés da vela atual
        resistance_levels, support_levels = detect_sr_levels(candles[:-1], n_levels=3)
        
        last_candle = candles[-1]
        prev_candle = candles[-2]

        # 2. GATILHO: Procura por um padrão de candlestick de reversão
        pattern = get_candle_pattern(last_candle, prev_candle)

        # --- LÓGICA DE DECISÃO DE ALTA PROBABILIDADE ---

        # Cenário de COMPRA (CALL):
        # A confluência perfeita é um padrão de reversão de alta
        # que ocorre exatamente numa zona de suporte.
        if pattern in ["BULLISH_ENGULFING", "HAMMER"]:
            if is_near_level(last_candle.min, support_levels, candles):
                return "call"

        # Cenário de VENDA (PUT):
        # A confluência perfeita é um padrão de reversão de baixa
        # que ocorre exatamente numa zona de resistência.
        if pattern in ["BEARISH_ENGULFING", "SHOOTING_STAR"]:
            if is_near_level(last_candle.max, resistance_levels, candles):
                return "put"

        # Se nenhuma confluência for encontrada, o bot permanece paciente.
        return None

# Lista de estratégias ativas. Agora, apenas a nossa estratégia principal.
STRATEGIES: List[TradingStrategy] = [
    PriceActionConfluenceStrategy(),
]
