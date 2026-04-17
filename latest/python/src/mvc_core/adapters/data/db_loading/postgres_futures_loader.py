from __future__ import annotations

from typing import Optional

import pandas as pd

from mvc_core.adapters.db_connection.postgres_connection import get_postgres

# ============================================================================
# Asset Name Mapping
# ============================================================================
#Mapping for references between tickers and asset name in db  
FUTURES_ASSET_NAMES = {
    "SB11": "sb11",
    "ARBC": "arabica",
    "ARABICA": "arabica",
    "RBST": "robusta",
    "ROBUSTA": "robusta",
}


# ============================================================================
# Query builder
# ============================================================================

def build_sql_query(
    asset_name: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: Optional[int] = None,
) -> str:
    """
    Build SQL query to fetch futures OHLC data.
    
    Args:
        asset_name: Asset name ("SB11", "ARBC", "RBST", "ARABICA", "ROBUSTA")
        start_date: Optional start date filter (format: "YYYY-MM-DD")
        end_date: Optional end date filter (format: "YYYY-MM-DD")
        limit: Optional limit on number of rows returned
    
    Returns:
        SQL query string
    
    Raises:
        KeyError: If asset_name is not in the mapping
    """
    asset_upper = asset_name.upper()
    
    if asset_upper not in FUTURES_ASSET_NAMES:
        available = list(FUTURES_ASSET_NAMES.keys())
        raise KeyError(f"Unknown asset '{asset_name}'. Available: {available}")
    
    futures_alias = FUTURES_ASSET_NAMES[asset_upper]
    
    query = f"""
        SELECT date, open, high, low, close, volume
        FROM public.data_market_intelligence_futures
        WHERE name = '{futures_alias}'
    """
    # public.data_market_intelligence_futures
    
    if start_date:
        query += f" AND date >= '{start_date}'"
    if end_date:
        query += f" AND date <= '{end_date}'"
    
    query += " ORDER BY date ASC"
    
    if limit:
        query += f" LIMIT {limit}"
    
    return query




def load_futures_raw(
    asset_name: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: Optional[int] = None,
) -> pd.DataFrame:
    """
    Load raw futures OHLC data from PostgreSQL.
    
    Returns a DataFrame with columns: date, open, high, low, close, volume
    (raw format, not yet formatted)
    
    Args:
        asset_name: Asset name ("SB11", "ARBC", "RBST")
        start_date: Optional start date filter
        end_date: Optional end date filter
        limit: Optional limit on number of rows
    
    Returns:
        Raw DataFrame with date, open, high, low, close, volume columns
    """
    db = get_postgres()
    
    query = build_sql_query(
        asset_name=asset_name,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )
    
    return db.select_from_query(query)





def format_futures(df: pd.DataFrame) -> pd.DataFrame:
    """
    Format raw futures DataFrame.
    
    - Sets DATE as index
    - Renames columns 
    
    Args:
        df: Raw DataFrame with date, open, high, low, close, volume columns
    
    Returns:
        Formatted DataFrame with:
        - DatetimeIndex named "DATE"
        - Columns: Open, High, Low, Close (Volume optional)
    """
    if df.empty:
        empty_df = pd.DataFrame(columns=["MID"])
        empty_df.index = pd.DatetimeIndex([], name="DATE")
        return empty_df
    
    df = df.copy()
    
    # legacy format columns
    rename_map = {
        "date": "DATE",
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "volume": "Volume",
    }
    df = df.rename(columns=rename_map)
    
    df["DATE"] = pd.to_datetime(df["DATE"])
    df.set_index("DATE", inplace=True)
    df.index.name = "DATE"
    
    for col in ["Open", "High", "Low", "Close"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    
    if "Volume" in df.columns:
        df["Volume"] = pd.to_numeric(df["Volume"], errors="coerce")
    
    df.sort_index(inplace=True)

    # need to divide by 100 to get correct price scale (ex 13.25 is stored as 1325 // 13.1 as 1310 // 13 as 1300)
    return df/100 




def load_futures(
    asset_name: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> pd.DataFrame:
    """
    Wrap function to load and format futures data from PostgreSQL based on asset name.
    """
    df_raw = load_futures_raw(
        asset_name=asset_name,
        start_date=start_date,
        end_date=end_date,
    )
    return format_futures(df_raw)
