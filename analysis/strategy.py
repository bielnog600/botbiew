# analysis/strategy.py
from typing import Protocol, List, Optional
from core.data_models import Candle
from analysis.technical import calculate_sma, calculate_ema

class TradingStrategy(Protocol):
    """Define a interface para todas as estratégias de negociação."""
    name: str
    def analyze(self, candles: List[Candle]) -> Optional[str]:
        ...

class MacdCrossoverStrategy(TradingStrategy):
    """
    Estratégia baseada no cruzamento de médias móveis, traduzida do script Lua.
    Semelhante a um indicador MACD, opera o cruzamento da linha de momento com a linha de sinal.
    """
    name = "macd_crossover"
    
    # Parâmetros da estratégia, como no script Lua
    FAST_MA_PERIOD = 5
    SLOW_MA_PERIOD = 34
    SIGNAL_PERIOD = 6

    def analyze(self, candles: List[Candle]) -> Optional[str]:
        # Precisa de dados suficientes para calcular a média lenta + a linha de sinal
        if len(candles) < self.SLOW_MA_PERIOD + self.SIGNAL_PERIOD:
            return None

        closes = [c.close for c in candles]

        # Calcula o histórico da linha de momento (diferença entre as SMAs)
        moment_line = []
        for i in range(self.SLOW_MA_PERIOD, len(closes) + 1):
            historical_closes = closes[:i]
            sma_fast = calculate_sma(historical_closes, self.FAST_MA_PERIOD)
            sma_slow = calculate_sma(historical_closes, self.SLOW_MA_PERIOD)
            moment_line.append(sma_fast - sma_slow)

        if len(moment_line) < 2:
            return None

        # Calcula a linha de sinal (EMA da linha de momento)
        signal_line_current = calculate_ema(moment_line, self.SIGNAL_PERIOD)
        signal_line_prev = calculate_ema(moment_line[:-1], self.SIGNAL_PERIOD)
        
        moment_current = moment_line[-1]
        moment_prev = moment_line[-2]

        # --- LÓGICA DE DECISÃO ---

        # Condição de Compra (CALL): Momento cruza a linha de sinal para cima.
        if moment_prev < signal_line_prev and moment_current > signal_line_current:
            return "call"

        # Condição de Venda (PUT): Momento cruza a linha de sinal para baixo.
        if moment_prev > signal_line_prev and moment_current < signal_line_current:
            return "put"

        return None

# Lista de estratégias ativas. Agora, apenas a nossa nova estratégia.
STRATEGIES: List[TradingStrategy] = [
    MacdCrossoverStrategy(),
]
