from typing import List, Optional
from core.data_models import Candle

class FluxoDeVelas:
    name = "Fluxo de Velas"

    @staticmethod
    def analyze(candles: List[Candle], zones: dict) -> Optional[str]:
        """
        1) Detecta sequência de 3-4 velas da mesma cor;
        2) A vela de entrada deve ter corpo "longo" (evitar dojis/spinning tops);
        3) Se sequência de alta + vela longa verde → CALL;
           Se sequência de baixa + vela longa vermelha → PUT;
        """
        if len(candles) < 4:
            return None

        last4 = candles[-4:]
        # identifica cores das 4 velas: bullish ou bearish
        colors = ["bullish" if c.close > c.open else "bearish" for c in last4]

        # primeiras 3 devem ser da mesma cor
        trend = colors[0]
        if any(col != trend for col in colors[:3]):
            return None

        # vela de entrada
        entry = last4[3]
        body_size = abs(entry.close - entry.open)
        total_range = entry.max - entry.min
        # exige corpo >= 60% do range total
        if total_range == 0 or (body_size / total_range) < 0.6:
            return None

        # decide direção
        if trend == "bullish" and entry.close > entry.open:
            return "call"
        if trend == "bearish" and entry.close < entry.open:
            return "put"

        return None


class Engolfo:
    name = "Engolfo"

    @staticmethod
    def analyze(candles: List[Candle], zones: dict) -> Optional[str]:
        """
        Identifica padrões de Engolfo de Alta (CALL) e Baixa (PUT).
        - Bullish engolfo: vela 1 bearish curta + vela 2 bullish longa que engloba o corpo da vela 1.
        - Bearish engolfo: vela 1 bullish curta + vela 2 bearish longa que engloba o corpo da vela 1.
        Retorna 'call' ou 'put'.
        """
        if len(candles) < 2:
            return None

        prev, curr = candles[-2], candles[-1]
        prev_body = abs(prev.close - prev.open)
        curr_body = abs(curr.close - curr.open)

        # Bullish Engulfing
        if prev.close < prev.open and curr.close > curr.open:
            # corpo da curr maior que corpo da prev e engloba
            if curr_body > prev_body:
                # curr.open abaixo de prev.close e curr.close acima de prev.open
                if curr.open < prev.close and curr.close > prev.open:
                    return "call"

        # Bearish Engulfing
        if prev.close > prev.open and curr.close < curr.open:
            if curr_body > prev_body:
                if curr.open > prev.close and curr.close < prev.open:
                    return "put"

        return None


# Lista de estratégias usadas pelo bot
STRATEGIES = [
    FluxoDeVelas(),
    Engolfo(),
]
