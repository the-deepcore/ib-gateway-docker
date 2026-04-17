from dataclasses import dataclass
from typing import Dict, Literal, Optional


@dataclass(frozen=True)
class ObjectiveConfig:
    """Objective function config."""
    direction: Literal["maximize", "minimize"] = "maximize"
    weights: Optional[Dict[str, float]] = None
    min_mdd: Optional[float] = None
    mdd_max: Optional[float] = None
    min_sharpe: Optional[float] = None
    min_total_return: Optional[float] = None
    max_vol_annualized: Optional[float] = None
    top_k: int = 1

    min_trades : Optional[int] = None
