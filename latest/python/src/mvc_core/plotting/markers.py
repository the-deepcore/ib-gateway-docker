# mvc_core/plotting/markers.py
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

COLORS = {
    "buy":   "#1e8f3e",
    "sell":  "#c12b2b",
    "tp":    "#1e8f3e",
    "sl":    "#c12b2b",
    "close": "#aaaaaa",
    "flat":  "#ff9800",  # Orange pour les signaux flat (désaccord)
    "outline": "#000000",
}

def _to_df(decisions) -> pd.DataFrame:
    if decisions is None:
        return pd.DataFrame()
    return decisions.copy() if isinstance(decisions, pd.DataFrame) else pd.DataFrame(decisions)

def _pick(df: pd.DataFrame, candidates) -> str | None:
    for c in candidates:
        if c in df.columns:
            return c
    return None



def add_decision_markers(fig: go.Figure, decisions, row: int = 1, col: int = 1) -> None:
    """
    Add only entry markers:
      - Long Entry  -> green triangle-up
      - Short Entry -> red triangle-down
    Ignore CLOSE / REDUCE / TP / SL.
    """
    df = _to_df(decisions)
    if df.empty:
        return

    # columns autodetect
    date_col   = _pick(df, ["date","ts","timestamp","time","exec_date","Date"])
    action_col = _pick(df, ["action","decision","Action","Decision","act"])
    price_col  = _pick(df, ["price","exec_price","fill_price","Close","close","PX","PX_Close"])

    if date_col is None:
        if isinstance(df.index, pd.DatetimeIndex):
            df = df.reset_index().rename(columns={"index": "date"})
            date_col = "date"
        else:
            return
    if action_col is None or price_col is None:
        return

    # normalize
    df["date"] = pd.to_datetime(df[date_col]).dt.tz_localize(None)
    df["action"] = df[action_col].astype(str).str.upper()
    df["price"] = pd.to_numeric(df[price_col], errors="coerce")

    # entries only
    long_entry  = df[df["action"].isin(["OPEN_LONG", "REVERSE_TO_LONG"])].dropna(subset=["date","price"])
    short_entry = df[df["action"].isin(["OPEN_SHORT","REVERSE_TO_SHORT"])].dropna(subset=["date","price"])

    if not long_entry.empty:
        fig.add_trace(
            go.Scatter(
                x=long_entry["date"], y=long_entry["price"],
                mode="markers", name="Long Entry",
                marker=dict(symbol="triangle-up", size=12, color=COLORS["buy"],
                            line=dict(color=COLORS["outline"], width=1)),
                hovertemplate="Long Entry<br>%{x|%b %d, %Y}<br>Px: %{y:.2f}<extra></extra>",
            ),
            row=row, col=col
        )

    if not short_entry.empty:
        fig.add_trace(
            go.Scatter(
                x=short_entry["date"], y=short_entry["price"],
                mode="markers", name="Short Entry",
                marker=dict(symbol="triangle-down", size=12, color=COLORS["sell"],
                            line=dict(color=COLORS["outline"], width=1)),
                hovertemplate="Short Entry<br>%{x|%b %d, %Y}<br>Px: %{y:.2f}<extra></extra>",
            ),
            row=row, col=col
        )

    # FLAT signals (disagreement between strategies in fusion mode)
    flat_signals = df[df["action"] == "FLAT"].dropna(subset=["date","price"])
    if not flat_signals.empty:
        fig.add_trace(
            go.Scatter(
                x=flat_signals["date"], y=flat_signals["price"],
                mode="markers", name="Flat (Disagreement)",
                marker=dict(symbol="x", size=10, color=COLORS["flat"],
                            line=dict(color=COLORS["outline"], width=1)),
                hovertemplate="Flat (Disagreement)<br>%{x|%b %d, %Y}<br>Px: %{y:.2f}<extra></extra>",
            ),
            row=row, col=col
        )
