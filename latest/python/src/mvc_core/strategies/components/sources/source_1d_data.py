from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class Source1DConfig:
    """Generic 1D source config."""
    mode: str
    feature_key: Optional[str] = None
    base_key: Optional[str] = None
    modifier_key: Optional[str] = None
    ops: Optional[List[Dict[str, Any]]] = None

