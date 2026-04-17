from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pandas as pd

from mvc_core.domain.clock.clock_data import Clock
from mvc_core.domain.enums import Action, Side
from mvc_core.domain.portfolio.portfolio_data import Portfolio


@dataclass
class TradeSignal:
    """Strategy signal."""
    action: Action
    instrument: str
    side: Optional[Side] = None
    lots: Optional[int] = None
    reduce_ratio: Optional[float] = None
    meta: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        self.meta = dict(self.meta)


@dataclass
class BacktesterCfg:
    """Backtest container."""
    clock: Clock
    portfolio: Portfolio
    price_series: Dict[str, pd.Series]
    tick_size: float = 0.01
    trades_log: List[Dict[str, Any]] = field(default_factory=list)
