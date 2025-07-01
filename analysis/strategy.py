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

class MacdCrossoverStrategy(TradingStrategy):
    """
    Estratégia baseada no cruzamento de médias móveis, com um filtro
    de segurança de Suporte e Resistência para evitar entradas contra "paredes".
    """
    name = "macd_crossover_sr_filtered"
    
    FAST_MA_PERIOD = 5
    SLOW_MA_PERIOD = 34
    SIGNAL_PERIOD = 6

    def analyze(self, candles: List[Candle]) -> Optional[str]:
        if len(candles) < self.SLOW_MA_PERIOD + self.SIGNAL_PERIOD:
            return None

        closes = [c.close for c in candles]
        last_candle = candles[-1]

        # --- LÓGICA DO INDICADOR (GATILHO) ---
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

        # Se não houver sinal de cruzamento, para a análise aqui.
        if not is_call_signal and not is_put_signal:
            return None

        # --- FILTRO DE SEGURANÇA DE PRICE ACTION ---
        
        # 1. Identifica as zonas de valor (S/R)
        resistance_levels, support_levels = detect_sr_levels(candles[:-1], n_levels=3)

        # 2. Aplica o filtro
        if is_call_signal:
            # Se o sinal é de COMPRA, verifica se NÃO está perto de uma resistência.
            if is_near_level(last_candle.max, resistance_levels, candles):
                print(f"DEBUG: Sinal de CALL ignorado. Preço próximo a uma resistência.")
                return None # Cancela o sinal
            return "call" # Sinal válido

        if is_put_signal:
            # Se o sinal é de VENDA, verifica se NÃO está perto de um suporte.
            if is_near_level(last_candle.min, support_levels, candles):
                print(f"DEBUG: Sinal de PUT ignorado. Preço próximo a um suporte.")
                return None # Cancela o sinal
            return "put" # Sinal válido

        return None

# Lista de estratégias ativas.
STRATEGIES: List[TradingStrategy] = [
    MacdCrossoverStrategy(),
]
