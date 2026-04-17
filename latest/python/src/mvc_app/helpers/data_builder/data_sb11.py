from typing import Callable, Dict, Optional, Tuple

import pandas as pd

from mvc_app.helpers.data_builder.builder import build_usecase_data
from mvc_app.helpers.data_loader.data_loader_data import (
    DataCfg,
    DataSource,
    FuturesPostgresCfg,
    SpotPostgresCfg,
    SpreadCfg,
    SugarFuturesCfg,
    SugarSpotCfg,
)
from mvc_core.adapters.data.price_source_data import PriceSource
from mvc_core.domain.clock.clock_data import Clock


def data_sb11_builder(start_load:str, end_load:str,
                      start_slice:Optional[str]=None, end_slice:Optional[str]=None, 
                      fill_method_spot: Optional[str] = "ffill",
                      fill_method_fut: Optional[str] = "dropna",
                      source: DataSource = DataSource.POSTGRES,
                      )-> Callable[[],Tuple[Clock, Dict[str, pd.Series]]]:
    """
    Build data loader for SB11 sugar futures strategy.
    
    Args:
        start_load: Start date for loading data
        end_load: End date for loading data
        start_slice: Optional start date for slicing
        end_slice: Optional end date for slicing
        fill_method_spot: Fill method for spot prices
        fill_method_fut: Fill method for futures prices
        source: Data source - DataSource.EXCEL or DataSource.POSTGRES
    
    Returns:
        A builder function that returns (Clock, price_series dict)
    """

    def builder() -> Tuple[Clock, Dict[str, pd.Series]]:

        if source == DataSource.EXCEL:
            # ---- Excel configs (original behavior) ----
            vhp_spot = SugarSpotCfg(
                file_name = "data_spot_VHP.xlsx",
                key = "VHP",
                data_dir = "data",
                price_source = PriceSource(kind="mid"),
                fill_method = fill_method_spot,
                as_date_index = False,
            )

            thp_spot = SugarSpotCfg(
                file_name = "data_spot_THP.xlsx",
                key = "THP",
                data_dir = "data",
                price_source = PriceSource(kind="mid"),
                fill_method = fill_method_spot,
                as_date_index = False,
            )

            sb11_close_prices = SugarFuturesCfg(
                file_name = "data_futures_sb11.xlsx",
                key = "SB11",
                data_dir = "data",
                price_source = PriceSource(kind="close"),
                fill_method = fill_method_fut,
                as_date_index = False,
            )
            
            loaders_list = [vhp_spot, thp_spot, sb11_close_prices]
            clock_intersection_list = [vhp_spot, sb11_close_prices]

        elif source == DataSource.POSTGRES:

            vhp_spot = SpotPostgresCfg(
                asset_name = "VHP",
                key = "VHP",
                price_source = PriceSource(kind="mid"),
                fill_method = fill_method_spot,
                as_date_index = False,
            )

            thp_spot = SpotPostgresCfg(
                asset_name = "THP",
                key = "THP",
                price_source = PriceSource(kind="mid"),
                fill_method = fill_method_spot,
                as_date_index = False,
            )
            # excel import legacy
            # sb11_close_prices = SugarFuturesCfg(
            #     file_name = "data_futures_sb11.xlsx",
            #     key = "SB11",
            #     data_dir = "data",
            #     price_source = PriceSource(kind="close"),
            #     fill_method = fill_method_fut,
            #     as_date_index = False,
            # )
            sb11_close_prices = FuturesPostgresCfg(
                asset_name = "SB11",
                key = "SB11",
                price_source = PriceSource(kind="close"),
                fill_method = fill_method_fut,
                as_date_index = False,
            )
            
            loaders_list = [vhp_spot, thp_spot, sb11_close_prices]
            clock_intersection_list = [vhp_spot, sb11_close_prices]

        else:
            raise ValueError(f"Unsupported data source: {source}")

        # Spread is computed from loaded data, same for both sources
        spread_vhp_thp = SpreadCfg(
            key_a = "VHP",
            key_b = "THP",
            key = "SPREAD",
            price_source = PriceSource(kind="spread")
        )

        data_cfg = DataCfg(
            loaders=loaders_list + [spread_vhp_thp],
            clock_intersection = clock_intersection_list,
            full_start=start_load,
            full_end=end_load,
            freq="1D",
            sample_start=start_slice,
            sample_end=end_slice,
            align_method="dropna",  
        )

        clock, price_series = build_usecase_data(data_cfg)

        return clock, price_series
        
    return builder
