# analysis/technical_indicators.py
import math
from typing import List, Dict, Optional, Any

# Padrões com pandas_ta ficam opcionais (pra não matar CPU em scan massivo)
try:
    import pandas as pd
    import pandas_ta as ta
    _HAS_TA = True
except:
    _HAS_TA = False


def _as_float(x, default=None):
    try:
        if x is None:
            return default
        return float(x)
    except:
        return default


def _norm(c: Dict) -> Optional[Dict[str, float]]:
    o = _as_float(c.get("open"))
    h = _as_float(c.get("max"))
    l = _as_float(c.get("min"))
    cl = _as_float(c.get("close"))
    if o is None or h is None or l is None or cl is None:
        return None
    return {"open": o, "high": h, "low": l, "close": cl}


def _norm_list(candles: List[Dict], max_len: int = 500) -> List[Dict[str, float]]:
    sliced = candles[-max_len:] if len(candles) > max_len else candles
    out = []
    for c in sliced:
        nc = _norm(c)
        if nc:
            out.append(nc)
    return out


def calculate_ema(candles: List[Dict], period: int) -> Optional[float]:
    c = _norm_list(candles, max_len=period * 6)
    if len(c) < period:
        return None
    closes = [x["close"] for x in c]
    k = 2.0 / (period + 1.0)
    ema = sum(closes[:period]) / period
    for price in closes[period:]:
        ema = (price * k) + (ema * (1 - k))
    return ema


def calculate_atr(candles: List[Dict], period: int = 14) -> Optional[float]:
    c = _norm_list(candles, max_len=period * 8)
    if len(c) < period + 1:
        return None

    trs = []
    for i in range(1, len(c)):
        high = c[i]["high"]
        low = c[i]["low"]
        prev_close = c[i - 1]["close"]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)

    if len(trs) < period:
        return None

    # Wilder RMA (mais estável pro ATR)
    rma = sum(trs[:period]) / period
    for tr in trs[period:]:
        rma = (rma * (period - 1) + tr) / period
    return rma


def calculate_rsi(candles: List[Dict], period: int = 14) -> Optional[float]:
    c = _norm_list(candles, max_len=period * 8)
    if len(c) < period + 1:
        return None

    closes = [x["close"] for x in c]
    gains = []
    losses = []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        if diff >= 0:
            gains.append(diff)
            losses.append(0.0)
        else:
            gains.append(0.0)
            losses.append(abs(diff))

    if len(gains) < period:
        return None

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / max(avg_loss, 1e-12)
    return 100.0 - (100.0 / (1.0 + rs))


def calculate_adx(candles: List[Dict], period: int = 14) -> Optional[Dict[str, float]]:
    """
    ADX + DI+/DI- (Welles Wilder).
    Retorna: {"adx": x, "di_plus": x, "di_minus": x}
    """
    c = _norm_list(candles, max_len=period * 10)
    if len(c) < period + 2:
        return None

    tr_list = []
    plus_dm = []
    minus_dm = []

    for i in range(1, len(c)):
        high = c[i]["high"]
        low = c[i]["low"]
        prev_high = c[i - 1]["high"]
        prev_low = c[i - 1]["low"]
        prev_close = c[i - 1]["close"]

        up_move = high - prev_high
        down_move = prev_low - low

        pdm = up_move if (up_move > down_move and up_move > 0) else 0.0
        mdm = down_move if (down_move > up_move and down_move > 0) else 0.0

        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))

        plus_dm.append(pdm)
        minus_dm.append(mdm)
        tr_list.append(tr)

    if len(tr_list) < period:
        return None

    # Wilder smoothing (RMA)
    tr14 = sum(tr_list[:period])
    pdm14 = sum(plus_dm[:period])
    mdm14 = sum(minus_dm[:period])

    dx_list = []

    for i in range(period, len(tr_list)):
        # atualiza somas suavizadas
        tr14 = tr14 - (tr14 / period) + tr_list[i]
        pdm14 = pdm14 - (pdm14 / period) + plus_dm[i]
        mdm14 = mdm14 - (mdm14 / period) + minus_dm[i]

        di_plus = 100.0 * (pdm14 / max(tr14, 1e-12))
        di_minus = 100.0 * (mdm14 / max(tr14, 1e-12))
        dx = 100.0 * (abs(di_plus - di_minus) / max(di_plus + di_minus, 1e-12))
        dx_list.append((di_plus, di_minus, dx))

    if len(dx_list) < period:
        # ainda dá pra retornar DI mesmo sem ADX estável
        di_plus, di_minus, _ = dx_list[-1]
        return {"adx": 0.0, "di_plus": di_plus, "di_minus": di_minus}

    # ADX começa como média dos primeiros 'period' DX
    adx = sum(x[2] for x in dx_list[:period]) / period
    for i in range(period, len(dx_list)):
        adx = (adx * (period - 1) + dx_list[i][2]) / period

    di_plus, di_minus, _ = dx_list[-1]
    return {"adx": adx, "di_plus": di_plus, "di_minus": di_minus}


def calculate_choppiness(candles: List[Dict], period: int = 14) -> Optional[float]:
    """
    CHOP = 100 * log10( sum(TR,n) / (maxHigh(n)-minLow(n)) ) / log10(n)
    Quanto maior, mais mercado preso.
    """
    c = _norm_list(candles, max_len=period * 8)
    if len(c) < period + 1:
        return None

    # usa os últimos period candles
    w = c[-(period + 1):]

    tr_sum = 0.0
    hi = -1e18
    lo = 1e18

    for i in range(1, len(w)):
        high = w[i]["high"]
        low = w[i]["low"]
        prev_close = w[i - 1]["close"]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        tr_sum += tr
        if high > hi:
            hi = high
        if low < lo:
            lo = low

    den = max(hi - lo, 1e-12)
    n = float(period)
    chop = 100.0 * (math.log10(tr_sum / den) / max(math.log10(n), 1e-12))
    return chop


def classify_regime(adx: Optional[float], chop: Optional[float]) -> str:
    """
    Regime simples e útil.
    """
    if adx is None or chop is None:
        return "UNKNOWN"

    # valores clássicos que funcionam bem no M1
    if adx >= 25 and chop <= 50:
        return "TREND"
    if adx <= 18 and chop >= 60:
        return "RANGE"
    return "MIXED"


def check_candlestick_pattern(candles: List[Dict]) -> Optional[str]:
    """
    Mantido, mas agora opcional.
    Retorna 'call' ou 'put' se achar padrão, senão None.
    """
    if not _HAS_TA:
        return None

    if len(candles) < 6:
        return None

    rows = []
    for c in candles[-60:]:
        nc = _norm(c)
        if not nc:
            continue
        rows.append({"open": nc["open"], "high": nc["high"], "low": nc["low"], "close": nc["close"]})

    if len(rows) < 10:
        return None

    df = pd.DataFrame(rows)

    df.ta.cdl_pattern(
        name=[
            "engulfing", "hammer", "shootingstar", "doji",
            "morningstar", "eveningstar", "piercing", "darkcloud",
            "tweezertop", "tweezerbottom"
        ],
        append=True
    )

    last = df.iloc[-1]

    # CALL
    if last.get("CDL_ENGULFING", 0) == 100 or \
       last.get("CDL_HAMMER", 0) == 100 or \
       last.get("CDL_MORNINGSTAR", 0) == 100 or \
       last.get("CDL_PIERCING", 0) == 100 or \
       last.get("CDL_TWEEZERBOTTOM", 0) == 100:
        return "call"

    # PUT
    if last.get("CDL_ENGULFING", 0) == -100 or \
       last.get("CDL_SHOOTINGSTAR", 0) == 100 or \
       last.get("CDL_EVENINGSTAR", 0) == 100 or \
       last.get("CDL_DARKCLOUD", 0) == 100 or \
       last.get("CDL_TWEEZERTOP", 0) == 100:
        return "put"

    # Doji eu não forço direção aqui, porque senão vira ruído
    return None
