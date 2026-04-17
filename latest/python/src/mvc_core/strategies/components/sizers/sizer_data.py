from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class SizerConfig:
    """Sizing recipe config."""
    name: Optional[str] = None
    enabled: bool = True
    schema_version: str = "sizer.v1"
    default_compose: str = "set"
    steps: Optional[List[Dict[str, Any]]] = None
    registry_name: Optional[str] = None
    meta: Optional[Dict[str, Any]] = None
