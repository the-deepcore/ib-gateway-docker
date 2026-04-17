from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd

from .objective_data import ObjectiveConfig


def _bad_score(direction: str) -> float:
    return -1e9 if direction == "maximize" else 1e9


def compute_score(metrics: Dict[str, float], cfg: ObjectiveConfig) -> float:

    mdd_abs = abs(float(metrics.get("mdd", float("inf"))))
    sharpe = float(metrics.get("sharpe", float("nan")))
    ttr = float(metrics.get("total_return_pct", float("nan")))
    vol = float(metrics.get("vol", float("nan")))


    if cfg.mdd_max and mdd_abs > float(cfg.mdd_max):
        return _bad_score(cfg.direction)
    
    if cfg.min_mdd and mdd_abs < float(cfg.min_mdd):
        return _bad_score(cfg.direction) 
    
    if cfg.min_sharpe and sharpe < float(cfg.min_sharpe):
        return _bad_score(cfg.direction)
    
    if cfg.min_total_return and ttr < float(cfg.min_total_return):
        return _bad_score(cfg.direction)
    
    if cfg.max_vol_annualized and vol > float(cfg.max_vol_annualized):
        return _bad_score(cfg.direction)
    
    if cfg.min_trades is not None:
        nb_trades = int(metrics.get("nb_trades", 0))
        if nb_trades < cfg.min_trades:
            return _bad_score(cfg.direction)
    
    weights = cfg.weights or {"sharpe": 1.0}

    s = 0.0
    for k, w in weights.items():
        s += float(metrics.get(k, 0.0)) * float(w)
    return s if cfg.direction == "maximize" else -s


def rank(results: List[Dict[str, Any]], cfg: ObjectiveConfig) -> pd.DataFrame:
    rows = []
    for r in results:
        m = r.get("metrics", {})
        s = compute_score(m, cfg)
        rows.append({"score": s, **m, "params": r.get("params"), "params_combo": r.get("params_combo")})
    df = pd.DataFrame(rows)
    asc = (cfg.direction != "maximize")
    df = df.sort_values("score", ascending=asc, ignore_index=True)
    return df



# def compute_score(metrics: Dict[str, float], cfg: ObjectiveConfig) -> float:
#     mdd_abs = abs(float(metrics.get("mdd", 0.0)))
#     if mdd_abs > cfg.mdd_max:
#         return -1e9 if cfg.direction == "maximize" else 1e9
#     if mdd_abs > cfg.mdd_max:
#         return -1e9 if cfg.direction == "maximize" else 1e9
    
#     weights = cfg.weights or {"sharpe": 1.0}

#     s = 0.0
#     for k, w in weights.items():
#         s += float(metrics.get(k, 0.0)) * float(w)
#     return s if cfg.direction == "maximize" else -s

