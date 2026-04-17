from __future__ import annotations

from typing import Dict

import pandas as pd

from mvc_app.helpers.data_loader.data_loader_data import (
    CoffeeFuturesCfg,
    CoffeeSpotCfg,
    FuturesPostgresCfg,
    MultiSpotPostgresCfg,
    PriceLoaderCfg,
    SpotPostgresCfg,
    SpreadCfg,
    SugarFuturesCfg,
    SugarSpotCfg,
)
from mvc_core.adapters.data.db_loading.postgres_coffee_spot_loader import (
    load_coffee_origin,
)
from mvc_core.adapters.data.db_loading.postgres_sugar_spot_loader import (
    format_sugar_spot,
    load_sugar_spot_raw,
)
from mvc_core.adapters.data.excel_loading.deepcore_loader_services import (
    extract_market_mid,
    load_deepcore_multi_workbook,
    load_futures_excel,
    load_spot_excel,
)
from mvc_core.adapters.data.formatters_services import spot_mid, spot_spread_mid
from mvc_core.adapters.data.price_source_services import (
    select_futures_price,
    select_spot_price,
)
from mvc_core.domain.clock.clock_data import Clock


def _load_sugar_spot(cfg: SugarSpotCfg, clock_full: Clock) -> Dict[str, pd.Series]:
    spot_df = load_spot_excel(cfg.file_name, data_dir=cfg.data_dir)
    spot_mid_df = spot_mid(spot_df)

    s = select_spot_price(
        spot_mid_df,
        cfg.price_source,
        clock_full,
        fill_method=cfg.fill_method,
        as_date_index=cfg.as_date_index,
    )
    return {cfg.key: s}


def _load_sugar_futures(cfg: SugarFuturesCfg, clock_full: Clock) -> Dict[str, pd.Series]:
    fut_ohlc = load_futures_excel(cfg.file_name, data_dir=cfg.data_dir)

    s = select_futures_price(
        fut_ohlc,
        cfg.price_source,
        clock_full,
        fill_method=cfg.fill_method,
        as_date_index=cfg.as_date_index,
    )
    return {cfg.key: s}


def _load_coffee_spot(cfg: CoffeeSpotCfg, clock_full: Clock) -> Dict[str, pd.Series]:
    sheets = load_deepcore_multi_workbook(cfg.file_name, data_dir=cfg.data_dir)
    sheet = sheets[cfg.sheet_name]

    out: Dict[str, pd.Series] = {}

    for market in cfg.markets:
        mid_df = extract_market_mid(sheet, market)
        s = select_spot_price(
            mid_df,
            cfg.price_source,
            clock_full,
            fill_method=cfg.fill_method,
            as_date_index=cfg.as_date_index,
        )

        if cfg.key_mapping is not None and market in cfg.key_mapping:
            key = cfg.key_mapping[market]
        else:
            key = market

        out[key] = s

    return out


def _load_coffee_futures(cfg: CoffeeFuturesCfg, clock_full: Clock) -> Dict[str, pd.Series]:
    fut_ohlc = load_futures_excel(cfg.file_name, data_dir=cfg.data_dir)

    s = select_futures_price(
        fut_ohlc,
        cfg.price_source,
        clock_full,
        fill_method=cfg.fill_method,
        as_date_index=cfg.as_date_index,
    )
    return {cfg.key: s}


# ---- PostgreSQL loaders ----


def _load_sugar_spot_postgres(cfg: SpotPostgresCfg, clock_full: Clock) -> Dict[str, pd.Series]:
    """
    Load SPOT data from PostgreSQL database (sugar: VHP, THP).
    
    Uses postgres_sugar_spot_loader to fetch data, then applies
    the same processing pipeline as Excel loaders.
    """
    # Load raw data from PostgreSQL
    df_raw = load_sugar_spot_raw(asset_name=cfg.asset_name)
    
    # Format to get MID column (same structure as spot_mid output)
    spot_df = format_sugar_spot(df_raw, keep_bid_offer=False)
    
    # Apply same processing as Excel loaders
    s = select_spot_price(
        spot_df,
        cfg.price_source,
        clock_full,
        fill_method=cfg.fill_method,
        as_date_index=cfg.as_date_index,
    )
    return {cfg.key: s}


def _load_multi_spot_postgres(cfg: MultiSpotPostgresCfg, clock_full: Clock) -> Dict[str, pd.Series]:
    """
    Load multiple coffee origins from PostgreSQL database.
    
    Equivalent to _load_coffee_spot but for PostgreSQL.
    """
    out: Dict[str, pd.Series] = {}
    
    for origin in cfg.markets:
        spot_df = load_coffee_origin(
            commodity=cfg.commodity,
            origin=origin,
        )
        
        s = select_spot_price(
            spot_df,
            cfg.price_source,
            clock_full,
            fill_method=cfg.fill_method,
            as_date_index=cfg.as_date_index,
        )
        
        if cfg.key_mapping is not None and origin in cfg.key_mapping:
            key = cfg.key_mapping[origin]
        else:
            key = origin
        
        out[key] = s
    
    return out


from mvc_core.adapters.data.db_loading.postgres_futures_loader import (
    load_futures,
)


def _load_futures_postgres(cfg: FuturesPostgresCfg, clock_full: Clock) -> Dict[str, pd.Series]:
    """
    HIgh level function to load futures data from PostgreSQL.
    """
    fut_ohlc = load_futures(asset_name=cfg.asset_name)
    
    s = select_futures_price(
        fut_ohlc,
        cfg.price_source,
        clock_full,
        fill_method=cfg.fill_method,
        as_date_index=cfg.as_date_index,
    )
    return {cfg.key: s}



# def _load_multi_spot_postgres(cfg: MultiSpotPostgresCfg, clock_full: Clock) -> Dict[str, pd.Series]:
#     """
#     Load multiple SPOT markets from PostgreSQL database.
    
#     Equivalent to _load_coffee_spot but for PostgreSQL.
#     Loads each market separately and applies the same processing.
#     """
#     out: Dict[str, pd.Series] = {}
    
#     for market in cfg.markets:
#         # Load this market's data from PostgreSQL
#         spot_df = load_spot_postgres(
#             asset_name=market,
#             table_name=cfg.table_name,
#         )
        
#         # Apply same processing as Excel loaders
#         s = select_spot_price(
#             spot_df,
#             cfg.price_source,
#             clock_full,
#             fill_method=cfg.fill_method,
#             as_date_index=cfg.as_date_index,
#         )
        
#         # Apply key mapping if provided
#         if cfg.key_mapping is not None and market in cfg.key_mapping:
#             key = cfg.key_mapping[market]
#         else:
#             key = market
        
#         out[key] = s
    
#     return out


def _compute_spread(cfg: SpreadCfg, price_series: Dict[str, pd.Series], clock_full: Clock) -> Dict[str, pd.Series]:

    if cfg.key_a not in price_series:
        raise KeyError(f"key_a '{cfg.key_a}' not found in price_series for spread '{cfg.key}'")
    if cfg.key_b not in price_series:
        raise KeyError(f"key_b '{cfg.key_b}' not found in price_series for spread '{cfg.key}'")
    
    series_a = price_series[cfg.key_a]
    series_b = price_series[cfg.key_b]

    spread = spot_spread_mid(series_a, series_b, cfg.key)
    spread_s = select_spot_price(
        spot_df = spread,
        price_source = cfg.price_source,
        clock = clock_full,
        fill_method = cfg.fill_method,
        as_date_index=False,
    )

    return {cfg.key: spread_s}


def load_price_loader(cfg: PriceLoaderCfg, clock_full: Clock) -> Dict[str, pd.Series]:
    """
    Generic dispatch to load data from any supported config type.
    
    Supports both Excel configs (Sugar/Coffee) and PostgreSQL configs.
    """
    # Excel loaders
    if isinstance(cfg, SugarSpotCfg):
        return _load_sugar_spot(cfg, clock_full)
    if isinstance(cfg, SugarFuturesCfg):
        return _load_sugar_futures(cfg, clock_full)
    if isinstance(cfg, CoffeeSpotCfg):
        return _load_coffee_spot(cfg, clock_full)
    if isinstance(cfg, CoffeeFuturesCfg):
        return _load_coffee_futures(cfg, clock_full)
    
    # PostgreSQL loaders
    if isinstance(cfg, SpotPostgresCfg):
        return _load_sugar_spot_postgres(cfg, clock_full)
    if isinstance(cfg, MultiSpotPostgresCfg):
        return _load_multi_spot_postgres(cfg, clock_full)
    if isinstance(cfg, FuturesPostgresCfg):
        return _load_futures_postgres(cfg, clock_full)

    raise TypeError(f"Unsupported PriceLoaderCfg type: {type(cfg)}")


