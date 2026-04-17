from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class RiskConfig:
    """Risk rules config."""
    enabled: bool = True
    rules: Optional[List[Dict[str, Any]]] = None
    meta: Optional[Dict[str, Any]] = None
