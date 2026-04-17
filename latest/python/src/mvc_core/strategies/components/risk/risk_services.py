# src/mvc_core/strategies/risk/risk_services.py
import math
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from mvc_core.domain.enums import Action, Side
from mvc_core.engine.backtester.backtester_data import TradeSignal
from mvc_core.strategies.build.callable_types import RiskFn
from mvc_core.strategies.components.risk.risk_data import RiskConfig


def build_risk_fn(cfg: Optional[RiskConfig], feature_map: Optional[Dict[str, pd.Series]] = None,) -> Optional[RiskFn]:
    """
    Build a pure risk function from a RiskConfig.

    Contract
    --------
    risk_fn(ts, price_map, portfolio) -> List[TradeSignal]
    """
    if cfg is None or not cfg.enabled or not cfg.rules:
        return None

    rules = sorted(cfg.rules, key=lambda r: int(r.get("priority", 100)))


    def risk_fn(ts, price_map: Dict[str, float], portfolio) -> List[TradeSignal]:
        out: List[TradeSignal] = []
        positions = getattr(portfolio, "positions", None)
        if not positions:
            return out

        by_key: Dict[Tuple[str, Side], List[Dict[str, Any]]] = {}

        for pos in positions:

            status = getattr(pos, "status", None)
            is_open_attr = getattr(pos, "is_open", None)
            if is_open_attr is not None and not bool(is_open_attr):
                continue
            if status is not None:
                status_str = getattr(status, "name", str(status))
                if str(status_str) != "OPEN":
                    continue

            inst = getattr(pos, "instrument", None)
            side = getattr(pos, "side", None)
            if inst is None or side is None:
                continue

            ep = _get_entry_price(pos)

            by_key.setdefault((str(inst), side), []).append({
                "entry_price": float(ep),
                "lots": float(getattr(pos, "lots", 0.0)),
                "opened_at": getattr(pos, "entry_date", None),
            })

        if not by_key:
            return out

        for (instrument, side), legs in by_key.items():
            px = price_map.get(instrument)
            if px is None:
                continue
            px = float(px)
            if math.isnan(px):
                continue

            total_lots = sum(l["lots"] for l in legs) or 1.0
            vwap_entry = sum(l["entry_price"] * l["lots"] for l in legs) / total_lots

            for rule in rules:
                rtype  = str(rule.get("type"))
                scope  = str(rule.get("scope", "per_leg"))
                params = dict(rule.get("params", {}))
                rr = params.get("reduce_ratio", None)
                reduce_ratio = float(rr) if rr is not None else None


                if rtype == "reduce_feature_cross_1d" and reduce_ratio is not None:
                    _risk_reduce_feature_cross_1d(out, instrument, side, ts, feature_map, legs, vwap_entry, scope, reduce_ratio, params)


                elif rtype == "sl_vol_multiple":
                    _risk_sl_vol_multiple(out, instrument, side, ts, feature_map, px, legs, vwap_entry, scope, params)
                elif rtype == "tp_vol_multiple":
                    _risk_tp_vol_multiple(out, instrument, side, ts, feature_map, px, legs, vwap_entry, scope, params)

                
                else:
                    pass

        return out

    return risk_fn




def _get_entry_price(pos: object) -> float:

    for attr in ("entry_price", "entry_price_eff", "entry_price_raw"):
        if hasattr(pos, attr):
            try:
                return float(getattr(pos, attr))
            except Exception:
                pass
    return 0.0






def _risk_sl_vol_multiple(
    out: List[TradeSignal],
    instrument: str,
    side: Side,
    ts,
    feature_map: Optional[Dict[str, pd.Series]],
    px: float,
    legs: List[Dict[str, Any]],
    vwap_entry: float,
    scope: str,
    params: Dict[str, Any],
) -> None:

    import math
    if feature_map is None:
        return

    vol_key   = str(params.get("key", ""))
    price_key = str(params.get("price_key", "")) 
    if not vol_key or vol_key not in feature_map or not price_key or price_key not in feature_map:
        return
    

    s_vol  = feature_map[vol_key]
    s_px   = feature_map[price_key]
    if ts not in s_vol.index or ts not in s_px.index:
        return

    # valeurs courantes (t) et d'hier (t-1) via shift(1).loc[ts]
    vol_t  = s_vol.loc[ts]
    vol_tm1 = s_vol.shift(1).loc[ts]
    px_t   = s_px.shift(1).loc[ts]
    px_tm1 = s_px.shift(2).loc[ts]

    if pd.isna(vol_t) or pd.isna(vol_tm1) or pd.isna(px_t) or pd.isna(px_tm1):
        return

    k = float(params.get("k", 3.0))
    unit = str(params.get("unit", "return"))
    annualized = bool(params.get("annualized", True))
    rr = params.get("reduce_ratio", None)
    reduce_ratio = float(rr) if rr is not None else None

    def dist(ep: float, v: float) -> float:
        if unit == "return":
            vday = v / math.sqrt(252.0) if annualized else v
            return float(ep) * (k * vday)
        else:
            return k * float(v)

    def hit(curr_px: float, ep: float, v: float) -> bool:
        d = dist(ep, v)
        if side == Side.LONG:
            return curr_px <= float(ep) - d
        else:
            return curr_px >= float(ep) + d

    def emit(meta: Dict[str, Any]) -> None:
        if reduce_ratio >0:
            out.append(TradeSignal(action=Action.REDUCE, instrument=instrument, side=side,
                                   reduce_ratio=reduce_ratio, meta=meta))
        else:
            out.append(TradeSignal(action=Action.CLOSE, instrument=instrument, side=side, meta=meta))


    meta_base = {"risk": "sl_vol_multiple", "key": vol_key, "price_key": price_key, "k": k, "unit": unit}

    if scope == "per_leg":
        for leg in legs:
            ep = float(leg["entry_price"])
            prev = hit(px_tm1, ep, vol_tm1)
            curr = hit(px_t,   ep, vol_t)
            if (not prev) and curr:   # CROSS uniquement
                emit(meta_base)
    else:
        ep = float(vwap_entry)
        prev = hit(px_tm1, ep, vol_tm1)
        curr = hit(px_t,   ep, vol_t)
        if (not prev) and curr:
            emit(meta_base)


def _risk_tp_vol_multiple(
    out: List[TradeSignal],
    instrument: str,
    side: Side,
    ts,
    feature_map: Optional[Dict[str, pd.Series]],
    px: float,
    legs: List[Dict[str, Any]],
    vwap_entry: float,
    scope: str,
    params: Dict[str, Any],
) -> None:

    import math
    if feature_map is None:
        return

    vol_key   = str(params.get("key", ""))
    price_key = str(params.get("price_key", ""))
    if not vol_key or vol_key not in feature_map or not price_key or price_key not in feature_map:
        return

    s_vol  = feature_map[vol_key]
    s_px   = feature_map[price_key]
    if ts not in s_vol.index or ts not in s_px.index:
        return

    vol_t  = s_vol.loc[ts]
    vol_tm1 = s_vol.shift(1).loc[ts]
    px_t   = s_px.shift(1).loc[ts]
    px_tm1 = s_px.shift(2).loc[ts]

    if pd.isna(vol_t) or pd.isna(vol_tm1) or pd.isna(px_t) or pd.isna(px_tm1):
        return

    k = float(params.get("k", 2.0))
    unit = str(params.get("unit", "return"))
    annualized = bool(params.get("annualized", True))
    rr = params.get("reduce_ratio", None)
    reduce_ratio = float(rr) if rr is not None else None

    def dist(ep: float, v: float) -> float:
        if unit == "return":
            vday = v / math.sqrt(252.0) if annualized else v
            return float(ep) * (k * vday)
        else:
            return k * float(v)

    def hit(curr_px: float, ep: float, v: float) -> bool:
        d = dist(ep, v)
        if side == Side.LONG:
            return curr_px >= float(ep) + d   # favorable LONG
        else:
            return curr_px <= float(ep) - d   # favorable SHORT
        
        
    def emit(meta: Dict[str, Any]) -> None:
        if reduce_ratio >0:
            out.append(TradeSignal(action=Action.REDUCE, instrument=instrument, side=side,
                                   reduce_ratio=reduce_ratio, meta=meta))
        else:
            out.append(TradeSignal(action=Action.CLOSE, instrument=instrument, side=side, meta=meta))


    meta_base = {"risk": "tp_vol_multiple", "key": vol_key, "price_key": price_key, "k": k, "unit": unit}

    if scope == "per_leg":
        for leg in legs:
            ep = float(leg["entry_price"])
            prev = hit(px_tm1, ep, vol_tm1)
            curr = hit(px_t,   ep, vol_t)
            if (not prev) and curr:   # CROSS uniquement
                emit(meta_base)
    else:
        ep = float(vwap_entry)
        prev = hit(px_tm1, ep, vol_tm1)
        curr = hit(px_t,   ep, vol_t)
        if (not prev) and curr:
            emit(meta_base)












def _risk_reduce_feature_cross_1d(
    out: List[TradeSignal],
    instrument: str,
    side: Side,
    ts,
    feature_map: Optional[Dict[str, pd.Series]],
    legs: List[Dict[str, Any]],
    vwap_entry: float,
    scope: str,
    reduce_ratio: float,
    params: Dict[str, Any],
) -> None:
    """
    Scale-out when a 1D feature crosses a threshold (e.g., Z-score crosses 0, RSI crosses 50).

    params:
      key: str                     # feature key in feature_map
      threshold: float             # value to cross (e.g., 0 for zscore, 50 for RSI)
      long_dir: str                # 'up' | 'down' | 'both' | 'none'   (trigger direction when side == LONG)
      short_dir: str               # 'up' | 'down' | 'both' | 'none'   (trigger direction when side == SHORT)
      touch_ok: bool               # if True, allow equality as crossing boundary (default False)
    """
    if feature_map is None:
        return
    
    key = str(params.get("key", ""))
    if key == "" or key not in feature_map:
        return

    s = feature_map[key]
    if not isinstance(s, pd.Series):
        return
    if ts not in s.index:
        return

    try:
        loc = s.index.get_loc(ts)
        if isinstance(loc, slice):
            loc = loc.start
    except KeyError:
        return

    if loc == 0:
        return

    prev_val = s.iloc[loc - 1]
    curr_val = s.iloc[loc]
    thr = float(params.get("threshold", 0.0))
    touch_ok = bool(params.get("touch_ok", False))

    def _cross_up(pv: float, cv: float, t: float) -> bool:
        return (pv < t and cv > t) or (touch_ok and pv <= t and cv >= t)

    def _cross_down(pv: float, cv: float, t: float) -> bool:
        return (pv > t and cv < t) or (touch_ok and pv >= t and cv <= t)

    long_dir = str(params.get("long_dir", "both"))
    short_dir = str(params.get("short_dir", "both"))

    want_up = want_down = False
    if side == Side.LONG:
        want_up   = long_dir in ("up", "both")
        want_down = long_dir in ("down", "both")
    else:
        want_up   = short_dir in ("up", "both")
        want_down = short_dir in ("down", "both")

    crossed = (want_up and _cross_up(prev_val, curr_val, thr)) or (want_down and _cross_down(prev_val, curr_val, thr))
    if not crossed:
        return

    if scope == "per_leg":
        for _ in legs:
            out.append(TradeSignal(action=Action.REDUCE, instrument=instrument, side=side, reduce_ratio=reduce_ratio,
                                   meta={"risk": "reduce_feature_cross_1d", "key": key, "threshold": thr}))
    else:
        out.append(TradeSignal(action=Action.REDUCE, instrument=instrument, side=side, reduce_ratio=reduce_ratio,
                               meta={"risk": "reduce_feature_cross_1d", "key": key, "threshold": thr}))


