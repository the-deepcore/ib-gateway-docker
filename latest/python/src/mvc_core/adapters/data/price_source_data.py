from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class PriceSource:
    """Config for selecting a reference price column."""
    kind: str = "mid"
    col_map: Optional[Dict[str, str]] = None

    def __post_init__(self) -> None:
        if self.col_map is None:
            self.col_map = {
                "mid": "MID",
                "bid": "BID",
                "offer": "OFFER",
                "spread": "SPREAD",
                "close": "Close",
                "open": "Open",
                "high": "High",
                "low": "Low",
            }
