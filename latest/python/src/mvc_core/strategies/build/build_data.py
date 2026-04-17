from dataclasses import dataclass, field
from typing import Any, Mapping, Optional
from mvc_core.strategies.core.strategy_data import StrategyCfg




from mvc_core.strategies.build.callable_types import SignalFn, RiskFn


# --- Runtime container ------------------------------------------------------

@dataclass(frozen=True)
class BuiltStrategy:
    """
    Stratégie prête à l'exécution.

    - strategy_cfg : config déclarative d'origine
    - instrument   : instrument principal de trading
    - signal_fn    : fonction de génération de signaux
    - risk_fn      : fonction de risk management (peut être None)
    - feature_map  : mapping des features calculés (clé -> série / dataframe)
    """

    strategy_cfg: StrategyCfg
    instrument: str

    signal_fn: SignalFn
    risk_fn: Optional[RiskFn] = None

    feature_map: Mapping[str, Any] = field(default_factory=dict)
