
from typing import Dict

from mvc_app.usecases.profile_base.profile_data import UseCaseProfile

_registry: Dict[str, UseCaseProfile] = {}


def register_profile(profile: UseCaseProfile) -> None:
    """
    Enregistre un use case (WF ou inference-only) dans le registry global.
    """
    if profile.name in _registry:
        raise ValueError(f"Use case profile '{profile.name}' already registered")
    _registry[profile.name] = profile


def get_profile(name: str) -> UseCaseProfile:
    try:
        return _registry[name]
    except KeyError:
        raise KeyError(f"Unknown use case profile '{name}'")
