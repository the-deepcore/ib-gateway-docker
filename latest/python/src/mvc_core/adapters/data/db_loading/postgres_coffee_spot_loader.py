from __future__ import annotations

from typing import Dict, Optional

import pandas as pd

from mvc_core.adapters.db_connection.postgres_connection import get_postgres

# Commodity IDs

COFFEE_COMMODITY_IDS = {
    "ARABICA": "0d39d62c-96d8-471e-acd9-956ed0a39842",
    "ROBUSTA": "0ccd8b25-0e9a-4d0a-91fb-c573cffd9f21",
}


# Origin Mapping (shipment_period_id per origin)

ARABICA_ORIGIN_IDS = {
    "Colombia Excelso": "8759e8a1-91ff-4d8d-9f42-33a11c97a05b",
    "Honduras HG": "f5bc54c0-83ca-4ed8-b29c-574721c16b1a",
    "Brazil GC": "d332daac-f002-493b-b27c-19a0ba02ea4e",
    "Brazil FC": "21fe57f3-1ad3-4f98-b5f9-b50e4e4a538e",
    "Brazil SW": "f3d3bf21-7883-4788-95ad-d4ee3c788de1",
    "Brazil Grinders": "49feb30c-7c6a-482d-93a8-5726d35b014a",
    "Peru G2": "8f2c747b-d526-45d4-8b7c-731e41e0f3f8",
    "Guatemala SHB": "798df53b-7af7-46c0-a181-858ca10f0b73",
    "Mexico PW": "1be42117-e363-42bb-a436-06f487577d97",
}

ROBUSTA_ORIGIN_IDS: Dict[str, str] = {
    "Vietnam": "6aef3c8c-b1c9-4c6e-81be-41f52b029b48",
    "Indonesia": "5b6b99f6-2b6e-4ad0-a200-6c528ca4d03e",
    "Conillon": "ec46e8b3-8847-486e-aa61-8904cc564596",
    "Uganda": "c9fbb12a-90e4-43e0-897c-7e2b2fc99641",
}




def build_sql_query_single_origin(
    commodity: str,
    origin: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: Optional[int] = None,
) -> str:
    """
    Build SQL query to fetch a single coffee origin's MID prices.
    
    Args:
        commodity: "ARABICA" or "ROBUSTA"
        origin: Origin name (e.g., "Brazil GC", "Colombia Excelso")
        start_date: Optional start date filter (format: "YYYY-MM-DD")
        end_date: Optional end date filter (format: "YYYY-MM-DD")
        limit: Optional limit on number of rows returned
    
    Returns:
        SQL query string that returns (date, mid)
    
    Raises:
        KeyError: If commodity or origin is not in the mapping
    """
    commodity = commodity.upper()
    
    if commodity not in COFFEE_COMMODITY_IDS:
        raise KeyError(f"Unknown commodity '{commodity}'. Available: {list(COFFEE_COMMODITY_IDS.keys())}")
    
    origin_map = ARABICA_ORIGIN_IDS if commodity == "ARABICA" else ROBUSTA_ORIGIN_IDS
    
    if origin not in origin_map:
        raise KeyError(f"Unknown origin '{origin}' for {commodity}. Available: {list(origin_map.keys())}")
    
    commodity_id = COFFEE_COMMODITY_IDS[commodity]
    period_id = origin_map[origin]
    
    query = f"""
        SELECT
            q.date,
            CASE
                WHEN q.bid IS NOT NULL AND q.offer IS NOT NULL THEN (q.bid + q.offer) / 2.0
                ELSE COALESCE(q.bid, q.offer)
            END AS mid
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


def load_coffee_origin_raw(
    commodity: str,
    origin: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: Optional[int] = None,
) -> pd.DataFrame:
    """
    Load raw coffee spot data for a SINGLE origin.
    
    Returns a DataFrame with columns: date, mid
    
    Args:
        commodity: "ARABICA" or "ROBUSTA"
        origin: Origin name (e.g., "Brazil GC")
        start_date: Optional start date filter
        end_date: Optional end date filter
        limit: Optional limit on number of rows
    
    Returns:
        Raw DataFrame with date, mid columns
    """
    db = get_postgres()
    
    query = build_sql_query_single_origin(
        commodity=commodity,
        origin=origin,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )
    
    return db.select_from_query(query)




def format_coffee_origin(df: pd.DataFrame) -> pd.DataFrame:
    """
    Format a single origin's DataFrame to standard format.
    
    - Sets DATE as index
    - Returns MID column
    
    Args:
        df: Raw DataFrame with date, mid columns
    
    Returns:
        Formatted DataFrame with:
        - DatetimeIndex named "DATE"
        - Column: MID
    """
    if df.empty:
        empty_df = pd.DataFrame(columns=["MID"])
        empty_df.index = pd.DatetimeIndex([], name="DATE")
        return empty_df
   
    df = df.copy()
    df.columns = [c.upper() for c in df.columns]
    
    df["DATE"] = pd.to_datetime(df["DATE"])
    df.set_index("DATE", inplace=True)
    df.index.name = "DATE"
    
    df["MID"] = pd.to_numeric(df["MID"], errors="coerce")
    df.sort_index(inplace=True)
    
    return df[["MID"]]





# Wrap load + format in a single function for convenience
def load_coffee_origin(
    commodity: str,
    origin: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> pd.DataFrame:
    """
    Load and format a single coffee origin's MID prices.
    
    Args:
        commodity: "ARABICA" or "ROBUSTA"
        origin: Origin name (e.g., "Brazil GC")
        start_date: Optional start date filter
        end_date: Optional end date filter
    
    Returns:
        DataFrame with DatetimeIndex and MID column
    """
    df_raw = load_coffee_origin_raw(
        commodity=commodity,
        origin=origin,
        start_date=start_date,
        end_date=end_date,
    )
    return format_coffee_origin(df_raw)
