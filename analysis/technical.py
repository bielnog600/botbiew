# analysis/technical.py
from typing import List, Tuple, Dict, Any, Optional

def _as_float(x, default=None):
    try:
        if x is None:
            return default
        return float(x)
    except:
        return default

def _normalize_candle(c: Dict) -> Optional[Dict[str, float]]:
    """
    Normaliza um candle vindo da API para floats seguros.
    Retorna None se faltar algum campo essencial.
    """
    o = _as_float(c.get("open"))
    h = _as_float(c.get("max"))
    l = _as_float(c.get("min"))
    cl = _as_float(c.get("close"))
    if o is None or h is None or l is None or cl is None:
        return None
    return {"open": o, "high": h, "low": l, "close": cl, "from": int(c.get("from", 0) or 0)}

def _pivot_points(candles: List[Dict], window_size: int, lookback: int = 300) -> Dict[str, List[Dict[str, Any]]]:
    """
    Detecta pivôs (topos e fundos) por janela.
    Retorna lista de pivôs com índice, preço e timestamp.
    """
    piv_hi = []
    piv_lo = []

    if len(candles) < (2 * window_size + 1):
        return {"highs": [], "lows": []}

    # recorta lookback para ficar leve
    start = max(0, len(candles) - lookback)
    sliced = candles[start:]

    norm = []
    for c in sliced:
        nc = _normalize_candle(c)
        if nc:
            norm.append(nc)

    if len(norm) < (2 * window_size + 1):
        return {"highs": [], "lows": []}

    for i in range(window_size, len(norm) - window_size):
        mid = norm[i]
        mh = mid["high"]
        ml = mid["low"]

        is_hi = True
        is_lo = True
        for j in range(1, window_size + 1):
            if not (mh > norm[i - j]["high"] and mh > norm[i + j]["high"]):
                is_hi = False
            if not (ml < norm[i - j]["low"] and ml < norm[i + j]["low"]):
                is_lo = False
            if (not is_hi) and (not is_lo):
                break

        if is_hi:
            piv_hi.append({"i": start + i, "price": mh, "ts": mid["from"]})
        if is_lo:
            piv_lo.append({"i": start + i, "price": ml, "ts": mid["from"]})

    return {"highs": piv_hi, "lows": piv_lo}

def _cluster_levels(levels: List[float], tolerance_pct: float = 0.0015) -> List[Dict[str, Any]]:
    """
    Agrupa níveis parecidos em "zonas" com força.
    tolerance_pct: 0.0015 = 0.15% de distância para juntar.
    """
    if not levels:
        return []

    lv = sorted([float(x) for x in levels if x is not None])
    zones = []

    for p in lv:
        placed = False
        for z in zones:
            ref = z["price"]
            if ref > 0 and abs(p - ref) / ref <= tolerance_pct:
                z["hits"] += 1
                z["prices"].append(p)
                z["price"] = sum(z["prices"]) / len(z["prices"])
                placed = True
                break
        if not placed:
            zones.append({"price": p, "hits": 1, "prices": [p]})

    zones.sort(key=lambda x: x["hits"], reverse=True)
    for z in zones:
        z.pop("prices", None)
    return zones

def get_sr_zones(
    candles: List[Dict],
    window_size: int,
    tolerance_pct: float = 0.0015,
    top_n: int = 6,
    lookback: int = 300
) -> Dict[str, Any]:
    """
    Retorna suportes e resistências em formato de zonas com força (hits).
    """
    piv = _pivot_points(candles, window_size=window_size, lookback=lookback)
    res_levels = [p["price"] for p in piv["highs"]]
    sup_levels = [p["price"] for p in piv["lows"]]

    res_zones = _cluster_levels(res_levels, tolerance_pct=tolerance_pct)[:top_n]
    sup_zones = _cluster_levels(sup_levels, tolerance_pct=tolerance_pct)[:top_n]

    resistances = sorted([z["price"] for z in res_zones], reverse=True)
    supports = sorted([z["price"] for z in sup_zones])

    return {
        "resistance": resistances,
        "support": supports,
        "resistance_zones": res_zones,
        "support_zones": sup_zones,
        "pivots": piv
    }

def get_m15_sr_zones(m15_candles: List[Dict]) -> Tuple[List[float], List[float]]:
    z = get_sr_zones(m15_candles, window_size=5, tolerance_pct=0.0015, top_n=6, lookback=400)
    return z["resistance"], z["support"]

def get_h1_sr_zones(h1_candles: List[Dict]) -> Tuple[List[float], List[float]]:
    z = get_sr_zones(h1_candles, window_size=8, tolerance_pct=0.0020, top_n=6, lookback=400)
    return z["resistance"], z["support"]

def detect_structure(
    candles: List[Dict],
    pivot_window: int = 3,
    lookback: int = 180
) -> Dict[str, Any]:
    """
    Detecta estrutura HH/HL ou LH/LL usando pivôs.
    """
    piv = _pivot_points(candles, window_size=pivot_window, lookback=lookback)
    highs = piv["highs"]
    lows = piv["lows"]

    if len(highs) < 2 or len(lows) < 2:
        return {"state": "UNKNOWN", "reason": "poucos_pivos", "last_high": None, "prev_high": None, "last_low": None, "prev_low": None}

    last_high = highs[-1]
    prev_high = highs[-2]
    last_low = lows[-1]
    prev_low = lows[-2]

    hh = last_high["price"] > prev_high["price"]
    hl = last_low["price"] > prev_low["price"]
    lh = last_high["price"] < prev_high["price"]
    ll = last_low["price"] < prev_low["price"]

    if hh and hl:
        state = "UP_HH_HL"
    elif lh and ll:
        state = "DOWN_LH_LL"
    else:
        state = "RANGE_MIXED"

    return {
        "state": state,
        "last_high": last_high,
        "prev_high": prev_high,
        "last_low": last_low,
        "prev_low": prev_low
    }

def distance_to_nearest_level(price: float, levels: List[float]) -> Optional[float]:
    """
    Retorna a distância percentual até o nível mais próximo.
    """
    if price is None or not levels:
        return None
    best = None
    for lv in levels:
        if lv is None or lv == 0:
            continue
        d = abs(price - lv) / lv
        if best is None or d < best:
            best = d
    return best
