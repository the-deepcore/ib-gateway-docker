from __future__ import annotations

from typing import Union

import numpy as np
import pandas as pd

DEFAULT_PERIODS_PER_YEAR = 252
DEFAULT_RISK_FREE = 0.04

def _series(equity: Union[pd.Series, pd.DataFrame], col: str = "TotalValue") -> pd.Series:
    s = equity[col] if isinstance(equity, pd.DataFrame) else pd.Series(equity, dtype=float)
    s = s.dropna()
    s.index = pd.to_datetime(s.index).tz_localize(None)
    return s.astype(float)

def daily_returns(equity: Union[pd.Series, pd.DataFrame], col: str = "TotalValue") -> pd.Series:
    s = _series(equity, col)
    return s.pct_change().dropna()

def annualized_volatility(
    equity: Union[pd.Series, pd.DataFrame],
    col: str = "TotalValue",
    periods_per_year: int = DEFAULT_PERIODS_PER_YEAR,
) -> float:
    r = daily_returns(equity, col)
    if r.empty:
        return float("nan")
    return float(r.std(ddof=0) * np.sqrt(periods_per_year))

def sharpe_ratio(
    equity: Union[pd.Series, pd.DataFrame],
    col: str = "TotalValue",
    rf: float = DEFAULT_RISK_FREE,
    periods_per_year: int = DEFAULT_PERIODS_PER_YEAR,
) -> float:
    r = daily_returns(equity, col)
    if r.empty:
        return float("nan")
    mu_ann = float(r.mean() * periods_per_year)
    vol_ann = float(r.std() * np.sqrt(periods_per_year))
    if vol_ann <= 0 or np.isnan(vol_ann):
        return float("nan")
    return float((mu_ann - rf) / vol_ann)


def cagr(equity: Union[pd.Series, pd.DataFrame], col: str = "TotalValue") -> float:
    s = _series(equity, col)
    if s.empty:
        return float("nan")
    start_val, end_val = float(s.iloc[0]), float(s.iloc[-1])
    if start_val <= 0:
        return float("nan")
    days = (s.index[-1] - s.index[0]).days
    if days <= 0:
        return float("nan")
    years = days / 365.25
    try:
        return float((end_val / start_val) ** (1.0 / years) - 1.0)
    except Exception:
        return float("nan")

def drawdown_series(equity: Union[pd.Series, pd.DataFrame], col: str = "TotalValue") -> pd.Series:
    s = _series(equity, col)
    if s.empty:
        return pd.Series(dtype=float)
    peak = s.cummax()
    return (s / peak) - 1.0  # [-1, 0]

def max_drawdown(equity: Union[pd.Series, pd.DataFrame], col: str = "TotalValue") -> float:
    dd = drawdown_series(equity, col)
    return float(dd.min()) if not dd.empty else float("nan")

def total_return_pct(equity: Union[pd.Series, pd.DataFrame], col: str = "TotalValue") -> float:
    s = _series(equity, col)
    if s.empty:
        return float("nan")
    start, end = float(s.iloc[0]), float(s.iloc[-1])
    if start == 0:
        return float("inf") if end > 0 else float("nan")
    return float((end / start - 1.0) * 100.0)
