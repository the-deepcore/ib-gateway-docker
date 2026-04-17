from dataclasses import dataclass
from typing import Any, Dict, Optional

import pandas as pd

from mvc_core.domain.enums import Side, Status


@dataclass
class Position:
    """Position data container."""
    instrument: Any
    side: Side
    lots: int
    multiplier: float
    entry_date: pd.Timestamp
    entry_price_raw: float
    entry_price_eff: float
    meta: Optional[Dict[str, Any]] = None

    status: Status = Status.OPEN
    exit_date: Optional[pd.Timestamp] = None
    exit_price_raw: Optional[float] = None
    exit_price_eff: Optional[float] = None
    realized_pnl: float = 0.0

    def __post_init__(self):
        if not isinstance(self.side, Side):
            raise TypeError(f"side must be Side enum, got {type(self.side)}")
        if not isinstance(self.status, Status):
            raise TypeError(f"status must be Status enum, got {type(self.status)}")
        if int(self.lots) <= 0:
            raise ValueError(f"lots must be > 0, got {self.lots}")
        if float(self.multiplier) <= 0:
            raise ValueError(f"multiplier must be > 0, got {self.multiplier}")

        self.lots = int(self.lots)
        self.multiplier = float(self.multiplier)
        self.entry_date = pd.Timestamp(self.entry_date)
        self.entry_price_raw = float(self.entry_price_raw)
        self.entry_price_eff = float(self.entry_price_eff)
        self.meta = dict(self.meta or {})