from __future__ import annotations

import itertools
import math
import random
from typing import Any, Dict, Iterable, List

from .search_space_data import Choice, RangeFloat, RangeInt, SearchSpace


def _values_from_param(p: Any) -> List[Any]:
    if isinstance(p, Choice):
        return list(p.values)

    if isinstance(p, RangeInt):
        if p.step <= 0:
            raise ValueError("RangeInt.step must be > 0")
        return list(range(p.low, p.high + 1, p.step))

    if isinstance(p, RangeFloat):
        if p.step is None:
            raise ValueError("RangeFloat requires 'step' for grid")
        if p.step <= 0:
            raise ValueError("RangeFloat.step must be > 0")
        n = int(math.floor((p.high - p.low) / p.step + 0.5))
        xs = [p.low + i * p.step for i in range(n + 1)]
        xs = [x for x in xs if x <= p.high + 1e-12]
        return xs

    raise TypeError("Unsupported param type")


def iter_grid(space: SearchSpace) -> Iterable[Dict[str, Any]]:
    keys = list(space.spec.keys())
    grids = [_values_from_param(space.spec[k]) for k in keys]
    for vals in itertools.product(*grids):
        yield dict(zip(keys, vals))


def _random_pick_from_param(p: Any, rng: random.Random) -> Any:
    if isinstance(p, Choice):
        return rng.choice(p.values)

    if isinstance(p, RangeInt):
        if p.step == 1:
            return rng.randint(p.low, p.high)
        k = (p.high - p.low) // p.step
        i = rng.randint(0, k)
        return p.low + i * p.step

    if isinstance(p, RangeFloat):
        x = rng.uniform(p.low, p.high)
        if p.step is None:
            return x
        i = round((x - p.low) / p.step)
        return p.low + i * p.step

    raise TypeError("Unsupported param type")


def iter_random(space: SearchSpace) -> Iterable[Dict[str, Any]]:
    trials = space.n_trials
    if trials is None or trials <= 0:
        raise ValueError("SearchSpace.n_trials must be set for random")
    rng = random.Random(space.seed)
    keys = list(space.spec.keys())
    for _ in range(trials):
        yield {k: _random_pick_from_param(space.spec[k], rng) for k in keys}



# ======================================================
# ======================================================
# ======================================================
# ======================================================
# ======================================================
# ======================================================
# ======================================================
# ======================================================
# ======================================================
# ======================================================
# ======================================================
# ======================================================
# ======================================================
# ======================================================
# ======================================================
# ======================================================



from typing import Any, Dict, Iterable, List


def suggest_from_space(trial, space: SearchSpace) -> Dict[str, Any]:
    """
    Traduction SearchSpace -> suggestions Optuna pour un 'trial'.
    Supporte Choice, RangeFloat, RangeInt (avec step facultatif).
    """
    params: Dict[str, Any] = {}
    for name, p in space.spec.items():
        if isinstance(p, Choice):
            params[name] = trial.suggest_categorical(name, list(p.values))
        elif isinstance(p, RangeFloat):
            # step optionnel -> espace continu si None, discret sinon
            if p.step is None:
                params[name] = trial.suggest_float(name, float(p.low), float(p.high))
            else:
                params[name] = trial.suggest_float(name, float(p.low), float(p.high), step=float(p.step))
        elif isinstance(p, RangeInt):
            step = getattr(p, "step", 1)
            params[name] = trial.suggest_int(name, int(p.low), int(p.high), step=int(step))
        else:
            raise TypeError(f"Unsupported param type for '{name}': {type(p)}")
    return params
