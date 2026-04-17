from typing import Any, Callable, Dict, List, Optional, Tuple

import pandas as pd

from mvc_app.helpers.data_builder.builder import build_usecase_data
from mvc_app.helpers.data_loader.data_loader_data import (
    CoffeeFuturesCfg,
    CoffeeSpotCfg,
    DataCfg,
    DataSource,
    FuturesPostgresCfg,
    IndexConfig,
    MultiSpotPostgresCfg,
)
from mvc_core.adapters.data.price_source_data import PriceSource
from mvc_core.domain.clock.clock_data import Clock


def data_arabica_builder(start_load:str, end_load:str,
                      start_slice:Optional[str]=None, end_slice:Optional[str]=None, 
                      fill_method_spot: Optional[str] = "ffill",
                      fill_method_fut: Optional[str] = "dropna",
                      market_list: Optional[List[str]] = None,
                      idx_cfg: Optional[Dict[str, Any]] = None,
                      source: DataSource = DataSource.POSTGRES,
                      ) -> Callable[[],Tuple[Clock, Dict[str, pd.Series]]]:
    """
    Build data loader for Arabica coffee strategy.
    
    Args:
        start_load: Start date for loading data
        end_load: End date for loading data
        start_slice: Optional start date for slicing
        end_slice: Optional end date for slicing
        fill_method_spot: Fill method for spot prices
        fill_method_fut: Fill method for futures prices
        market_list: List of markets to load
        idx_cfg: Optional index configuration
        source: Data source - DataSource.EXCEL or DataSource.POSTGRES
    
    Returns:
        A builder function that returns (Clock, price_series dict)
    """
    
    market_mapping = {"Brazil FC": "BRZ_FC",
                      "Brazil GC": "BRZ_GC",
                      "Brazil Grinders": "BRZ_GR", 
                      "Brazil SW": "BRZ_SW",
                      "Colombia Excelso": "CLB", 
                      "Guatemala SHB": "GUA", 
                      "Honduras HG": "HON",
                      "Mexico PW": "MEX", 
                      "Peru G2": "PER"}

    key_mapping = {}
    
    for market in market_list:
        if market in market_mapping:
            key_mapping[market] = market_mapping[market]



    def builder() -> Tuple[Clock, Dict[str, pd.Series]]:
        
        if source == DataSource.EXCEL:

            coffee_spot_cfg = CoffeeSpotCfg(
                file_name="data_spot_coffee.xlsx",
                sheet_name="Coffee Arabica",
                markets= market_list,
                key_mapping=key_mapping,
                data_dir="data",
                fill_method=fill_method_spot,
                as_date_index=False,
            )

            coffee_fut_cfg = CoffeeFuturesCfg(
                file_name="data_futures_arabica.xlsx",
                key="ARBC",
                data_dir="data",
                fill_method=fill_method_fut,
                as_date_index=False,
            )
            
            loaders_list = [coffee_spot_cfg, coffee_fut_cfg]
        
        elif source == DataSource.POSTGRES:
            
            coffee_spot_cfg = MultiSpotPostgresCfg(
                commodity="ARABICA",
                markets=market_list,
                key_mapping=key_mapping,
                price_source=PriceSource(kind="mid"),
                fill_method=fill_method_spot,
                as_date_index=False,
            )

            # excel import legacy
            # coffee_fut_cfg = CoffeeFuturesCfg(
            #     file_name="data_futures_arabica.xlsx",
            #     key="ARBC",
            #     data_dir="data",
            #     fill_method=fill_method_fut,
            #     as_date_index=False,
            # )
            
            coffee_fut_cfg = FuturesPostgresCfg(
                asset_name="ARBC",
                key="ARBC",
                price_source=PriceSource(kind="close"),
                fill_method=fill_method_fut,
                as_date_index=False,
            )
            loaders_list = [coffee_spot_cfg, coffee_fut_cfg]
        
        else:
            raise ValueError(f"Unsupported data source: {source}")

        if idx_cfg: 
            idx = IndexConfig(
                name = idx_cfg['name'],
                index_compo = idx_cfg['index_compo'],
                weights = idx_cfg['weights']
            )


        data_cfg = DataCfg(
            loaders=loaders_list,
            full_start=start_load,
            full_end=end_load,
            freq="1D",
            sample_start=start_slice,
            sample_end=end_slice,
            align_method="dropna",
            index = idx if idx_cfg else None  
        )

        return build_usecase_data(data_cfg)

    return builder


