from typing import Callable, Dict, Any, List, Tuple, Optional
import pandas as pd
from mvc_core.engine.signals.signal_data import TradeSignal
from mvc_core.domain.portfolio.portfolio_data import Portfolio
# from mvc_core.strategies.core.strategy_data import StrategyCfg # cannot import because of circular import


SourceComputeFn = Callable[[Dict[str, pd.Series], Any], Any]

NormalizerFn = Callable[[pd.Index, pd.Series, Any], pd.DataFrame]

SizerFn = Callable[
    [pd.Timestamp, str, TradeSignal, Dict[str, pd.Series], Dict[str, int], Dict[str, Any], Dict[str, float]],
    Tuple[str, Optional[float]]
]


SignalizerFn = Callable[
    [pd.Timestamp, Dict[str, int], str, Dict[str, Any]],
    List[TradeSignal]
]
RiskFn = Callable[[pd.Timestamp, Dict[str, float], Portfolio], List[TradeSignal]]

SignalFn = Callable[[pd.Timestamp, Dict[str, float]], List[TradeSignal]]

ParamBindFn = Callable[[Dict[str, Any], Any], Dict[str, Any]]