from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class ContractSpec:
    instrument: str
    multiplier: float


# Futures contract multipliers (USD PnL per 1.0 price move per 1 lot)
_CONTRACT_SPECS: Dict[str, ContractSpec] = {
    # Sugar #11 (ICE)
    "SB11": ContractSpec("SB11", multiplier=1120.0),

    # Arabica coffee (ICE KC)
    "ARBC": ContractSpec("ARBC", multiplier=375.0),
    "KC": ContractSpec("KC", multiplier=375.0),

    # Robusta coffee (LIFFE/ICE Europe)
    "RBST": ContractSpec("RBST", multiplier=10.0),
    "DF": ContractSpec("DF", multiplier=10.0),
}


def resolve_contract_spec(instrument: str) -> ContractSpec:
    key = str(instrument)
    if key not in _CONTRACT_SPECS:
        raise KeyError(f"No contract spec for instrument='{instrument}'")
    return _CONTRACT_SPECS[key]


def lots_from_notional_usd(*, notional_usd: float, price: float, multiplier: float) -> int:
    """Convert a USD notional target into an integer number of lots (floor)."""
    notional_usd = float(notional_usd)
    price = float(price)
    multiplier = float(multiplier)

    if notional_usd <= 0.0 or price <= 0.0 or multiplier <= 0.0:
        return 0

    lots = int(notional_usd // (price * multiplier))
    return max(0, lots)
