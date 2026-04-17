from typing import Dict

import pandas as pd

from mvc_core.domain.clock.clock_data import Clock

from mvc_core.strategies.components.features.feature_services import build_feature_set
from mvc_core.strategies.core.strategy_data import StrategyCfg, StrategyComponents
from mvc_core.strategies.build.build_data import BuiltStrategy

from mvc_core.strategies.components.sources.source_1d_data import Source1DConfig

from mvc_core.strategies.components.sources.source_1d_services import compute_scores_1d


from mvc_core.strategies.components.normalizers.threshold_1d_data import Threshold1DConfig
from mvc_core.strategies.components.normalizers.threshold_1d_services import normalize_1d_to_fls

from mvc_core.strategies.components.sizers.sizer_services import build_sizer_fn
from mvc_core.strategies.components.signalizer.signalizer_services import build_signalizer_fn
from mvc_core.strategies.components.risk.risk_services import build_risk_fn


from mvc_core.strategies.core.strategy_services import build_signal_fn

from mvc_core.strategies.build.callable_types import SignalFn




def build_runtime_strategy(
    clock: Clock,
    price_series: Dict[str, pd.Series],
    strategy_cfg: StrategyCfg,
) -> BuiltStrategy:
    from mvc_core.domain.clock.clock_services import build_from_index
    
    # 1) Determine if we need extended clock for lookback (KNN warm-up)
    src_cfg = strategy_cfg.source_cfg
    lookback_bars = getattr(src_cfg, "lookback_bars", 0)
    feature_clock = clock
    
    if lookback_bars > 0:
        # Find a reference price series to get historical dates
        ref_key = next(iter(price_series.keys()), None)
        if ref_key is not None:
            ref_series = price_series[ref_key]
            # Get dates before clock start
            clock_start = clock.index[0]
            hist_dates = ref_series.index[ref_series.index < clock_start]
            if len(hist_dates) >= lookback_bars:
                # Take last lookback_bars dates before clock
                lookback_dates = hist_dates[-lookback_bars:]
                extended_index = lookback_dates.append(clock.index).unique().sort_values()
                feature_clock = build_from_index(extended_index)
    
    # 2) Feature map (built on potentially extended clock)
    fill_method = strategy_cfg.extras.get("feature_fill_method", "dropna")
    feature_map: Dict[str, pd.Series] = build_feature_set(
        feature_clock,
        price_series,
        strategy_cfg.input_spec,
        fill_method=fill_method,
    )



    # 2) Compléter StrategyComponents
    components = strategy_cfg.components

    # Source fn
    if components.source_fn is None:
        source_cfg = strategy_cfg.source_cfg
        if isinstance(source_cfg, Source1DConfig):
            source_fn = compute_scores_1d
        else:
            raise TypeError(f"Unsupported source_cfg type: {type(source_cfg)!r}")
    else:
        source_fn = components.source_fn


    # Normalizer fn
    if components.normalizer_fn is None:
        normalizer_cfg = strategy_cfg.normalizer_cfg
        if isinstance(normalizer_cfg, Threshold1DConfig):
            normalizer_fn = normalize_1d_to_fls
        else:
            raise TypeError(f"Unsupported normalizer_cfg type: {type(normalizer_cfg)!r}")
    else:
        normalizer_fn = components.normalizer_fn

    # Sizer fn
    if components.sizer_fn is None:
        sizer_fn = build_sizer_fn(strategy_cfg.sizer_cfg, feature_map = feature_map) if strategy_cfg.sizer_cfg else None
    else:
        sizer_fn = components.sizer_fn

    # Risk fn
    if components.risk_fn is None:
        risk_fn = build_risk_fn(strategy_cfg.risk_cfg, feature_map=feature_map) if strategy_cfg.risk_cfg else None
    else:
        risk_fn = components.risk_fn

    # Signalizer fn
    if components.signalizer_fn is None:
        signalizer_fn = build_signalizer_fn()
    else:
        signalizer_fn = components.signalizer_fn

    # Reconstruire un StrategyComponents complet
    full_components = StrategyComponents(
        source_fn=source_fn,
        normalizer_fn=normalizer_fn,
        sizer_fn=sizer_fn,
        risk_fn=risk_fn,
        signalizer_fn=signalizer_fn,
    )

    from dataclasses import replace
    strategy_cfg = replace(strategy_cfg, components=full_components)

    signal_fn: SignalFn = build_signal_fn(
        clock=clock,  
        price_series=price_series,
        strategy_cfg=strategy_cfg,
    )

    return BuiltStrategy(
        strategy_cfg=strategy_cfg,
        instrument=strategy_cfg.instrument,
        signal_fn=signal_fn,
        risk_fn=risk_fn,
        feature_map=feature_map,
    )



