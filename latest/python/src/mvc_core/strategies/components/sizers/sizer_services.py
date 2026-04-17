# src/mvc_core/strategies/sizers/sizer_services.py
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from mvc_core.domain.enums import Action, Side
from mvc_core.domain.market.contract_specs import lots_from_notional_usd, resolve_contract_spec
from mvc_core.strategies.build.callable_types import SizerFn
from mvc_core.strategies.components.sizers.sizer_data import SizerConfig


def build_sizer_fn(
    config_or_steps: Optional[Any],
    registry: Optional[Dict[str, SizerFn]] = None,
    feature_map: Optional[Dict[str, pd.Series]] = None
) -> Optional[Callable]:
    """
    Build a sizer_fn from either:
      - a SizerConfig (recommended for clarity and validation), or
      - a plain list of steps (ultra-minimal mode).

    Returns
    -------
    sizer_fn(ts, instrument, signal, feature_set, hls_row, state, price_map)
      -> ("keep"|"skip", Optional[float])

    Notes
    -----
    - If input is None or disabled, returns None (no sizing).
    - Validation is performed only when a SizerConfig is provided.
    """
    if config_or_steps is None:
        return None

    if isinstance(config_or_steps, SizerConfig):
        cfg: SizerConfig = config_or_steps
        if not cfg.enabled:
            return None
        validate_sizer_config(cfg)
        steps = _materialize_steps(cfg)
        reg = registry if registry is not None else default_registry()
        default_compose = cfg.default_compose
    else:
        # Plain list of steps
        steps = list(config_or_steps or [])
        if len(steps) == 0:
            return None
        reg = registry if registry is not None else default_registry()
        default_compose = "set"

    def sizer_fn(
        ts: pd.Timestamp,
        instrument: str,
        signal: Any,
        # feature_set: Optional[Dict[str, Any]] = None,
        hls_row: Dict[str, int],
        state: Dict[str, Any],
        price_map: Dict[str, float],
    ) -> Tuple[str, Optional[int]]:
        if getattr(signal, "action", None) != Action.OPEN:
            return "keep", None

        size_factor: Optional[float] = None
        
        for step in steps:
            name = step.get("service")
            compose = step.get("compose", None) or default_compose
            cfg = step.get("cfg", {})

            if name not in reg:
                raise KeyError("Unknown sizing service: %s" % str(name))
            fn = reg[name]

            decision, value = fn(ts, instrument, signal, feature_map, state, price_map, cfg)
            if decision == "skip":
                return "skip", None
            if value is None:
                continue

            if compose == "set":
                size_factor = float(value)
            elif compose == "scale":
                size_factor = float(value) if size_factor is None else float(size_factor) * float(value)
            elif compose == "clip":
                mn = cfg.get("min_expo", None)
                mx = cfg.get("max_expo", None)
                if size_factor is not None:
                    if mn is not None and size_factor < float(mn):
                        size_factor = float(mn)
                    if mx is not None and size_factor > float(mx):
                        size_factor = float(mx)
            else:
                raise ValueError("Unknown compose mode: %s" % str(compose))

        meta = {}
        if isinstance(config_or_steps, SizerConfig):
            meta = config_or_steps.meta or {}

        notional_usd = meta.get("notional_usd", None)
        if notional_usd is None:
            raise ValueError("SizerConfig.meta['notional_usd'] is required for lot sizing")

        if instrument not in price_map:
            raise KeyError(f"Missing price for instrument '{instrument}' in price_map")

        px = float(price_map[instrument])
        spec = resolve_contract_spec(instrument)
        mult = float(spec.multiplier)

        f = 1.0 if size_factor is None else float(size_factor)
        # If fixed_notional is set, ignore scaling steps and use raw notional
        use_fixed = bool(meta.get("fixed_notional", False))
        target_notional = float(notional_usd) if use_fixed else float(notional_usd) * f

        lots = lots_from_notional_usd(notional_usd=target_notional, price=px, multiplier=mult)
        return "keep", int(lots)

    return sizer_fn


def default_registry() -> Dict[str, SizerFn]:
    """Default registry of sizing steps. Extend/override at call site if needed."""
    return {
        "constant": step_constant,
        "vol": step_vol,
        "accum": step_accum,
        "clip":step_clip,
    }


# ---- Validation & materialization --------------------------------------

def validate_sizer_config(cfg: SizerConfig) -> None:
    """
    Validate a SizerConfig (schema + allowed compose values).
    Raises ValueError/TypeError if invalid.
    """
    if not isinstance(cfg.schema_version, str) or not cfg.schema_version:
        raise ValueError("SizerConfig.schema_version must be a non-empty str")
    if cfg.default_compose not in ("set", "scale", "clip"):
        raise ValueError("SizerConfig.default_compose must be one of: set|scale|clip")
    if not isinstance(cfg.steps, list):
        raise TypeError("SizerConfig.steps must be a list")

    for i, step in enumerate(cfg.steps):
        if not isinstance(step, dict):
            raise TypeError("Step #%d must be a dict" % i)
        if "service" not in step:
            raise ValueError("Step #%d missing 'service'" % i)
        if "cfg" not in step or not isinstance(step["cfg"], dict):
            raise ValueError("Step #%d missing 'cfg' dict" % i)
        compose = step.get("compose", None)
        if compose is not None and compose not in ("set", "scale", "clip"):
            raise ValueError("Step #%d has invalid compose='%s'" % (i, str(compose)))


def _materialize_steps(cfg: SizerConfig) -> List[Dict[str, Any]]:
    """Make a defensive copy of steps (could also merge defaults here if needed)."""
    return [dict(s) for s in cfg.steps]


# ---- Built-in sizing steps ---------------------------------------------

def step_constant(
    ts: pd.Timestamp,
    instrument: str,
    signal: Any,
    feature_set: Dict[str, Any],
    state: Dict[str, Any],
    price_map: Dict[str, float],
    cfg: Dict[str, Any],
) -> Tuple[str, Optional[float]]:
    """Set a baseline exposure. Use with compose='set'. cfg: {'value': float}"""
    val = cfg.get("value", None)
    if val is None:
        return "keep", None
    return "keep", float(val)


def step_vol(
    ts: pd.Timestamp,
    instrument: str,
    signal: Any,
    feature_set: Dict[str, Any],
    state: Dict[str, Any],
    price_map: Dict[str, float],
    cfg: Dict[str, Any],
) -> Tuple[str, Optional[float]]:
    """
    Scale exposure based on volatility. Use with compose='scale'.
    cfg:
      key: str   (feature key -> Series or 1-col DataFrame aligned to clock)
      mode: 'inverse'|'linear'|'bucket' (default 'inverse')
      target_vol: float (for 'inverse')
      floor: Optional[float]
      cap: Optional[float]
      buckets: Optional[List[Tuple[float, float]]]  # (upper, mult) for 'bucket'
    """
    key = cfg.get("key", None)
    if key is None or key not in feature_set:
        return "keep", None

    series = feature_set[key]
    if isinstance(series, pd.Series):
        vol = series.get(ts, None)
    else:
        try:
            vol = series.loc[ts].item()
        except Exception:
            vol = None

    if vol is None or pd.isna(vol):
        return "keep", None

    mode = str(cfg.get("mode", "inverse"))
    floor = cfg.get("floor", None)
    cap = cfg.get("cap", None)

    if mode == "inverse":
        tgt = cfg.get("target_vol", None)
        if tgt is None or float(vol) <= 0.0:
            return "keep", None
        mult = float(tgt) / float(vol)

        if mult>cap:
            mult=cap
        elif mult<floor:
            mult=floor

    elif mode == "linear":
        a = float(cfg.get("a", 0.0))
        b = float(cfg.get("b", 1.0))
        mult = a * float(vol) + b
    elif mode == "bucket":
        buckets = cfg.get("buckets", [])
        mult = None
        for upper, m in buckets:
            if float(vol) <= float(upper):
                mult = float(m)
                break
        if mult is None and len(buckets) > 0:
            mult = float(buckets[-1][1])
        if mult is None:
            return "keep", None
    else:
        raise ValueError("vol step: unsupported mode %s" % mode)

    if floor is not None:
        mult = max(float(mult), float(floor))
    if cap is not None:
        mult = min(float(mult), float(cap))

    return "keep", float(mult)


def step_accum(
    ts: pd.Timestamp,
    instrument: str,
    signal: Any,
    feature_set: Dict[str, Any],
    state: Dict[str, Any],
    price_map: Dict[str, float],
    cfg: Dict[str, Any],
) -> Tuple[str, Optional[float]]:
    """
    Exposure for accumulation 'adds' (decreasing increments).
    Assume `state['open_legs'][(instrument, side)]` holds current logical count.
    cfg:
      coef_pos: float (default 1.0)
      log_coeff: float (default 2.5)
      min_expo_if_first: float (default 1.0)
      cap_total: Optional[float] (clip on logical total: open_legs + this add)
    """
    coef_pos = float(cfg.get("coef_pos", 1.0))
    log_coeff = float(cfg.get("log_coeff", 2.5))
    min_first = float(cfg.get("min_expo_if_first", 1.0))

    side = getattr(signal, "side", None)
    legs_before = None


    if hasattr(signal, "meta") and isinstance(signal.meta, dict):
        legs_before = signal.meta.get("legs_before", None)

    if legs_before is None: # Fallback old behaviour
        key = (instrument, side.value if isinstance(side, Side) else str(side))
        open_legs_map = state.setdefault("open_legs", {})
        nb_open = int(open_legs_map.get(key, 0))
    else:
        nb_open = int(legs_before)

    if nb_open <= 0:
        expo = coef_pos * min_first
    else:
        n = 2.0 + float(nb_open)
        add_expo = float(log_coeff) * float(np.log(n / (n - 1.0)))
        expo = coef_pos * add_expo

    return "keep", float(expo)


def step_clip(
    ts: pd.Timestamp,
    instrument: str,
    signal: Any,
    feature_set: Dict[str, Any],
    state: Dict[str, Any],
    price_map: Dict[str, float],
    cfg: Dict[str, Any],
) -> Tuple[str, Optional[float]]:
    """Compose='clip' uses min/max from cfg; this step returns None."""
    return "keep", None
