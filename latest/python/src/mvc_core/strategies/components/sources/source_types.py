from dataclasses import dataclass, field
from typing import Any, Dict, Union

import pandas as pd


@dataclass(frozen=True)
class SourceOutput:
    """Scores + optional meta."""
    scores: Union[pd.Series, pd.DataFrame]
    meta: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        object.__setattr__(self, "meta", dict(self.meta))



