from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from mvc_core.domain.enums import Action, Side
from mvc_core.engine.signals.signal_data import TradeSignal
from mvc_core.strategies.build.callable_types import SignalizerFn


def _legs_key(instrument: str, side: Side) -> Tuple[str, str]:
    return instrument, side.value

def _inc_legs(state: Dict[str, Any], instrument: str, side: Side) -> int:
    legs = state.setdefault("open_legs", {})
    k = _legs_key(instrument, side)
    legs[k] = int(legs.get(k, 0)) + 1
    return legs[k]

def _reset_legs(state: Dict[str, Any], instrument: str, side: Side) -> None:
    legs = state.setdefault("open_legs", {})
    k = _legs_key(instrument, side)
    legs[k] = 0
    # also reset cooldown tracker
    last_add = state.setdefault("last_add_bar_idx", {})
    if k in last_add:
        del last_add[k]

def _get_legs(state: Dict[str, Any], instrument: str, side: Side) -> int:
    return int(state.setdefault("open_legs", {}).get(_legs_key(instrument, side), 0))


# ------------------------------
# Helpers: base transitions F/L/S
# ------------------------------

def _base_transitions_from_fls(
    ts: pd.Timestamp,
    fls_row: Dict[str, int],
    instrument: str,
    state: Dict[str, Any],
) -> List[TradeSignal]:
    """
    Convert a F/L/S row to OPEN/CLOSE transitions (no accumulation).
    Keeps a simple 'current_side' in state[(instrument)].
    """
    out: List[TradeSignal] = []
    cur_side: Optional[Side] = state.setdefault("current_side_map", {}).get(instrument, None)

    is_long = int(fls_row.get(Side.LONG, 0)) == 1
    is_short = int(fls_row.get(Side.SHORT, 0)) == 1

    if is_long :
        if cur_side == Side.SHORT:
            out.append(TradeSignal(action=Action.CLOSE, instrument=instrument, side=Side.SHORT))
            _reset_legs(state, instrument, Side.SHORT)

        legs_before = _get_legs(state, instrument, Side.LONG)
        out.append(TradeSignal(action=Action.OPEN,  instrument=instrument, side=Side.LONG, meta={"legs_before":legs_before}))
        state["current_side_map"][instrument] = Side.LONG
        _inc_legs(state, instrument, Side.LONG)

    elif is_short :
        if cur_side == Side.LONG:
            out.append(TradeSignal(action=Action.CLOSE, instrument=instrument, side=Side.LONG))
            _reset_legs(state, instrument, Side.LONG)

        legs_before = _get_legs(state, instrument, Side.SHORT)
        out.append(TradeSignal(action=Action.OPEN,  instrument=instrument, side=Side.SHORT, meta={"legs_before":legs_before}))
        state["current_side_map"][instrument] = Side.SHORT
        _inc_legs(state, instrument, Side.SHORT)

    else:
        pass

    return out



# # ------------------------------
# # Public builder
# # ------------------------------

def build_signalizer_fn() -> SignalizerFn:

    def signalizer_fn(ts, hls_row, instrument, state):
        signals = _base_transitions_from_fls(ts, hls_row, instrument, state)
        return signals
    
    return signalizer_fn




















