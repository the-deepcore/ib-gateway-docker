from typing import Dict, Tuple

import pandas as pd

from mvc_app.helpers.data_loader.data_loader_data import DataCfg, SpreadCfg
from mvc_app.helpers.data_loader.data_loader_services import _compute_spread, load_price_loader
from mvc_core.domain.clock.clock_data import Clock
from mvc_core.domain.clock.clock_services import (
    build_from_intersection,
    build_from_range,
    slice_clock,
)


def build_usecase_data(cfg: DataCfg) -> Tuple[Clock, Dict[str, pd.Series]]:
    """
    Construit le clock final (slicé) et les séries de prix alignées.
    Traite d'abord les loaders de données brutes, puis les spreads.
    """
    if not cfg.loaders:
        raise ValueError("DataCfg.loaders cannot be empty")

    full_start_ts = (
        cfg.full_start
        if isinstance(cfg.full_start, pd.Timestamp)
        else pd.Timestamp(cfg.full_start)
    )
    full_end_ts = (
        cfg.full_end
        if isinstance(cfg.full_end, pd.Timestamp)
        else pd.Timestamp(cfg.full_end)
    )

    clock_full = build_from_range(full_start_ts, full_end_ts, cfg.freq)

    # 1) Séparer les loaders en deux catégories
    data_loaders = []
    spread_loaders = []
    
    for loader_cfg in cfg.loaders:
        if isinstance(loader_cfg, SpreadCfg):
            spread_loaders.append(loader_cfg)
        else:
            data_loaders.append(loader_cfg)

    # 2) Premier passage : charger les données brutes
    price_series_all: Dict[str, pd.Series] = {}

    for loader_cfg in data_loaders:
        loaded = load_price_loader(loader_cfg, clock_full)
        for key, s in loaded.items():
            if key in price_series_all:
                raise ValueError(f"Duplicate price series key '{key}' from loaders")
            price_series_all[key] = s

    if not price_series_all and not spread_loaders:
        raise ValueError("No price series produced by loaders")

    # 3) Deuxième passage : calculer les spreads
    for spread_cfg in spread_loaders:
        spread_data = _compute_spread(spread_cfg, price_series_all, clock_full)
        for key, s in spread_data.items():
            if key in price_series_all:
                raise ValueError(f"Duplicate price series key '{key}' from spread")
            price_series_all[key] = s

    # 4) Clock adapté = intersection
    if cfg.clock_intersection:
        price_series_for_index_intersection = {
            ps.key: price_series_all[ps.key] for ps in cfg.clock_intersection
        }
        index_list = [s.index for s in price_series_for_index_intersection.values()]
        clock_adapted = build_from_intersection(index_list)
    else:
        # Si pas de clock_intersection spécifié, prendre toutes les séries
        index_list = [s.index for s in price_series_all.values()]
        clock_adapted = build_from_intersection(index_list)

    # 5) Slicing window
    if cfg.sample_start is not None or cfg.sample_end is not None:
        start_ts = (
            None
            if cfg.sample_start is None
            else (
                cfg.sample_start
                if isinstance(cfg.sample_start, pd.Timestamp)
                else pd.Timestamp(cfg.sample_start)
            )
        )
        end_ts = (
            None
            if cfg.sample_end is None
            else (
                cfg.sample_end
                if isinstance(cfg.sample_end, pd.Timestamp)
                else pd.Timestamp(cfg.sample_end)
            )
        )

        clock = slice_clock(clock_adapted, start_ts, end_ts)
    else:
        clock = clock_adapted


    return clock, price_series_all