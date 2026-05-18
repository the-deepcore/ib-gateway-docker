from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict

import pandas as pd

from mvc_app.helpers.data_builder.data_arabica import data_arabica_builder
from mvc_app.helpers.data_loader.data_loader_data import (
    DataSource,
)
from mvc_app.usecases.profile_base.profile_data import UseCaseProfile
from mvc_app.usecases.profile_base.profile_services import register_profile
from mvc_core.domain.clock.clock_data import Clock
from mvc_core.domain.enums import CrossSense, TriggerMode
from mvc_core.optimize.calibration.calibration_data import CalibrationConfig
from mvc_core.optimize.components.objective.objective_data import ObjectiveConfig
from mvc_core.optimize.components.param_bindings.param_bindings_services import (
    bind_params,
)
from mvc_core.optimize.components.search_space.search_space_data import (
    Choice,
    SearchSpace,
)
from mvc_core.optimize.components.splitter.splitter_data import SplitConfig
from mvc_core.strategies.components.features.feature_data import InputSpec
from mvc_core.strategies.components.filters.filter_services import (
    block_cumulative_entries,
)
from mvc_core.strategies.components.normalizers.threshold_1d_data import (
    Threshold1DConfig,
)
from mvc_core.strategies.components.normalizers.threshold_1d_services import (
    normalize_1d_to_fls,
)
from mvc_core.strategies.components.risk.risk_data import RiskConfig
from mvc_core.strategies.components.sizers.sizer_data import SizerConfig
from mvc_core.strategies.components.sources.source_1d_data import Source1DConfig
from mvc_core.strategies.components.sources.source_1d_services import compute_scores_1d
from mvc_core.strategies.core.strategy_data import StrategyCfg, StrategyComponents

CAPITAL_INITIAL = 200_000_000.0
POSITION_NOTIONAL_USD = 20_000_000.0



# start_load, end_load = "1998-01-01", "2027-01-01"
# start_slice, end_slice = "1998-05-07", datetime.today().strftime('%Y-%m-%d')
start_load, end_load = "1998-01-01", "2027-01-01"
start_slice, end_slice = "2013-05-01", datetime.today().strftime('%Y-%m-%d'),


fill_method_spot = "ffill"
fill_method_fut = "dropna"
market_list = ["Brazil GC", "Colombia Excelso"]

data_builder = data_arabica_builder(start_load, end_load, start_slice, end_slice,
                                    fill_method_spot, fill_method_fut, market_list,
                                    source=DataSource.POSTGRES)




def build_strategy_arbc(clock: Clock, price_series: Dict[str, pd.Series]) -> StrategyCfg:
    spec = InputSpec(
        base_keys={"spot_mid": "BRZ_GC", "fut_close": "ARBC"},
        recipes={
            "zscore": {
                "base": "spot_mid",
                "ops": [
                    {"op": "zscore_smooth_ewm", "window": 15, "smooth_span": 1},
                ],
            },

            "zscore_fut_shifted": {
                "base": "fut_close",
                "ops": [
                    {"op": "shift", "periods": 1},
                    {"op": "zscore_smooth_ewm", "window": 15, "smooth_span": 1},
                ],
            },


            "zscore_combined": {
                "base": "spot_mid",
                "ops": [
                    {
                    "op": "zscore_combined_spot_fut",
                    "fut_key": "fut_close",
                    "shift_fut": 1,
                    "window_spot": 20,
                    "window_fut": 20
                    }
                  ]
              },



            "vol_sizer": {
                "base": "fut_close",
                "ops": [
                    {"op": "shift", "periods": 1},
                    {"op": "logret", "periods": 1},
                    {"op": "rolling_vol", "window": 504},
                    {"op": "mult", "coeff": 252 ** 0.5},
                ],
            },
            "ratio_vol": {
                "base": "fut_close",
                "ops": [
                    {"op": "shift", "periods": 1},
                    {"op": "ratio_stds", "short_window": 42, "long_window": 252},
                ],
            },
            "ratio_vol_rm": {
                "base": "fut_close",
                "ops": [
                    {"op": "shift", "periods": 1},
                    {"op": "ratio_stds", "short_window": 21, "long_window": 504},
                ],
            },
        },
    )

    src_cfg = Source1DConfig(mode="by_feature_key", feature_key="zscore_fut_shifted")

    th_cfg = Threshold1DConfig(
        low=-0.5,
        high=0.5,
        mode=TriggerMode.CROSS,
        cross_sense=CrossSense.OUTSIDE_TO_INSIDE,
        start_hold=True,
    )

    sz_cfg = SizerConfig(
        enabled=True,
        default_compose="set",
        meta={"notional_usd": POSITION_NOTIONAL_USD, "fixed_notional": True},
        steps=[
            {
                "service": "constant",
                "cfg": {"value": 1.0},
                "compose": "set",
            },

        ],
    )


    risk_cfg = RiskConfig(
        enabled=False,
        rules=[
            {
                "type": "sl_vol_multiple",
                "scope": "per_side",
                "priority": 5,
                "params": {
                    "key": "vol_sizer",
                    "price_key": "fut_close",
                    "k": 2.5,
                    "unit": "return",
                    "annualized": True,
                    "reduce_ratio": 0.3,
                },
            },
            {
                "type": "tp_vol_multiple",
                "scope": "per_side",
                "priority": 5,
                "params": {
                    "key": "vol_sizer",
                    "price_key": "fut_close",
                    "k": 12.0,
                    "unit": "return",
                    "annualized": True,
                    "reduce_ratio": 0.3,
                },
            },
        ],
    )

    instrument = "ARBC"

    strat_extras = {
        "filters": [
            {"fn": block_cumulative_entries, "cfg": {"enabled": True}},
        ],
    }

    components = StrategyComponents(
        source_fn=compute_scores_1d,
        normalizer_fn=normalize_1d_to_fls,
        signalizer_fn=None,
        sizer_fn=None,
        risk_fn=None,
    )

    return StrategyCfg(
        instrument=instrument,
        input_spec=spec,
        source_cfg=src_cfg,
        normalizer_cfg=th_cfg,
        sizer_cfg=sz_cfg,
        risk_cfg=risk_cfg,
        components=components,
        extras=strat_extras,
    )




# def build_calib_arbc() -> CalibrationConfig:
#     nb_trials = 100

#     space = SearchSpace(
#         engine="random",
#         spec={
#             "normalizer.low": Choice([-i / 10.0 for i in range(4, 40)]),
#             "normalizer.high": Choice([i / 10.0 for i in range(4, 40)]),
#             "input_spec.recipes[key=zscore_fut_shifted].ops[op=zscore_smooth_ewm].window": Choice(
#                 [i for i in range(10, 50)]
#             ),
#             "input_spec.recipes[key=zscore_fut_shifted].ops[op=zscore_smooth_ewm].smooth_span": Choice(
#                 [i for i in range(1, 5)]
#             ),
#         },
#         n_trials=nb_trials,
#     )
def build_calib_arbc() -> CalibrationConfig:


    nb_trials = 30

    space = SearchSpace(
        engine="optuna",
        spec={

            "normalizer.low": Choice([-i / 10.0 for i in range(5, 30, 5)]),
            "normalizer.high": Choice([i / 10.0 for i in range(5, 30, 5)]),

        },
        n_trials=nb_trials,
        # seed=42,
    )

    obj = ObjectiveConfig(
        direction="maximize",
        weights={"sharpe": 1.5, "total_return_pct": 0.75, "mdd": 25},
        top_k=nb_trials,
    )

    calib_cfg = CalibrationConfig(
        search_space=space,
        objective=obj,
        bind_fn=bind_params,
        keep_artifacts=False,
        top_k=nb_trials,
        bench_key="ARBC",
        initial_inv=CAPITAL_INITIAL,
        tick_size=0.0,
        walk_mode="carry",
        n_jobs=11,
    )

    split_cfg = SplitConfig(
        mode="walk_bars",
        train_bars=168,
        test_bars=42,
        stride_bars=42,
        gap_bars=0,
        include_tail=True,
    )

    return calib_cfg, split_cfg




# ============================================================
# Enregistrement du profil dans le registry
# ============================================================

PROFILE_NAME = "arabica_zscore_fut_shifted_wf"

PROFILE = UseCaseProfile(
    name=PROFILE_NAME,
    data_builder=data_builder,
    strategy_cfg_builder=build_strategy_arbc, 
    calib_builder=build_calib_arbc,           
    bench_key="ARBC",
    # wf_json_path=Path("save_wf_simu/wf_arbc_fut_shifted_calibration.json"),
    wf_json_path=Path("save_wf_simu/calib_temp/arbc_zscore_fut_calibration.json"),

)

register_profile(PROFILE)
