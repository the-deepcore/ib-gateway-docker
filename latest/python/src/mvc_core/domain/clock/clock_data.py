from dataclasses import dataclass

import pandas as pd


@dataclass
class Clock:
    """Time backbone used across the framework.
    
    Attributes:
        index: UTC, strictly increasing, non-empty timeline
        cursor: Current pointer into index (0..len(index)-1)
    """
    index: pd.DatetimeIndex
    cursor: int = 0

    def __post_init__(self):
        if not isinstance(self.index, pd.DatetimeIndex):
            raise TypeError("Clock.index must be a pandas.DatetimeIndex")

        # Normalize to UTC tz-aware
        if self.index.tz is None:
            self.index = self.index.tz_localize("UTC")
        else:
            self.index = self.index.tz_convert("UTC")

        if not self.index.is_monotonic_increasing:
            self.index = self.index.sort_values()

        if len(self.index) == 0:
            raise ValueError("Clock.index must be non-empty")

        if self.cursor < 0 or self.cursor > len(self.index) - 1:
            raise ValueError("Clock.cursor out of bounds")
