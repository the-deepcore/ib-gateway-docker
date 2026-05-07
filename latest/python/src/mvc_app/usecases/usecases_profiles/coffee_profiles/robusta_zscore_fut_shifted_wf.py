from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, Tuple

from mvc_app.helpers.data_loader.data_loader_data import DataSource
import pandas as pd

from mvc_core.domain.clock.clock_data import Clock

from mvc_core.strategies.components.features.feature_data import InputSpec
from mvc_core.strategies.components.sources.source_1d_data import Source1DConfig
from mvc_core.strategies.components.sources.source_1d_services import compute_scores_1d
from mvc_core.strategies.components.normalizers.threshold_1d_data import (
    Threshold1DConfig,
)
from mvc_core.strategies.components.normalizers.threshold_1d_services import (
    normalize_1d_to_fls,
)
from mvc_core.strategies.components.sizers.sizer_data import SizerConfig
from mvc_core.strategies.components.risk.risk_data import RiskConfig
from mvc_core.strategies.components.filters.filter_services import (
    block_cumulative_entries,
)

from mvc_core.domain.enums import TriggerMode, CrossSense

from mvc_core.strategies.core.strategy_data import StrategyCfg, StrategyComponents

from mvc_core.optimize.components.search_space.search_space_data import (
    SearchSpace,
    Choice,
)
from mvc_core.optimize.components.objective.objective_data import ObjectiveConfig
from mvc_core.optimize.calibration.calibration_data import CalibrationConfig
from mvc_core.optimize.components.param_bindings.param_bindings_services import (
    bind_params_v2,
)
from mvc_core.optimize.components.splitter.splitter_data import SplitConfig

from mvc_app.usecases.profile_base.profile_data import UseCaseProfile
from mvc_app.usecases.profile_base.profile_services import register_profile

CAPITAL_INITIAL = 200_000_000.0
POSITION_NOTIONAL_USD = 30_000_000.0

# ============================================================
# Builders pour le use case WF SB11
# ============================================================

from mvc_core.adapters.data.price_source_data import PriceSource
from mvc_core.domain.clock.clock_services import (
    build_from_intersection,
    slice_clock,
)


from mvc_core.adapters.data.excel_loading.deepcore_loader_services import (
    load_deepcore_multi_workbook,
    extract_market_mid,
)


from mvc_app.helpers.data_builder.data_robusta import data_robusta_builder


# preset
start_load, end_load = "2008-01-14", "2027-01-01"
start_slice, end_slice = "2013-05-01", datetime.today().strftime('%Y-%m-%d'),
fill_method_spot = "ffill"
fill_method_fut = "dropna"
market_list = ["Vietnam"]



data_builder = data_robusta_builder(start_load, end_load, start_slice, end_slice,
                                    fill_method_spot, fill_method_fut, market_list,
                                    source=DataSource.POSTGRES)




def build_strategy_rbst(clock: Clock, price_series: Dict[str, pd.Series]) -> StrategyCfg:
    """
    Stratégie SB11 : même chose que dans test_new_refacto.py.
    """
    spec = InputSpec(
        base_keys={"spot_mid": "VTM", "fut_close": "RBST"},
        recipes={
            # "zscore": {
            #     "base": "spot_mid",
            #     "ops": [
            #         {"op": "zscore_smooth_ewm", "window": 18, "smooth_span": 9},
            #     ],
            # },
            "zscore": {
                "base": "fut_close",
                "ops": [
                    {"op": "shift", "periods": 1},
                    {"op": "zscore_smooth_ewm", "window": 15, "smooth_span": 1},
                ],
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

    src_cfg = Source1DConfig(mode="by_feature_key", feature_key="zscore")

    th_cfg = Threshold1DConfig(
        low=-0.5,
        high=0.5,
        mode=TriggerMode.CROSS,
        cross_sense=CrossSense.OUTSIDE_TO_INSIDE,
        start_hold=True,
    )

    # sz_cfg = SizerConfig(
    #     enabled=True,
    #     default_compose="set",
    #     steps=[
    #         {
    #             "service": "constant",
    #             "cfg": {"value": 1.0},
    #             "compose": "set",
    #         },
    #         {
    #             "service": "vol",
    #             "compose": "scale",
    #             "cfg": {
    #                 "key": "ratio_vol",
    #                 "mode": "inverse",
    #                 "target_vol": 1.0,
    #                 "floor": 0.25,
    #                 "cap": 2.0,
    #             },
    #         },
    #     ],
    # )
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
            # {
            #     "service": "vol",
            #     "compose": "scale",
            #     "cfg": {
            #         "key": "ratio_vol",
            #         "mode": "inverse",
            #         "target_vol": 1.0,
            #         "floor": 0.25,
            #         "cap": 2.0,
            #     },
            # },
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
                    "reduce_ratio": 0.0,
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
                    "reduce_ratio": 0.0,
                },
            },
        ],
    )

    instrument = "RBST"

    strat_extras = {
        "filters": [
            {"fn": block_cumulative_entries, "cfg": {"enabled": True}},
        ],
    }

    components = StrategyComponents(
        # feature_map={}, 
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
        # source_fn=compute_scores_1d,
        # normalizer_fn=normalize_1d_to_fls,
        extras=strat_extras,
    )


def build_calib_rbst() -> CalibrationConfig:
    """
    CalibrationConfig (search_space + objective) pour WF RBST.
    """
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
        weights={"sharpe": 3.0, "total_return_pct": 0.75, "max_drawdown": -3.0},
        # min_trades=3,
        # min_sharpe=1.0,
        # mdd_max=0.20,
        top_k=nb_trials,
    )

    split_cfg = SplitConfig(
        mode="walk_bars",
        train_bars=168,
        test_bars=42,
        stride_bars=42,
        gap_bars=0,
        include_tail=True,
    )

    calib_cfg = CalibrationConfig(
        search_space=space,
        objective=obj,
        bind_fn=bind_params_v2,
        keep_artifacts=False,
        top_k=nb_trials,
        bench_key="RBST",
        initial_inv=CAPITAL_INITIAL,
        tick_size=0.0,
        walk_mode="carry",
        n_jobs = 11,
    )

    return calib_cfg, split_cfg


# ============================================================
# Enregistrement du profil dans le registry
# ============================================================

PROFILE_NAME = "robusta_zscore_fut_shifted_wf"

PROFILE = UseCaseProfile(
    name=PROFILE_NAME,
    data_builder=data_builder,
    strategy_cfg_builder=build_strategy_rbst,
    calib_builder=build_calib_rbst,
    bench_key = "RBST",
    wf_json_path=Path("save_wf_simu/calib_temp/rbst_zscore_fut_calibration.json"),

)

register_profile(PROFILE)
