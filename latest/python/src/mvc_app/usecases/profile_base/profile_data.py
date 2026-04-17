from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

import pandas as pd

from mvc_core.domain.clock.clock_data import Clock
from mvc_core.optimize.calibration.calibration_data import CalibrationConfig
from mvc_core.optimize.components.splitter.splitter_data import SplitConfig
from mvc_core.strategies.core.strategy_data import StrategyCfg

DataBuilder = Callable[[], Tuple[Clock, Dict[str, pd.Series]]]
StrategyCfgBuilder = Callable[[Clock, Dict[str, pd.Series]], StrategyCfg]
CalibrationBuilder = Callable[[], Tuple[CalibrationConfig, SplitConfig]]



@dataclass
class UseCaseProfile:

    name: str

    data_builder: DataBuilder
    strategy_cfg_builder: StrategyCfgBuilder

    calib_builder: Optional[CalibrationBuilder] = None



    bench_key: str = "SB11"
    wf_json_path: Optional[Path] = None

    @property
    def has_calibration(self) -> bool:

        return self.calib_builder is not None and self.wf_json_path is not None
