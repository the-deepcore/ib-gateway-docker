from __future__ import annotations

from typing import Any, Dict, List

from mvc_core.domain.enums import Action
from mvc_core.engine.signals.signal_data import TradeSignal


def block_cumulative_entries(
    *,
    ts,
    instrument: str,
    state: Dict[str, Any],
    signals: List[TradeSignal],
    cfg: Dict[str, Any],
    hls_row=None,
    feature_set=None,
) -> List[TradeSignal]:

    out: List[TradeSignal] = []
    for s in signals:
        if getattr(s, "action", None) == Action.OPEN:
            meta = getattr(s, "meta", {}) or {}
            if meta.get("is_add", False) or meta.get("legs_before", 0) >= 1:
                continue 
        out.append(s)
    return out


