from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Union

import pandas as pd

from mvc_core.adapters.data.price_source_data import PriceSource

# ============================================================================
# Data source enum
# ============================================================================

class DataSource(Enum):
    """
    Enum to specify the data source.
    
    - EXCEL: Load data from Excel files (current behavior)
    - POSTGRES: Load data from PostgreSQL database
    """
    EXCEL = "excel"
    POSTGRES = "postgres"


# ---- Configs spécifiques par type de dataset ----


@dataclass
class SugarSpotCfg:

    file_name: str
    key: str
    data_dir: str = "data"
    price_source: PriceSource = field(default_factory=lambda: PriceSource(kind="mid"))
    fill_method: str = "dropna"
    as_date_index: bool = False


@dataclass
class SugarFuturesCfg:

    file_name: str
    key: str
    data_dir: str = "data"
    price_source: PriceSource = field(default_factory=lambda: PriceSource(kind="close"))
    fill_method: str = "dropna"
    as_date_index: bool = False


@dataclass
class CoffeeSpotCfg:

    file_name: str
    sheet_name: str
    markets: List[str]
    key_mapping: Optional[dict[str, str]] = None
    data_dir: str = "data"
    price_source: PriceSource = field(default_factory=lambda: PriceSource(kind="mid"))
    fill_method: str = "ffill"
    as_date_index: bool = False


@dataclass
class CoffeeFuturesCfg:

    file_name: str
    key: str
    data_dir: str = "data"
    price_source: PriceSource = field(default_factory=lambda: PriceSource(kind="close"))
    fill_method: str = "dropna"
    as_date_index: bool = False


PriceLoaderCfg = Union[SugarSpotCfg, SugarFuturesCfg, CoffeeSpotCfg, CoffeeFuturesCfg]


# ============================================================================
# PostgreSQL configs (equivalent to Excel configs above)
# ============================================================================

@dataclass
class SpotPostgresCfg:
    """
    Config to load SPOT data from PostgreSQL.
    
    Attributes:
        asset_name: The asset identifier in the database (e.g., "VHP", "THP")
        key: The key to use in the output price_series dict
        table_name: Optional custom table name (uses default if not specified)
        price_source: Which price to select (mid, bid, offer)
        fill_method: How to handle missing values
        as_date_index: Whether to normalize index to dates
    """
    asset_name: str
    key: str
    table_name: Optional[str] = None
    price_source: PriceSource = field(default_factory=lambda: PriceSource(kind="mid"))
    fill_method: str = "dropna"
    as_date_index: bool = False


@dataclass
class FuturesPostgresCfg:
    """
    Config to load FUTURES data from PostgreSQL.
    
    Attributes:
        asset_name: The asset identifier in the database (e.g., "SB11", "KC")
        key: The key to use in the output price_series dict
        table_name: Optional custom table name (uses default if not specified)
        price_source: Which price to select (close, open, high, low)
        fill_method: How to handle missing values
        as_date_index: Whether to normalize index to dates
    """
    asset_name: str
    key: str
    table_name: Optional[str] = None
    price_source: PriceSource = field(default_factory=lambda: PriceSource(kind="close"))
    fill_method: str = "dropna"
    as_date_index: bool = False


@dataclass
class MultiSpotPostgresCfg:
    """
    Config to load multiple SPOT markets from PostgreSQL.
    
    Equivalent to CoffeeSpotCfg but for PostgreSQL.
    Used when you need to load several coffee origins (e.g., Brazil GC, Colombia, etc.)
    
    Attributes:
        commodity: The commodity type ("ARABICA" or "ROBUSTA")
        markets: List of origin names to load from the database
        key_mapping: Optional dict to rename market keys in output (e.g., {"Brazil GC": "BRZ_GC"})
        price_source: Which price to select (mid)
        fill_method: How to handle missing values
        as_date_index: Whether to normalize index to dates
    """
    commodity: str  # "ARABICA" or "ROBUSTA"
    markets: List[str]
    key_mapping: Optional[Dict[str, str]] = None
    price_source: PriceSource = field(default_factory=lambda: PriceSource(kind="mid"))
    fill_method: str = "ffill"
    as_date_index: bool = False


# Union type including both Excel and PostgreSQL configs
PriceLoaderCfgAll = Union[
    SugarSpotCfg, SugarFuturesCfg, CoffeeSpotCfg, CoffeeFuturesCfg,
    SpotPostgresCfg, FuturesPostgresCfg, MultiSpotPostgresCfg
]


@dataclass
class SpreadCfg:

    key_a: str
    key_b: str
    key: str

    fill_method: str = 'dropna'

    price_source: PriceSource = field(default_factory=lambda: PriceSource(kind="spread"))




@dataclass(frozen=True)
class IndexConfig:

    name: str
    index_compo: List[str] 
    weights: Dict[str, float]










# ---- Config globale pour la data d'un use case ----

@dataclass
class DataCfg:
    """
    Config complète pour construire (clock, price_series) d'un use case.

    - loaders      : liste de configs de loaders (spot/fut sucre/café, etc.)
    - full_start   : début du clock "full" (avant slicing use case)
    - full_end     : fin du clock "full"
    - freq         : fréquence du clock (ex: "1D")
    - sample_start : début de la fenêtre d'étude du use case (optionnel)
    - sample_end   : fin de la fenêtre d'étude du use case (optionnel)
    - align_method : méthode d'alignement sur le clock ("dropna", "ffill", ...)
    """

    loaders: List[PriceLoaderCfg]
    clock_intersection: Optional[List[PriceLoaderCfg]] = None

    full_start: Union[pd.Timestamp, str] = None
    full_end: Union[pd.Timestamp, str] = None
    freq: str = "1D"


    sample_start: Union[pd.Timestamp, str, None] = None
    sample_end: Union[pd.Timestamp, str, None] = None

    align_method: str = "dropna"
    index: Optional[IndexConfig] = None
