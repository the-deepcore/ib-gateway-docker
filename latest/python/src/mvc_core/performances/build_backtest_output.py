from typing import Dict, Optional

import pandas as pd

from mvc_core.domain.clock.clock_services import _to_naive, _to_naive_index
from mvc_core.domain.market.contract_specs import resolve_contract_spec


def _series_naive(s: pd.Series) -> pd.Series:
    """Ensure Series index is tz-naive, float dtype, sorted, no NA."""
    if s is None or len(s) == 0:
        return pd.Series(dtype=float)
    out = pd.Series(s, dtype=float).dropna()
    out.index = pd.to_datetime(out.index)
    out.index = _to_naive_index(out.index)
    return out.sort_index()


def equity_series_from_points(
    equity_points: Dict[pd.Timestamp, float],
    clock_index: pd.DatetimeIndex,
) -> pd.Series:
    """Dict[timestamp->value] -> Series 'TotalValue', alignée à la clock, ffill."""
    if not equity_points:
        return pd.Series(dtype=float, name="TotalValue")

    s = pd.Series(equity_points, dtype=float).sort_index()
    s.index = pd.to_datetime(s.index)
    s.index = _to_naive_index(s.index)

    clk = _to_naive_index(pd.DatetimeIndex(clock_index))
    s = s.reindex(clk).ffill()
    s.name = "TotalValue"
    return s




def buy_and_hold_from_price(
    bench_price: Optional[pd.Series],
    clock_index: pd.DatetimeIndex,
    initial_inv: float,
    bench_notional: Optional[float] = None,
    bench_key: Optional[str] = None,
    start_date: Optional[str] = None,  
) -> pd.Series:
    """Buy&Hold: notionnel converti en lots entiers + cash résiduel, aligné clock."""
    if bench_price is None or len(bench_price) == 0:
        return pd.Series(dtype=float, name="Buy&Hold")

    px = _series_naive(bench_price)
    clk = _to_naive_index(pd.DatetimeIndex(clock_index))

    # ✅ aligner sur la clock
    px = px.reindex(clk).ffill().bfill()
    if px.empty:
        return pd.Series(dtype=float, name="Buy&Hold")

    # ✅ Utiliser start_date si fourni, sinon premier prix valide
    if start_date is not None:
        start_ts = pd.Timestamp(start_date)
        # S'assurer que start_ts est tz-naive pour la comparaison
        if start_ts.tz is not None:
            start_ts = start_ts.tz_localize(None)
        if start_ts in px.index:
            base = float(px.loc[start_ts])
        else:
            # Trouver le premier prix >= start_date
            mask = px.index >= start_ts
            if mask.any():
                base = float(px[mask].iloc[0])
            else:
                base = float(px.iloc[0])
    else:
        base = float(px.iloc[0])
    
    if base == 0.0:
        return pd.Series(dtype=float, name="Buy&Hold")

    notional = float(bench_notional) if bench_notional is not None else float(initial_inv)

    multiplier = 1.0
    if bench_key:
        try:
            multiplier = float(resolve_contract_spec(bench_key).multiplier)
        except Exception:
            pass

    lots = int(notional // (multiplier * base))
    cash = notional - float(lots) * multiplier * base

    bh = float(lots) * float(multiplier) * px + cash
    bh.name = "Buy&Hold"

    return bh.reindex(clk)


def make_equity_df(
    equity_points: Dict[pd.Timestamp, float],
    clock_index: pd.DatetimeIndex,
    bench_price: Optional[pd.Series],
    initial_inv: float,
    bench_notional: Optional[float] = None,
    display_initial_value: Optional[float] = None,
    bench_key: Optional[str] = None,  

) -> pd.DataFrame:
    """Assemble un DataFrame [TotalValue, Buy&Hold], aligné à la clock.

    display_initial_value permet de rebaser les deux courbes (strat et bench)
    à un niveau visuel commun, tout en conservant le notional réel utilisé pour
    le calcul de PnL (bench_notional pour le buy&hold).
    """
    eq = equity_series_from_points(equity_points, clock_index)
    start_date = str(eq.index[0]) if not eq.empty else None

    bh = buy_and_hold_from_price(bench_price, clock_index, initial_inv, bench_notional, bench_key, start_date)
    df = pd.concat([eq, bh], axis=1)

    if display_initial_value is not None and not df.empty:
        start_date = str(_to_naive(df.index[0]))
        end_date = str(_to_naive(df.index[-1]))
        df = crop_equity_series(df, start_date, end_date, initial_value=float(display_initial_value))

    return df


def crop_equity_series(
    equity_df: pd.DataFrame,
    start_date: str,
    end_date: str,
    initial_value: Optional[float] = None,
) -> pd.DataFrame:
    """Crop equity/benchmark and rebase to the provided or starting level."""
    eq_slice = equity_df.loc[start_date:end_date]
    if eq_slice.empty:
        return eq_slice

    base_total = float(eq_slice["TotalValue"].iloc[0])
    base_bh = float(eq_slice["Buy&Hold"].iloc[0]) if "Buy&Hold" in eq_slice.columns else None

    level = float(initial_value) if initial_value is not None else base_total
    level_bh = float(initial_value) if initial_value is not None else (base_bh if base_bh is not None else level)

    s = eq_slice["TotalValue"] - base_total + level
    df = pd.DataFrame({"TotalValue": s})

    if "Buy&Hold" in eq_slice.columns:
        s_bh = eq_slice["Buy&Hold"] - (base_bh if base_bh is not None else 0.0) + level_bh
        df["Buy&Hold"] = s_bh

    return df





























