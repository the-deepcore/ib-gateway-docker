from pathlib import Path
from typing import Dict, List, Optional, Union

import pandas as pd


def _resolve(base_dir: Union[str, Path], file_name: Union[str, Path]) -> Path:
    """Resolve to absolute existing Path."""
    base = Path(base_dir)
    p = Path(file_name)
    if not p.is_absolute():
        p = base / p
    if not p.exists():
        raise FileNotFoundError(p)
    return p


def _read_excel_raw(path: Union[str, Path], header: Optional[int] = None) -> pd.DataFrame:
    """Read Excel as-is (no header)."""
    return pd.read_excel(path, header=header)


# ---------- SPOT (Deepcore) ----------

def load_spot_excel(file_name: Union[str, Path], data_dir: Union[str, Path] = "data") -> pd.DataFrame:
    """Load Deepcore SPOT Excel and return cleaned MultiIndex DataFrame."""
    path = _resolve(data_dir, file_name)
    raw = _read_excel_raw(path, header=None)
    return clean_spot_raw(raw)


def clean_spot_raw(data: pd.DataFrame) -> pd.DataFrame:
    """Normalize Deepcore SPOT to MultiIndex with DATE index."""
    columns = data.iloc[1].ffill()
    sub_columns = data.iloc[2]
    multi_index = pd.MultiIndex.from_arrays([columns, sub_columns])

    df = data[3:].copy()
    df.columns = multi_index
    df.reset_index(drop=True, inplace=True)

    # Index column is the (NaN, "DATE") block in your files
    df.set_index((float("nan"), "DATE"), inplace=True)
    df.index.name = "DATE"
    df.index = pd.to_datetime(df.index)
    return df


# ---------- FUTURES (MarketWatch-like) ----------

def load_futures_excel(file_name: Union[str, Path], data_dir: Union[str, Path] = "data") -> pd.DataFrame:
    """Load Futures Excel and return OHLC DataFrame indexed by DATE."""
    path = _resolve(data_dir, file_name)
    raw = _read_excel_raw(path, header=None)
    return clean_futures_raw(raw)


def clean_futures_raw(data: pd.DataFrame) -> pd.DataFrame:
    """Normalize Futures layout to labeled OHLC with DATE index."""
    col = data.iloc[0]
    df = data[1:].copy()
    df.columns = col
    df.set_index("Date", inplace=True)
    df.index.name = "DATE"
    df.index = pd.to_datetime(df.index)
    df = df.loc[:, :]
    return df



# ======================================================= Load coffee data =================================================


def _find_row_with_value(df: pd.DataFrame, value: str) -> int:
    """Retourne l'indice de la première ligne contenant `value` (exact) ou lève."""
    hits = df.apply(lambda row: row.astype(str).str.strip().eq(value).any(), axis=1)
    idx = hits[hits].index
    if len(idx) == 0:
        raise ValueError(f"Row with value '{value}' not found")
    return int(idx[0])


def _make_multi_from_two_rows(raw: pd.DataFrame, markets_row: int, header_row: int) -> pd.DataFrame:
    """
    Construit des colonnes MultiIndex (marché, champ) à partir de 2 lignes d’entête :
      - markets_row : noms de marchés ("Brazil GC", "Vietnam", …)
      - header_row  : "DATE" / "FUTURES" / "VALUE"
    """
    # forward fill sur la rangée des marchés pour propager les noms
    top = raw.iloc[markets_row].ffill()
    bot = raw.iloc[header_row]

    multi_cols = pd.MultiIndex.from_arrays([top, bot])
    df = raw[(header_row + 1):].copy()
    df.columns = multi_cols

    # index = (NaN, "DATE")
    idx_col = (float("nan"), "DATE")
    if idx_col not in df.columns:
        # parfois "DATE" est sous un marchÉ ; cherche la colonne "DATE" dans level=1
        candidates = [c for c in df.columns if isinstance(c, tuple) and c[1] == "DATE"]
        if not candidates:
            raise ValueError("No 'DATE' column found in the expected header layout")
        idx_col = candidates[0]

    df.set_index(idx_col, inplace=True)
    df.index.name = "DATE"
    df.index = pd.to_datetime(df.index)

    # normalisation : VALUE -> MID pour coller à ton écosystème
    new_cols = []
    for fam, fld in df.columns:
        fld_norm = "MID" if str(fld).strip().upper() == "VALUE" else fld
        new_cols.append((fam, fld_norm))
    df.columns = pd.MultiIndex.from_tuples(new_cols)

    # nettoyage des doublons d’index éventuels
    if not df.index.is_unique:
        df = df.groupby(level=0).last()

    return df


def _clean_deepcore_multi_sheet(raw: pd.DataFrame) -> pd.DataFrame:
    """
    Nettoie UN onglet “multi-marchés” (Coffee Arabica / Coffee Robusta).
    On détecte la ligne "DATE" et la ligne des marchés juste au-dessus.
    """
    # localise la ligne "DATE"
    hdr_row = _find_row_with_value(raw, "DATE")
    markets_row = hdr_row - 1  # dans tes captures, la ligne du dessus porte les noms de familles
    return _make_multi_from_two_rows(raw, markets_row, hdr_row)


def load_deepcore_multi_workbook(
    file_name: Union[str, Path],
    *,
    data_dir: Union[str, Path] = "data",
    sheet_names: Optional[List[str]] = None,
) -> Dict[str, pd.DataFrame]:
    """
    Load a Deepcore workbook with several sheets and two-row headers.

    Returns a dict: {sheet_name: DataFrame} where columns are a MultiIndex
    (market, field) and VALUE is renamed to MID. Index = DATE (DatetimeIndex).
    """

    path = _resolve(data_dir, file_name)
    raw_sheets: Dict[str, pd.DataFrame] = pd.read_excel(path, sheet_name=sheet_names, header=None)
    if not isinstance(raw_sheets, dict):
        raw_sheets = {str(sheet_names[0] if sheet_names else "Sheet1"): raw_sheets}

    cleaned: Dict[str, pd.DataFrame] = {}
    for sheet, raw in raw_sheets.items():
        try:
            cleaned[sheet] = _clean_deepcore_multi_sheet(raw)
        except Exception as e:
            raise ValueError(f"Failed to clean sheet '{sheet}': {e}") from e
    return cleaned


def list_markets(df_multi: pd.DataFrame) -> List[str]:
    """
    Return the list of market names (level-0 of the MultiIndex columns)
    from a cleaned multi-market DataFrame.
    """
    if not isinstance(df_multi.columns, pd.MultiIndex):
        raise TypeError("Expected MultiIndex columns (family, field).")
    fams = [str(f) for f in df_multi.columns.get_level_values(0).unique() if pd.notna(f)]
    fams = [f for f in fams if f.lower() != "nan"]
    return fams


def extract_market_mid(df_multi: pd.DataFrame, market: str) -> pd.DataFrame:
    """
    Extract one market as a single-column DataFrame with 'MID'.

    Input is a multi-market DataFrame (columns: (market, field)).
    If only BID/OFFER exist, MID is computed as their mid.
    Index is DATE.
    """

    if not isinstance(df_multi.columns, pd.MultiIndex):
        raise TypeError("Expected MultiIndex columns (family, field).")
    if market not in df_multi.columns.get_level_values(0):
        raise KeyError(f"Market '{market}' not found. Available: {list_markets(df_multi)}")

    sub = df_multi[market].copy()

    u = {c.upper(): c for c in sub.columns}
    if "MID" in u:
        mid = pd.to_numeric(sub[u["MID"]], errors="coerce").astype("float64")
        out = pd.DataFrame({"MID": mid}).sort_index()
    elif "BID" in u and "OFFER" in u:
        bid = pd.to_numeric(sub[u["BID"]], errors="coerce")
        offer = pd.to_numeric(sub[u["OFFER"]], errors="coerce")
        out = pd.DataFrame({"MID": (0.5 * (bid.fillna(offer) + offer.fillna(bid))).astype("float64")})
    else:
        raise ValueError(f"Market '{market}' has neither MID nor BID/OFFER columns.")
    if not out.index.is_unique:
        out = out.groupby(level=0).last()
    return out


def concat_sheets_as_big_multi(sheets: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    Concatenate multiple cleaned sheets into one multi-market DataFrame.

    If a market name appears on several sheets, a " (SheetName)" suffix is added.
    Columns remain a MultiIndex (market, field). Index is DATE.
    """

    dfs = []
    for sheet, df in sheets.items():
        fams = df.columns.get_level_values(0)
        fams = [f if (isinstance(f, str) and f.strip()) else f for f in fams]
        fam_counts = pd.Series(fams).value_counts()
        if (fam_counts > 1).any():
            new_cols = []
            for fam, fld in df.columns:
                fam2 = f"{fam} ({sheet})" if fam_counts.loc[fam] > 1 else fam
                new_cols.append((fam2, fld))
            df2 = df.copy()
            df2.columns = pd.MultiIndex.from_tuples(new_cols)
            dfs.append(df2)
        else:
            dfs.append(df)
    big = pd.concat(dfs, axis=1).sort_index(axis=1)
    if not big.index.is_unique:
        big = big.groupby(level=0).last()
    return big
