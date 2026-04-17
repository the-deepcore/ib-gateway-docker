from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class JobConfig:
    """
    Configuration d'un job WF.

    - profile_name : nom du use-case (ex: "wf_sb11")
    - run_id       : identifiant logique du run de calibration (facultatif)
    - extra        : dict extensible pour plus tard (dates custom, etc.)
    """
    profile_name: str
    run_id: Optional[str] = None
    extra: Optional[Dict[str, Any]] = None
