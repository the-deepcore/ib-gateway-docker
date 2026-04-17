from typing import Dict, Optional

import pandas as pd

from mvc_core.domain.clock.clock_data import Clock
from mvc_core.domain.clock.clock_services import align_to_clock
from mvc_core.strategies.components.features.transforms_services import apply_ops

from .feature_data import InputSpec

# def build_feature_set(
#     clock: Clock,
#     price_series: Dict[str, pd.Series],
#     spec: InputSpec,
#     fill_method: Optional[str] = "ffill",
# ) -> Dict[str, pd.Series]:
    
#     """Build features per spec; apply shifts here; align to Clock."""

#     input_spec = deepcopy(spec)

#     bases: Dict[str, pd.Series] = {}
#     for alias, key in input_spec.base_keys.items():
#         if key not in price_series:
#             raise KeyError(f"Missing base key '{key}' in price_series")
#         bases[alias] = price_series[key]

#     features: Dict[str, pd.Series] = {}
#     for feat_name, recipe in input_spec.recipes.items():
#         base_alias = recipe.get("base")
#         if base_alias not in bases:
#             raise KeyError(f"Unknown base alias '{base_alias}' in recipes")
#         base = bases[base_alias]
#         ops = recipe.get("ops", [])
#         s = apply_ops(base, ops)
#         s = align_to_clock(s, clock, method=fill_method)
#         features[feat_name] = s

#     for alias, s in bases.items():
#         features[alias] = align_to_clock(s, clock, method=fill_method)

#     return features




def build_feature_set(
    clock: Clock,
    price_series: Dict[str, pd.Series],
    spec: InputSpec,
    fill_method: Optional[str] = "ffill",
) -> Dict[str, pd.Series]:
    """Build feature set from InputSpec recipes."""
    
    bases: Dict[str, pd.Series] = {}
    for alias, key in spec.base_keys.items():
        if key not in price_series:
            raise KeyError(f"Missing base key '{key}' in price_series")
        bases[alias] = price_series[key]

    features: Dict[str, pd.Series] = {}
    
    for feat_name, recipe in spec.recipes.items():
        base_alias = recipe.get("base")
        if base_alias not in bases:
            raise KeyError(f"Unknown base alias '{base_alias}' in recipe '{feat_name}'")
        
        base = bases[base_alias]
        ops = recipe.get("ops", [])
        
        # ✅ Passer price_series à apply_ops
        s = apply_ops(base, ops, optional_time_series=bases)
        
        s = align_to_clock(s, clock, method=fill_method)
        features[feat_name] = s

    for alias, s in bases.items():
        features[alias] = align_to_clock(s, clock, method=fill_method)

    return features