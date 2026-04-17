from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from mvc_core.domain.portfolio.position_data import Position


@dataclass
class Portfolio:
    """Portfolio data container."""
    initial_inv: float
    instruments: Dict[str, Any] = field(default_factory=dict)
    cash: Optional[float] = None
    total_borrowed: float = 0.0
    positions: List[Position] = field(default_factory=list)

    def __post_init__(self):
        self.initial_inv = float(self.initial_inv)
        self.cash = float(self.cash) if self.cash is not None else float(self.initial_inv)
