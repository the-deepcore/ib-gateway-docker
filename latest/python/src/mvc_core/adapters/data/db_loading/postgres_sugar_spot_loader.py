from __future__ import annotations

from typing import Optional

import pandas as pd

from mvc_core.adapters.db_connection.postgres_connection import get_postgres

# ============================================================================
# Asset ID Mapping
# ============================================================================
# Maps asset names to (data_commodity_id, shipment_period_id) in db

SUGAR_SPOT_ASSET_IDS = {
    "VHP": {
        "data_commodity_id": "96bb478f-7baf-4027-a9dc-2c646644f90f",
        "shipment_period_id": "d95ff7a9-644e-4b9a-b57c-fbd0ffeecae1",
    },
    "THP": {
        "data_commodity_id": "48b9390f-6333-42bd-bb91-8f6d585960d6",
        "shipment_period_id": "3baa818d-9972-4b9a-9eea-3f6e9e92f58d",
    },
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
    Build SQL query to fetch sugar spot data.
    
    Args:
        asset_name: Asset name ("VHP", "THP")
        start_date: Optional start date filter (format: "YYYY-MM-DD")
        end_date: Optional end date filter (format: "YYYY-MM-DD")
        limit: Optional limit on number of rows returned
    
    Returns:
        SQL query string
    
    Raises:
        KeyError: If asset_name is not in the mapping
    """
    if asset_name not in SUGAR_SPOT_ASSET_IDS:
        available = list(SUGAR_SPOT_ASSET_IDS.keys())
        raise KeyError(f"Unknown asset '{asset_name}'. Available: {available}")
    
    ids = SUGAR_SPOT_ASSET_IDS[asset_name]
    commodity_id = ids["data_commodity_id"]
    period_id = ids["shipment_period_id"]
    
    query = f"""
        SELECT q.date, q.bid, q.offer
        FROM public.quotations q
        WHERE q.data_commodity_id = '{commodity_id}'
        AND q.shipment_period_id = '{period_id}'
    """
    
    if start_date:
        query += f" AND q.date >= '{start_date}'"
    if end_date:
        query += f" AND q.date <= '{end_date}'"
    
    query += " ORDER BY q.date ASC"
    
    if limit:
        query += f" LIMIT {limit}"
    
    return query


# ============================================================================
# Data loader
# ============================================================================

def load_sugar_spot_raw(
    asset_name: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: Optional[int] = None,
) -> pd.DataFrame:
    """
    Load raw sugar spot data from PostgreSQL.
    
    Returns a DataFrame with columns: date, bid, offer
    (raw format, not yet formatted)
    
    Args:
        asset_name: Asset name ("VHP", "THP")
        start_date: Optional start date filter
        end_date: Optional end date filter
        limit: Optional limit on number of rows
    
    Returns:
        Raw DataFrame with date, bid, offer columns
    """
    db = get_postgres()
    
    query = build_sql_query(
        asset_name=asset_name,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )
    
    df = db.select_from_query(query)
    
    return df


# ============================================================================
# Data formatter
# ============================================================================

def format_sugar_spot(
    df: pd.DataFrame,
    keep_bid_offer: bool = False,
) -> pd.DataFrame:
    """
    Format raw sugar spot DataFrame to standard format.
    
    - Sets DATE as index
    - Adds MID column (average of BID and OFFER)
    - Optionally drops BID and OFFER columns
    
    Args:
        df: Raw DataFrame with date, bid, offer columns
        keep_bid_offer: If False, drop BID and OFFER columns
    
    Returns:
        Formatted DataFrame with:
        - DatetimeIndex named "DATE"
        - Columns: MID (and optionally BID, OFFER)
    """
    if df.empty:
        empty_df = pd.DataFrame(columns=["MID"])
        empty_df.index = pd.DatetimeIndex([], name="DATE")
        return empty_df
    
    df = df.copy()
    
    # Rename columns to uppercase
    df.columns = [c.upper() for c in df.columns]
    
    # Set DATE as index
    df["DATE"] = pd.to_datetime(df["DATE"])
    df.set_index("DATE", inplace=True)
    df.index.name = "DATE"
    
    # Ensure numeric types
    df["BID"] = pd.to_numeric(df["BID"], errors="coerce")
    df["OFFER"] = pd.to_numeric(df["OFFER"], errors="coerce")
    
    # Compute MID — cross-fill BID/OFFER so a single-sided quote still yields a value
    bid_f = df["BID"].fillna(df["OFFER"])
    offer_f = df["OFFER"].fillna(df["BID"])
    df["MID"] = 0.5 * (bid_f + offer_f)
    
    # Sort by date
    df.sort_index(inplace=True)
    
    # Optionally drop BID/OFFER
    if not keep_bid_offer:
        df = df.drop(columns=["BID", "OFFER"])
    
    return df

