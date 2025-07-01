# analysis/strategy.py
from typing import Protocol, List, Optional
from core.data_models import Candle
from analysis.technical import (
    calculate_sma, 
    calculate_ema, 
    detect_sr_levels, 
    is_near_level
)

class TradingStrategy(Protocol):
    """Define a interface para todas as estratégias de negociação."""
    name: str
    def analyze(self, candles: List[Candle]) -> Optional[str]:
        ...

class ContextualCrossoverStrategy(TradingStrategy):
    """
    Estratégia que opera o cruzamento de médias móveis, mas APENAS quando
    o preço está numa zona de valor (Suporte ou Resistência), respeitando
    a direção esperada para essa zona.
    """
    name = "contextual_crossover"
    
    FAST_MA_PERIOD = 5
    SLOW_MA_PERIOD = 34
    SIGNAL_PERIOD = 6

    def analyze(self, candles: List[Candle]) -> Optional[str]:
        if len(candles) < self.SLOW_MA_PERIOD + self.SIGNAL_PERIOD:
            return None

        # --- CÁLCULO DO GATILHO (CRUZAMENTO) ---
        closes = [c.close for c in candles]
        moment_line = []
        for i in range(self.SLOW_MA_PERIOD, len(closes) + 1):
            historical_closes = closes[:i]
            sma_fast = calculate_sma(historical_closes, self.FAST_MA_PERIOD)
            sma_slow = calculate_sma(historical_closes, self.SLOW_MA_PERIOD)
            moment_line.append(sma_fast - sma_slow)

        if len(moment_line) < 2:
            return None

        signal_line_current = calculate_ema(moment_line, self.SIGNAL_PERIOD)
        signal_line_prev = calculate_ema(moment_line[:-1], self.SIGNAL_PERIOD)
        
        moment_current = moment_line[-1]
        moment_prev = moment_line[-2]

        is_call_signal = moment_prev < signal_line_prev and moment_current > signal_line_current
        is_put_signal = moment_prev > signal_line_prev and moment_current < signal_line_current

        # Se não houver nenhum gatilho de cruzamento, não há nada a fazer.
        if not is_call_signal and not is_put_signal:
            return None

        # --- ANÁLISE DE CONTEXTO (A PARTE INTELIGENTE) ---
        last_candle = candles[-1]
        resistance_levels, support_levels = detect_sr_levels(candles[:-1], n_levels=3)

        # Se o preço está perto de um SUPORTE, SÓ consideramos sinais de COMPRA (CALL).
        if is_near_level(last_candle.min, support_levels, candles):
            if is_call_signal:
                print(f"DEBUG: Sinal de CALL confirmado perto de um suporte.")
                return "call"
            # Se for um sinal de PUT perto de um suporte, é inválido.
            return None

        # Se o preço está perto de uma RESISTÊNCIA, SÓ consideramos sinais de VENDA (PUT).
        if is_near_level(last_candle.max, resistance_levels, candles):
            if is_put_signal:
                print(f"DEBUG: Sinal de PUT confirmado perto de uma resistência.")
                return "put"
            # Se for um sinal de CALL perto de uma resistência, é inválido.
            return None

        # Se o gatilho ocorreu, mas LONGE de uma zona de valor, ignora o sinal.
        return None

# Lista de estratégias ativas.
STRATEGIES: List[TradingStrategy] = [
    ContextualCrossoverStrategy(),
]
