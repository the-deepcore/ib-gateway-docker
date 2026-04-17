from dataclasses import dataclass
from typing import Any, Mapping, Optional


@dataclass(frozen=True)
class InputSpec:
    """Feature set specification."""
    base_keys: Mapping[str, Any]
    recipes: Mapping[str, Any]
    extras: Optional[Mapping[str, Any]] = None


