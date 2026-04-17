from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional, Union


@dataclass(frozen=True)
class Choice:
    """Discrete choices."""
    values: List[Any]

@dataclass(frozen=True)
class RangeFloat:
    """Float range."""
    low: float
    high: float
    step: Optional[float] = None

@dataclass(frozen=True)
class RangeInt:
    """Int range."""
    low: int
    high: int
    step: Optional[int] = None

Param = Union[Choice, RangeFloat, RangeInt]

@dataclass(frozen=True)
class SearchSpace:
    """Search space."""
    engine: Literal["grid", "random", "optuna"]
    spec: Dict[str, Param]
    n_trials: Optional[int] = None
    seed: int = 42
