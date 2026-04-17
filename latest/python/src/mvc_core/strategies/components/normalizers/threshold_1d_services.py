from typing import Any, Dict, Optional

import pandas as pd

from mvc_core.domain.enums import CrossSense, Side, TriggerMode

from .threshold_1d_data import Threshold1DConfig


def normalize_1d_to_fls(
    clock_index: pd.DatetimeIndex,
    score: pd.Series,
    cfg: Threshold1DConfig,
    low_series: Optional[pd.Series] = None,
    high_series: Optional[pd.Series] = None,
    state: Optional[Dict[str, Any]] = None,
) -> pd.DataFrame:
    """Return H/L/S=0|1 DataFrame aligned to clock_index."""
    # thresholds as Series (either from cfg or provided series)
    s = score.astype(float).copy()
    s.index = pd.to_datetime(s.index)

    low = low_series if low_series is not None else pd.Series(float(cfg.low), index=s.index)
    high = high_series if high_series is not None else pd.Series(float(cfg.high), index=s.index)
    low = pd.to_numeric(low.reindex(s.index), errors="coerce")
    high = pd.to_numeric(high.reindex(s.index), errors="coerce")

    # regions (internal labels only)
    curr = pd.Series(index=s.index, dtype="object")
    curr[s < low] = "below"
    curr[(s >= low) & (s <= high)] = "inside"
    curr[s > high] = "above"
    prev = curr.shift(1)

    flat = pd.Series(1, index=s.index, dtype=int)
    lng  = pd.Series(0, index=s.index, dtype=int)
    sht  = pd.Series(0, index=s.index, dtype=int)

    mode = cfg.mode if isinstance(cfg.mode, TriggerMode) else TriggerMode(str(cfg.mode).lower())
    sense = cfg.cross_sense if isinstance(cfg.cross_sense, CrossSense) else CrossSense(str(cfg.cross_sense).lower())


# TODO POSITION mode is obsolete, refactoring 
    if mode == TriggerMode.POSITION:
        cond_long  = (prev != "above") & (curr == "above")
        cond_short = (prev != "below") & (curr == "below")

    elif mode == TriggerMode.CROSS:
        if sense == CrossSense.OUTSIDE_TO_INSIDE:
            cond_long  = (prev == "below") & (curr != "below")
            cond_short = (prev == "above") & (curr != "above")
        elif sense == CrossSense.INSIDE_TO_OUTSIDE:
            cond_long  = (prev != "below") & (curr == "below")
            cond_short = (prev != "above") & (curr == "above")
        else:
    # elif mode == TriggerMode.CROSS:
    #     if sense == CrossSense.OUTSIDE_TO_INSIDE:
    #         cond_long  = (prev == "below") & (curr == "inside")
    #         cond_short = (prev == "above") & (curr == "inside")
    #     elif sense == CrossSense.INSIDE_TO_OUTSIDE:
    #         cond_long  = (prev == "inside") & (curr == "below")
    #         cond_short = (prev == "inside") & (curr == "above")
    #     else:
            raise ValueError("unknown cross_sense")
    else:
        raise ValueError("unknown mode")

    if getattr(cfg, "start_hold", True) and len(s.index) > 0:
        first_ts = s.index[0]
        cond_long.loc[first_ts] = False
        cond_short.loc[first_ts] = False

    lng[cond_long] = 1
    sht[cond_short] = 1
    flat[(lng == 1) | (sht == 1)] = 0

    fls = pd.DataFrame({Side.FLAT: flat, Side.LONG: lng, Side.SHORT: sht})
    # align to clock
    fls = fls.reindex(pd.DatetimeIndex(clock_index)).fillna({Side.FLAT: 1, Side.LONG: 0, Side.SHORT: 0}).astype(int)
    return fls
