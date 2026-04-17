from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

from mvc_core.strategies.build.callable_types import ParamBindFn


@dataclass(frozen=True)
class CalibrationConfig:
    """Calibration setup."""
    search_space: Any
    objective: Any
    bind_fn: ParamBindFn
    keep_artifacts: bool = False
    top_k: int = 1
    bench_key: Optional[str] = None
    initial_inv: float = 100_000.0
    tick_size: float = 0.0
    strict_params: bool = True
    walk_mode: Literal["flat", "carry"] = "flat"
    n_jobs: int = 1   

@dataclass
class CalibrationReport:
    """Calibration results."""
    splits: List[Dict[str, Any]] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)
