# analysis/cataloger.py
from typing import List, Dict, Tuple

def backtest_strategy(candles: List[Dict], strategy_func: callable) -> Tuple[int, int, int]:
    """
    Testa uma estratégia num histórico de velas para catalogação.
    Retorna uma tupla com (wins, losses, draws).
    """
    wins = 0
    losses = 0
    draws = 0

    # Garante que temos velas suficientes para o backtest
    if len(candles) < 51:
        return 0, 0, 0

    # Itera a partir do 50º candle (para dar dados aos indicadores) até ao penúltimo
    for i in range(50, len(candles) - 1):
        # Simula a fatia de dados que a estratégia teria no momento da decisão
        current_candle_slice = candles[i-50:i+1]
        
        # A decisão é baseada no candle 'i', e o resultado é verificado no candle seguinte, 'i+1'
        entry_candle = candles[i]
        result_candle = candles[i+1]

        # Executa a função da estratégia para obter a direção do sinal
        direction = strategy_func(current_candle_slice)

        if direction:
            # Compara a previsão com o resultado real
            if direction.lower() == 'call':
                if result_candle['close'] > entry_candle['close']:
                    wins += 1
                elif result_candle['close'] < entry_candle['close']:
                    losses += 1
                else:
                    draws += 1
            elif direction.lower() == 'put':
                if result_candle['close'] < entry_candle['close']:
                    wins += 1
                elif result_candle['close'] > entry_candle['close']:
                    losses += 1
                else:
                    draws += 1
                    
    return wins, losses, draws
