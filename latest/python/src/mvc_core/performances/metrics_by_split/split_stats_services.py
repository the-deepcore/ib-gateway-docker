from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd

from mvc_core.domain.clock.clock_services import _to_naive
from mvc_core.optimize.wf_history.wf_history_data import WFCalibrationRun
from mvc_core.performances.metrics_by_split.split_stats_data import SplitMetrics
from mvc_core.performances.metrics_services import (
    annualized_volatility,
    cagr,
    max_drawdown,
    sharpe_ratio,
    total_return_pct,
)


def compute_wf_window_stats(
    *,
    wf_run: WFCalibrationRun,
    equity_oos_df: pd.DataFrame,
    decisions: List[Dict[str, Any]],
) -> List[SplitMetrics]:

    if "TotalValue" not in equity_oos_df.columns:
        raise ValueError("equity_oos_df doit contenir une colonne 'TotalValue'.")

    stats: List[SplitMetrics] = []

    for i, split in enumerate(wf_run.splits, start=1):
        test_start = _to_naive(pd.to_datetime(split.test_start)) 
        test_end = _to_naive(pd.to_datetime(split.test_end))      

        eq_slice = equity_oos_df["TotalValue"].loc[test_start:test_end]
        if eq_slice.empty:
            continue

        # --- Metrics sur la fenêtre ---
        sharpe = sharpe_ratio(eq_slice)
        mdd = max_drawdown(eq_slice)*100
        total_ret = total_return_pct(eq_slice)
        cagr_ = cagr(eq_slice)
        vol_ = annualized_volatility(eq_slice)

        start_ts = _to_naive(pd.to_datetime(test_start))
        end_ts = _to_naive(pd.to_datetime(test_end))

        nb_trades = 0
        for dec in decisions:
            dt = dec.get("date")
            if dt is None:
                continue

            dt_naive = _to_naive(dt)
            action = (dec.get("action") or "").upper()

            if start_ts <= dt_naive <= end_ts and action.startswith("CLOSE"):
                nb_trades += 1

        stats.append(
            SplitMetrics(
                split_id=i,
                # train_start=str(split.train_start),
                # train_end=str(split.train_end),
                test_start=str(split.test_start),
                test_end=str(split.test_end),
                # period_label=f"{split.test_start} -> {split.test_end}",
               
                nb_trades=nb_trades,
                sharpe=sharpe,
                mdd=mdd,
                total_return_pct=total_ret,
                cagr=cagr_,
                vol=vol_,
            )
        )

    return stats
