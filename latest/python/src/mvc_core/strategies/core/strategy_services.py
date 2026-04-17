from typing import Callable, Dict, List

import pandas as pd

from mvc_core.domain.clock.clock_data import Clock
from mvc_core.domain.enums import Side
from mvc_core.engine.signals.signal_data import TradeSignal
from mvc_core.strategies.components.features.feature_services import build_feature_set
from mvc_core.strategies.core.strategy_data import StrategyCfg


def build_signal_fn(
    clock: Clock,
    price_series: Dict[str, pd.Series],
    strategy_cfg: StrategyCfg,
) -> Callable[[pd.Timestamp, Dict[str, float]], List[TradeSignal]]:
    
    instrument = strategy_cfg.instrument
    input_spec = strategy_cfg.input_spec

    components = strategy_cfg.components
    source_compute_fn = components.source_fn
    source_cfg = strategy_cfg.source_cfg

    normalizer_fn = components.normalizer_fn
    normalizer_cfg = strategy_cfg.normalizer_cfg

    signalizer_fn = components.signalizer_fn
    sizer_fn = components.sizer_fn

    extras = strategy_cfg.extras

    # Build features
    feature_set = build_feature_set(clock, price_series, input_spec, fill_method="dropna")

    # Source
    src_out = source_compute_fn(feature_set, source_cfg)
    scores = src_out.scores

    # Normalizer
    low_series = extras.get("low_series")
    high_series = extras.get("high_series")
    signal_filters = extras.get("filters", [])

    if low_series is not None or high_series is not None:
        hls_df = normalizer_fn(clock.index, scores, normalizer_cfg, low_series=low_series, high_series=high_series)
    else:
        hls_df = normalizer_fn(clock.index, scores, normalizer_cfg)

    state: Dict[str, object] = {}

    def _fn(ts: pd.Timestamp, price_map: Dict[str, float]) -> List[TradeSignal]:
        if ts not in hls_df.index:
            return []
        row = hls_df.loc[ts]
        hls_row = {
            Side.FLAT: int(row.get(Side.FLAT, 1)),
            Side.LONG: int(row.get(Side.LONG, 0)),
            Side.SHORT: int(row.get(Side.SHORT, 0)),
        }

        # Seed state (WF carry mode)
        if extras and not state.get("_wf_seeded", False):
            seed = extras.get("seed_state")
            if seed:
                side = seed.get("current_side")
                legs = int(seed.get("legs", 0) or 0)
                if side:
                    state.setdefault("current_side_map", {})[instrument] = side
                    if legs > 0:
                        state.setdefault("open_legs", {})[(instrument, side.value)] = legs
            state["_wf_seeded"] = True

        # Signalizer
        signals = signalizer_fn(ts, hls_row, instrument, state)

        # Filters
        if signal_filters:
            for f in signal_filters:
                fn = f["fn"] if isinstance(f, dict) else getattr(f, "fn")
                cfg = f.get("cfg", {}) if isinstance(f, dict) else getattr(f, "cfg", {})
                if cfg.get("enabled") is False:
                    continue
                signals = fn(
                    ts=ts,
                    instrument=instrument,
                    state=state,
                    signals=signals,
                    cfg=cfg,
                    hls_row=hls_df.loc[ts] if ts in hls_df.index else None,
                    feature_set=feature_set,
                )

        # Sizer
        if sizer_fn is not None:
            sized: List[TradeSignal] = []
            for sig in signals:
                decision, expo = sizer_fn(
                    ts=ts,
                    instrument=instrument,
                    signal=sig,
                    # feature_set=feature_set,
                    hls_row=hls_row,
                    state=state,
                    price_map=price_map,
                )
                if decision == "skip":
                    continue
                if expo is not None and hasattr(sig, "lots"):
                    sig.lots = int(expo)
                sized.append(sig)
            signals = sized

        return signals

    return _fn


