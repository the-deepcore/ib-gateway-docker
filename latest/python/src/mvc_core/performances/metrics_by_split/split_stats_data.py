from dataclasses import dataclass
from typing import Optional

from mvc_core.engine.run.run_data import RunMetrics


@dataclass
class SplitMetrics(RunMetrics):
    split_id: Optional[int] = None
    # train_start: Optional[str] = None
    # train_end: Optional[str] = None
    test_start: Optional[str] = None
    test_end: Optional[str] = None
    # period_label: Optional[str] = None

