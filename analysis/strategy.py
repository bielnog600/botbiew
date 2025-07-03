# analysis/strategy.py
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
        # Precisamos de pelo menos 4 velas: 3 de tendência + 1 de entrada
        if len(candles) < 4:
            return None

        last4 = candles[-4:]
        # determina se são de alta (bullish) ou baixa (bearish)
        colors = ["bullish" if c.close > c.open else "bearish" for c in last4]

        # todas as 3 primeiras devem ter mesma cor
        trend = colors[0]
        if not all(col == trend for col in colors[:3]):
            return None

        # vela de entrada
        entry = last4[3]
        body_size = abs(entry.close - entry.open)
        total_range = entry.max - entry.min
        # exige corpo >= 60% da variação total para ser "longa"
        if total_range == 0 or (body_size / total_range) < 0.6:
            return None

        # decide direção
        if trend == "bullish" and entry.close > entry.open:
            return "call"
        if trend == "bearish" and entry.close < entry.open:
            return "put"

        return None


# Em algum lugar do módulo, substitua a inclusão da antiga three_bar_momentum por:
STRATEGIES = [
    FluxoDeVelas(),
    # ... outras estratégias
]
