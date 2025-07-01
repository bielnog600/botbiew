# analysis/strategy.py
from typing import Protocol, List, Optional, Dict
from core.data_models import Candle
from analysis.technical import (
    detect_sr_levels, is_near_level
)

class TradingStrategy(Protocol):
    """Define a interface para todas as estratégias de negociação."""
    name: str
    def find_setup(self, candles: List[Candle]) -> Optional[Dict]:
        """
        Procura por uma configuração de trade numa vela fechada.
        Retorna um dicionário com a direção e o nível de rompimento se encontrar um setup.
        """
        ...

class ReversalBreakoutStrategy(TradingStrategy):
    """
    Estratégia de Reversão com Confirmação de Rompimento.
    Fase 1: Identifica uma vela de potencial reversão perto de uma zona de S/R.
    Fase 2 (no bot): Confirma a entrada se a próxima vela romper a máxima/mínima da vela de setup.
    """
    name = "reversal_breakout"

    def find_setup(self, candles: List[Candle]) -> Optional[Dict]:
        if len(candles) < 10:
            return None

        # A vela de setup é a última vela da lista (que acabou de fechar)
        setup_candle = candles[-1]
        
        # Identifica as zonas de valor (S/R) com base no histórico anterior
        resistance, support = detect_sr_levels(candles[:-1], n_levels=3)

        # --- LÓGICA DE DECISÃO ---

        # Procura por um Setup de COMPRA (CALL)
        # Condição: Uma vela (qualquer cor) fecha perto de um suporte,
        # indicando uma possível reversão para alta.
        if is_near_level(setup_candle.min, support, candles):
            return {
                "direction": "call",
                "breakout_level": setup_candle.max, # O alvo é romper a máxima da vela de setup
                "strategy": self.name
            }

        # Procura por um Setup de VENDA (PUT)
        # Condição: Uma vela (qualquer cor) fecha perto de uma resistência,
        # indicando uma possível reversão para baixa.
        if is_near_level(setup_candle.max, resistance, candles):
            return {
                "direction": "put",
                "breakout_level": setup_candle.min, # O alvo é romper a mínima da vela de setup
                "strategy": self.name
            }

        return None

# Lista de estratégias ativas. Focada na nossa nova estratégia principal.
STRATEGIES: List[TradingStrategy] = [
    ReversalBreakoutStrategy(),
]
