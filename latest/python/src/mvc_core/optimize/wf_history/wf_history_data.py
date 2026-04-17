from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class SplitCalibrationSnapshot:
    """
    Snapshot "persistable" d'un split walk-forward.

    On ne stocke que ce qui est utile et stable :
      - bornes de train / test (timestamps en ISO)
      - combo choisi
      - score
      - métriques OOS
    """
    split_id: int

    train_start: str
    train_end: str
    test_start: str
    test_end: str

    best_params: Dict[str, Any]
    best_score: float
    metrics: Dict[str, float]


@dataclass
class WFCalibrationRun:
    """
    Artefact de calibration walk-forward complet.

    - use_case_name : ex: "wf_sb11"
    - run_id : identifiant de la run (UUID, timestamp...)
    - created_at : timestamp de création (ISO)
    - split_config / search_space_cfg / objective_cfg :
        snapshots serialisables (dict) des configs utilisées
    - splits : résultats par split
    - summary : résumé global (moyennes OOS, etc.)
    """
    use_case_name: str
    run_id: str
    created_at: str

    split_config: Dict[str, Any]
    search_space_cfg: Dict[str, Any]
    objective_cfg: Dict[str, Any]

    splits: List[SplitCalibrationSnapshot] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)
