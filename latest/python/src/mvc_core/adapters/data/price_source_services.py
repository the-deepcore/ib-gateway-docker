from typing import Optional

import pandas as pd

from mvc_core.adapters.data.price_source_data import PriceSource
from mvc_core.domain.clock.clock_data import Clock
from mvc_core.domain.clock.clock_services import align_to_clock


def select_spot_price(
    spot_df: pd.DataFrame,
    price_source: PriceSource,
    clock: Clock,
    fill_method: Optional[str] = None,
    as_date_index: bool = True
) -> pd.Series:
    """Select SPOT price column by kind and align to clock."""
    if price_source.kind not in price_source.col_map:
        raise KeyError("Unknown price kind")
    col = price_source.col_map[price_source.kind]
    if col not in spot_df.columns:
        # If df is a single-col MID DataFrame from spot_mid, accept that
        if price_source.kind == "mid" and "MID" in spot_df.columns:
            col = "MID"
        else:
            raise KeyError("Selected price column not in spot DataFrame")
    s = pd.to_numeric(spot_df[col], errors="coerce")
    out = align_to_clock(s, clock, method=fill_method)
    if as_date_index:
        out.index = out.index.tz_localize(None).normalize()
    return out


def select_futures_price(
    futures_df_ohlc: pd.DataFrame,
    price_source: PriceSource,
    clock: Clock,
    fill_method: Optional[str] = None,
    as_date_index: bool = True
) -> pd.Series:
    """Select FUTURES price column ('Close' by default) and align to clock."""
    col = price_source.col_map.get(price_source.kind, "Close")
    candidates = (col, col.upper(), col.capitalize())
    found = next((c for c in candidates if c in futures_df_ohlc.columns), None)
    if found is None:
        raise KeyError("Selected price column not in futures DataFrame")

    s = pd.to_numeric(futures_df_ohlc[found], errors="coerce")
    out = align_to_clock(s, clock, method=fill_method)
    if as_date_index:
        out.index = out.index.tz_localize(None).normalize()
    return out



# TODO Permettre de récupérer plusieurs colonnes à la fois pour un futures (ex kind = ['Open', 'CLose'], => select_futures_price -> Union[pd.Series, pd.DataFrame])
