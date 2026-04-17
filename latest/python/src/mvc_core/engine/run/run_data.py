from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import pandas as pd

from mvc_core.domain.clock.clock_data import Clock
from mvc_core.domain.portfolio.portfolio_data import Portfolio
from mvc_core.strategies.build.build_data import BuiltStrategy


@dataclass
class RunCfg:


    clock: Clock
    price_series: Dict[str, pd.Series]
    built_strat: BuiltStrategy

    bench_key: Optional[str] = None
    initial_inv: float = 30_000_000.0
    tick_size: float = 0.0
    keep_artifacts: bool = True

    tags: Dict[str, Any] = field(default_factory=dict)
    initial_portfolio: Optional[Portfolio] = None


@dataclass
class RunArtifacts:


    equity_df: pd.DataFrame
    decisions: Any
    portfolio: Portfolio


@dataclass
class RunMetrics:


    sharpe: float
    mdd: float
    cagr: float
    vol: float
    total_return_pct: float
    nb_trades: float


@dataclass
class RunResult:

    cfg: RunCfg
    artifacts: RunArtifacts
    metrics: RunMetrics
    extra: Dict[str, Any] = field(default_factory=dict)
