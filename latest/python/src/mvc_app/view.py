from __future__ import annotations

from typing import Any, Dict, Optional

from matplotlib.figure import Figure
import pandas as pd

from mvc_core.optimize.oos_reconstruction_services import crop_oos_output
from mvc_core.plotting.figures import plot_price_equity, plot_price_equity_indicator, plot_price_only


def build_wf_oos_figure_from_oos(
    *,
    oos: Dict[str, Any],
    instrument: str,
    title_suffix: str = "",
    start_date : Optional[str] = None,
    end_date : Optional[str] = None,
) -> Figure:

    if start_date is None:
        start_date = oos["equity_oos_df"].index[0]
    if end_date is None:
        end_date = oos["equity_oos_df"].index[-1]


    display_initial_value = (
        float(oos.get("display_initial_value"))
        if oos.get("display_initial_value") is not None
        else float(oos.get("initial_inv") or 0.0) or None
    )
    oos = crop_oos_output(
        oos,
        start_date=start_date,
        end_date=end_date,
        initial_value=None,
        display_initial_value=display_initial_value,
    )

    price = oos["price"]
    equity_df: pd.DataFrame = oos["equity_oos_df"]
    decisions = oos.get("decisions")
    indicator = oos.get("indicator")
    thresholds = oos.get("thresholds")

    title = f"OOS — {instrument}"
    if title_suffix:
        title += f" ({title_suffix})"

    fig = plot_price_equity_indicator(
        price=price,
        equity=equity_df,
        instrument=instrument,
        indicator=({"Source": indicator} if indicator is not None else None),
        thresholds=thresholds,
        decisions=decisions,
        title=title,
    )
    return fig


def build_wf_oos_figure_from_oos_no_indicator(
    *,
    oos: Dict[str, Any],
    instrument: str,
    title_suffix: str = "",
    start_date : Optional[str] = None,
    end_date : Optional[str] = None,
) -> Figure:
    """
    Same as build_wf_oos_figure_from_oos but without the indicator panel.
    """
    if start_date is None:
        start_date = oos["equity_oos_df"].index[0]
    if end_date is None:
        end_date = oos["equity_oos_df"].index[-1]

    display_initial_value = (
        float(oos.get("display_initial_value"))
        if oos.get("display_initial_value") is not None
        else float(oos.get("initial_inv") or 0.0) or None
    )
    oos = crop_oos_output(
        oos,
        start_date=start_date,
        end_date=end_date,
        initial_value=None,
        display_initial_value=display_initial_value,
    )

    price = oos["price"]
    equity_df: pd.DataFrame = oos["equity_oos_df"]
    decisions = oos.get("decisions")

    title = f"OOS — {instrument}"
    if title_suffix:
        title += f" ({title_suffix})"

    fig = plot_price_equity(
        price=price,
        equity=equity_df,
        instrument=instrument,
        decisions=decisions,
        title=title,
    )
    return fig


def build_wf_oos_figure_price_only(
    *,
    oos: Dict[str, Any],
    instrument: str,
    title_suffix: str = "",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Figure:
    """
    Plot uniquement la courbe de prix avec les markers de décisions.
    Pas d'indicateur, pas de suivi PnL.
    """
    if start_date is None:
        start_date = oos["equity_oos_df"].index[0]
    if end_date is None:
        end_date = oos["equity_oos_df"].index[-1]

    display_initial_value = (
        float(oos.get("display_initial_value"))
        if oos.get("display_initial_value") is not None
        else float(oos.get("initial_inv") or 0.0) or None
    )
    oos = crop_oos_output(
        oos,
        start_date=start_date,
        end_date=end_date,
        initial_value=None,
        display_initial_value=display_initial_value,
    )

    price = oos["price"]
    decisions = oos.get("decisions")

    title = f"OOS — {instrument}"
    if title_suffix:
        title += f" ({title_suffix})"

    fig = plot_price_only(
        price=price,
        instrument=instrument,
        decisions=decisions,
        title=title,
    )
    return fig
