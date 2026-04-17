from dataclasses import dataclass

from mvc_core.domain.enums import CrossSense, TriggerMode


@dataclass(frozen=True)
class Threshold1DConfig:
    """1D thresholds to map scores to H/L/S."""
    low: float
    high: float

    # scale_key: Optional[str]=None
# TODO POSITION mode is obsolete, refactoring 

    mode: TriggerMode
    cross_sense: CrossSense
    start_hold: bool = True

    def __post_init__(self):
        if self.low > self.high:
            raise ValueError("low must be <= high")
