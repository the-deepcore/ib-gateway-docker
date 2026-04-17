from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class SplitConfig:
    """Split definition."""
    mode: str
    train_start: Optional[str] = None
    train_end: Optional[str] = None
    test_start: Optional[str] = None
    test_end: Optional[str] = None
    
    train_bars: Optional[int] = None
    test_bars: Optional[int] = None
    stride_bars: Optional[int] = None
    gap_bars: int = 0
    include_tail: bool = True
