from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

from mvc_core.strategies.build.callable_types import NormalizerFn, SourceComputeFn
from mvc_core.strategies.components.features.feature_data import InputSpec


@dataclass
class StrategyComponents:
    # feature_map: Dict[str, pd.Series]
    source_fn: Optional[SourceComputeFn] = None
    normalizer_fn: Optional[NormalizerFn] = None

    signalizer_fn: Optional[Callable] = None
    sizer_fn: Optional[Callable] = None
    risk_fn: Optional[Callable] = None



@dataclass(frozen=True)
class StrategyCfg:

    instrument: str
    input_spec: InputSpec

    source_cfg: Any
    normalizer_cfg: Any

    components: StrategyComponents

    sizer_cfg: Optional[Any] = None
    risk_cfg: Optional[Any] = None

# #to delete
#     source_fn: Optional[SourceComputeFn] = None
#     normalizer_fn: Optional[NormalizerFn] = None

    extras: Dict[str, Any] = field(default_factory=dict)


