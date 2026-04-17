import pandas as pd


def spot_mid(df_multi: pd.DataFrame) -> pd.DataFrame:
    """Compute MID from a SPOT MultiIndex (first family with BID & OFFER)."""
    if not isinstance(df_multi.columns, pd.MultiIndex):
        raise TypeError("Expected MultiIndex columns (family, field).")

    bid_col = offer_col = None
    fam = None
    for fam_candidate in df_multi.columns.get_level_values(0).unique():
        sub = df_multi[fam_candidate]
        u = {c.upper(): c for c in sub.columns}
        if "BID" in u and "OFFER" in u:
            fam = fam_candidate
            bid_col, offer_col = u["BID"], u["OFFER"]
            break
    if fam is None:
        raise ValueError("No family with BID/OFFER found in SPOT.")

    sub = df_multi[fam].copy()
    bid = pd.to_numeric(sub[bid_col], errors="coerce")
    offer = pd.to_numeric(sub[offer_col], errors="coerce")
    bid_f = bid.fillna(offer)
    offer_f = offer.fillna(bid)
    mid = 0.5 * (bid_f + offer_f)

    out = pd.DataFrame({"MID": mid.astype("float64")}).sort_index()
    if not out.index.is_unique:
        out = out.groupby(level=0).last()
    return out


def spot_spread_mid(spot1_mid: pd.DataFrame, spot2_mid: pd.DataFrame, name: str = "MID") -> pd.DataFrame:
    """Return spread MID = spot1 - spot2 (both single-col MID DataFrames)."""
    df = pd.merge(spot1_mid, spot2_mid, left_index=True, right_index=True, how="inner")
    df.columns = ["MID_1", "MID_2"]
    spread = (df["MID_1"] - df["MID_2"]).astype("float64").rename(name)
    out = spread.to_frame().sort_index()
    if not out.index.is_unique:
        out = out.groupby(level=0).last()
    return out


