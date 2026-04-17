from typing import List, Optional, Union

import pandas as pd

from mvc_core.domain.clock.clock_data import Clock

# --------- Builders ---------

def build_from_index(index: pd.DatetimeIndex) -> Clock:
    """Build a Clock from an existing DatetimeIndex (tz-naive)."""
    if isinstance(index, pd.DatetimeIndex) and index.tz is not None:
        index = index.tz_localize(None)
    index = index.unique().sort_values()
    return Clock(index=index, cursor=0)

def build_from_intersection(indices: List[pd.DatetimeIndex]) -> Clock:
    """Build a Clock from the sorted intersection of multiple indices."""
    if not indices:
        raise ValueError("indices must not be empty")
    idx = indices[0]
    for other in indices[1:]:
        # drop tz if any, then intersect
        if isinstance(idx, pd.DatetimeIndex) and idx.tz is not None:
            idx = idx.tz_localize(None)
        if isinstance(other, pd.DatetimeIndex) and other.tz is not None:
            other = other.tz_localize(None)
        idx = idx.intersection(other)
    idx = idx.unique().sort_values()
    return Clock(index=idx, cursor=0)

def build_from_range(
    start: pd.Timestamp,
    end: pd.Timestamp,
    freq: str,
    cursor: int = 0,
) -> Clock:
    """
    Build a Clock from a date range.

    Parameters
    ----------
    start : pd.Timestamp
    end : pd.Timestamp
    freq : str
        Pandas frequency string (e.g. "1min", "5min", "1H", "1D").
    cursor : int

    Returns
    -------
    Clock
    """
    idx = pd.date_range(start=start, end=end, freq=freq, tz="UTC")
    return Clock(index=idx, cursor=cursor)


# --------- Navigation ---------



def tick(clock: Clock, steps: int = 1) -> bool:
    """
    Advance cursor by `steps` (clamped to the last index item).

    Returns
    -------
    bool
        True if there is at least one further step possible after this move.
    """
    next_pos = clock.cursor + steps
    if next_pos > len(clock.index) - 1:
        next_pos = len(clock.index) - 1
    clock.cursor = next_pos
    return clock.cursor < len(clock.index) - 1


def now(clock: Clock) -> pd.Timestamp:
    """
    Return the current timestamp at the cursor.
    """
    return clock.index[clock.cursor]

# --------- Alignment ---------

def align_to_clock(s: pd.Series, clock: Clock, method: Optional[str] = None) -> pd.Series:
    """Reindex a Series on clock.index (UTC). method: 'ffill'|'bfill'|None."""

    idx = s.index
    
    if not isinstance(idx, pd.DatetimeIndex):
        raise TypeError("Series must have a DatetimeIndex")

    if idx.tz is None:
        s = s.tz_localize("UTC")
    else:
        s = s.tz_convert("UTC")

    has_duplicates = s.index.duplicated(keep="last")
    s = s[has_duplicates == False]  
    s = s.sort_index()

    out = s.reindex(clock.index)
    if method == "ffill":
        out = out.ffill()
    elif method == "bfill":
        out = out.bfill()
    elif method == "dropna":
        out = out.dropna()
    elif method is None:
        pass
    else:
        raise ValueError("align_to_clock: unsupported method")

    return out


def _to_naive(ts: pd.Timestamp) -> pd.Timestamp:
    return ts.tz_localize(None) if getattr(ts, "tzinfo", None) is not None else ts

def _to_naive_index(idx: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Return tz-naive DatetimeIndex."""
    if isinstance(idx, pd.DatetimeIndex) and idx.tz is not None:
        return idx.tz_localize(None)
    return idx

def _to_tz_aware(ts: Union[str, pd.Timestamp], tz: Optional[str] = "UTC") -> pd.Timestamp:
    base = pd.Timestamp(ts)
    if tz is None:
        return base.tz_localize(None)
    if base.tzinfo is None:
        return base.tz_localize(tz)
    return base.tz_convert(tz)


def slice_clock(clock: Clock, start_date: Optional[str], end_date: Optional[str]) -> Clock:
    """Return a new Clock limited to [start, end], cursor reset to 0."""
    idx = clock.index
    if isinstance(idx, pd.DatetimeIndex) and idx.tz is not None:
        idx = idx.tz_localize(None)


    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)

    if start is not None:
        start = _to_naive(pd.Timestamp(start))
        idx = idx[idx >= start]
    if end is not None:
        end = _to_naive(pd.Timestamp(end))
        idx = idx[idx <= end]

    if len(idx) == 0:
        raise ValueError("slice_clock: empty range after filtering.")

    return Clock(index=idx, cursor=0)
