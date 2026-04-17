from typing import Dict

import pandas as pd

from .source_1d_data import Source1DConfig
from .source_types import SourceOutput


def compute_scores_1d(
    feature_set: Dict[str, pd.Series],
    cfg: Source1DConfig,
) -> SourceOutput:
    """Return 1D score from feature key or on-the-fly recipe."""
    if cfg.mode == "by_feature_key":
        if cfg.feature_key is None or cfg.feature_key not in feature_set:
            raise KeyError("feature_key missing in feature_set")
        s = feature_set[cfg.feature_key].astype(float)

        if getattr(cfg, "modifier_key", None):
            mk = cfg.modifier_key
            if mk not in feature_set:
                raise KeyError(f"modifier_key '{mk}' missing in feature_set")
            m = feature_set[mk].astype(float).reindex(s.index)
            s = s * m

        return SourceOutput(scores=s, meta={"name": f"1D:{cfg.feature_key}"})

    # elif cfg.mode == "by_recipe":
    #     if cfg.base_key is None or cfg.base_key not in feature_set:
    #         raise KeyError("base_key missing in feature_set")
    #     base = feature_set[cfg.base_key].astype(float)
    #     s = apply_ops(base, cfg.ops)
    #     return SourceOutput(scores=s, meta={"name": "1D:recipe"})

    else:
        raise ValueError("mode must be 'by_feature_key' or 'by_recipe'")
