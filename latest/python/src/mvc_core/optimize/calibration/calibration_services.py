from __future__ import annotations

from typing import Any, Dict, Iterable, List

import pandas as pd
from tqdm import tqdm

from mvc_core.domain.clock.clock_data import Clock
from mvc_core.optimize.components.objective.objective_services import compute_score, rank
from mvc_core.optimize.components.search_space.search_space_data import SearchSpace
from mvc_core.optimize.components.search_space.search_space_services import (
    iter_grid,
    iter_random,
    suggest_from_space,
)

from .calibration_data import CalibrationConfig, CalibrationReport


def _iter_space(space: SearchSpace) -> Iterable[Dict[str, Any]]:
    if space.engine == "grid":
        return iter_grid(space)
    if space.engine == "random":
        return iter_random(space)
    raise ValueError("SearchSpace.engine must be 'grid' or 'random'")

def summarize_report(rep: CalibrationReport) -> CalibrationReport:
    rows = []
    for i, s in enumerate(rep.splits, 1):
        b = s["best"]
        m = b["metrics"]
        rows.append({
            "split": i,
            "score": float(b["score"]),
            "sharpe": float(m["sharpe"]),
            "mdd": float(m["mdd"]),
            "cagr": float(m["cagr"]),
            "vol": float(m["vol"]),
            "total_return_pct": float(m["total_return_pct"])
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        rep.summary = {
            "oos_table": df,
            "oos_mean": df[["sharpe","mdd","cagr","vol", "total_return_pct"]].mean().to_dict(),
            "oos_median": df[["sharpe","mdd","cagr","vol", "total_return_pct"]].median().to_dict(),
        }
    else:
        rep.summary = {"oos_table": pd.DataFrame(), "oos_mean": {}, "oos_median": {}}
    return rep



from mvc_core.engine.run.run_data import RunCfg, RunResult
from mvc_core.engine.run.run_services import run_full
from mvc_core.strategies.build.build_services import build_runtime_strategy
from mvc_core.strategies.core.strategy_data import StrategyCfg


def _run_one_combo_on_clock(
    *,
    clock: Clock,
    price_series: Dict[str, pd.Series],
    strategy_cfg: StrategyCfg,
    cfg: CalibrationConfig,
    keep_artifacts: bool,
) -> Dict[str, Any]:

    built = build_runtime_strategy(clock=clock, price_series=price_series, strategy_cfg=strategy_cfg)


    # propagate notional (for bench sizing) and display capital (for rebasing plots)
    strat_notional = None
    try:
        strat_notional = float(strategy_cfg.sizer_cfg.meta.get("notional_usd"))  # type: ignore[attr-defined]
    except Exception:
        strat_notional = None

    display_initial_value = strategy_cfg.extras.get("display_initial_value") if strategy_cfg.extras else None

    run_cfg = RunCfg(
        clock=clock,
        price_series=price_series,
        built_strat=built,
        bench_key=cfg.bench_key,
        initial_inv=cfg.initial_inv,
        tick_size=cfg.tick_size,
        keep_artifacts=keep_artifacts or (cfg.walk_mode == "carry"),
        tags={
            "display_initial_value": display_initial_value if display_initial_value is not None else cfg.initial_inv,
            "bench_notional": strat_notional,
        },
    )

    res: RunResult = run_full(run_cfg)

    metrics = {
        "sharpe": float(res.metrics.sharpe),
        "mdd": float(res.metrics.mdd),
        "cagr": float(res.metrics.cagr),
        "vol": float(res.metrics.vol),
        "total_return_pct": float(res.metrics.total_return_pct),
    }

    out: Dict[str, Any] = {
        "metrics": metrics,
    }

    if keep_artifacts or cfg.walk_mode == "carry":
        out["equity_df"] = res.artifacts.equity_df
        out["decisions"] = res.artifacts.decisions
        out["portfolio"] = res.artifacts.portfolio

    return out


def _train_and_select_v2(
    *,
    train_clock: Clock,
    test_clock: Clock,
    price_series: Dict[str, pd.Series],
    base_strategy: StrategyCfg,
    cfg: CalibrationConfig,
) -> Dict[str, Any]:


    # ------------------- TRAIN : recherche sur train_clock -----------------
    results_train: List[Dict[str, Any]] = []

    # --- moteur d'exploration ---
    if cfg.search_space.engine == "optuna":
        import optuna
        from optuna.samplers import TPESampler

        n_trials = int(getattr(cfg.search_space, "n_trials", 50) or 50)
        seed = int(getattr(cfg.search_space, "seed", 42) or 42)
        direction = cfg.objective.direction  # "maximize" | "minimize"

        study = optuna.create_study(
            direction=direction,
            sampler=TPESampler(seed=seed),
        )

        def _objective(trial) -> float:
            # 1) proposer un combo
            combo = suggest_from_space(trial, cfg.search_space)

            # 2) binding -> StrategyCfg
            overrides = cfg.bind_fn(combo, base_strategy)

            unknown = overrides.pop("__unknown_keys__", [])
            overrides.pop("__applied_keys__", None)
            if cfg.strict_params and unknown:
                raise KeyError(f"Unknown param keys in combo: {unknown}")

            strategy_cfg = overrides["strategy_cfg"]



            # 3) run train
            r = _run_one_combo_on_clock(
                clock=train_clock,
                price_series=price_series,
                strategy_cfg=strategy_cfg,
                cfg=cfg,
                keep_artifacts=False,
            )

            r["params"] = combo
            r["params_combo"] = combo

            results_train.append(r)

            score = compute_score(r.get("metrics", {}), cfg.objective)
            return float(score)

        study.optimize(_objective, n_trials=n_trials, n_jobs=cfg.n_jobs)

    else:
        # chemins grid / random
        combos = list(_iter_space(cfg.search_space))
        
        # Paralléliser si n_jobs > 1
        if cfg.n_jobs > 1:
            from joblib import Parallel, delayed
            
            def _eval_one_combo(combo):
                overrides = cfg.bind_fn(combo, base_strategy)
                unknown = overrides.pop("__unknown_keys__", [])
                overrides.pop("__applied_keys__", None)
                if cfg.strict_params and unknown:
                    raise KeyError(f"Unknown param keys in combo: {unknown}")

                strategy_cfg = overrides["strategy_cfg"]
                
                r = _run_one_combo_on_clock(
                    clock=train_clock,
                    price_series=price_series,
                    strategy_cfg=strategy_cfg,
                    cfg=cfg,
                    keep_artifacts=False,
                )
                
                r["params"] = combo
                r["params_combo"] = combo
                return r
            

            results_train = Parallel(
                n_jobs=cfg.n_jobs, 
                backend='loky', 
                verbose=10,
                batch_size=5
                # batch_size='auto'

            )(
                delayed(_eval_one_combo)(combo) for combo in combos
            )
        
        else:
            # Séquentiel (comportement actuel)
            for combo in combos:
                overrides = cfg.bind_fn(combo, base_strategy)
                unknown = overrides.pop("__unknown_keys__", [])
                overrides.pop("__applied_keys__", None)
                if cfg.strict_params and unknown:
                    raise KeyError(f"Unknown param keys in combo: {unknown}")

                strategy_cfg = overrides["strategy_cfg"]

                r = _run_one_combo_on_clock(
                    clock=train_clock,
                    price_series=price_series,
                    strategy_cfg=strategy_cfg,
                    cfg=cfg,
                    keep_artifacts=False,
                )

                r["params"] = combo
                r["params_combo"] = combo

                results_train.append(r)

    # ------------------- RANK TRAIN ---------------------------------------
    lb_train = rank(results_train, cfg.objective)

    # ------------------- TEST : top-k sur test_clock ----------------------
    top = lb_train.head(cfg.top_k)

    results_test: List[Dict[str, Any]] = []

    # Paralléliser la phase test si n_jobs > 1
    if cfg.n_jobs > 1:
        from joblib import Parallel, delayed
        
        def _eval_test_combo(row):
            params = row["params"]
            match = next((rt for rt in results_train if rt["params"] == params), None)
            combo = match.get("params_combo", {}) if match else {}
            
            overrides = cfg.bind_fn(combo, base_strategy)
            unknown = overrides.pop("__unknown_keys__", [])
            overrides.pop("__applied_keys__", None)
            if cfg.strict_params and unknown:
                raise KeyError(f"Unknown param keys in combo (OOS): {unknown}")
            
            strategy_cfg = overrides["strategy_cfg"]
            
            r = _run_one_combo_on_clock(
                clock=test_clock,
                price_series=price_series,
                strategy_cfg=strategy_cfg,
                cfg=cfg,
                keep_artifacts=cfg.keep_artifacts,
            )
            
            r["params"] = combo
            r["params_combo"] = combo
            return r
        
        top_rows = [row for _, row in top.iterrows()]
        results_test = Parallel(n_jobs=cfg.n_jobs, backend='loky', verbose=0)(
            delayed(_eval_test_combo)(row) for row in top_rows
        )
    
    else:
        # Séquentiel
        for _, row in top.iterrows():
            params = row["params"]
            match = next((rt for rt in results_train if rt["params"] == params), None)
            combo = match.get("params_combo", {}) if match else {}
            
            overrides = cfg.bind_fn(combo, base_strategy)
            unknown = overrides.pop("__unknown_keys__", [])
            overrides.pop("__applied_keys__", None)
            if cfg.strict_params and unknown:
                raise KeyError(f"Unknown param keys in combo (OOS): {unknown}")
            
            strategy_cfg = overrides["strategy_cfg"]
            
            r = _run_one_combo_on_clock(
                clock=test_clock,
                price_series=price_series,
                strategy_cfg=strategy_cfg,
                cfg=cfg,
                keep_artifacts=cfg.keep_artifacts,
            )
            
            r["params"] = combo
            r["params_combo"] = combo
            results_test.append(r)

    lb_test = rank(results_test, cfg.objective)


    # ------------------- BEST + TOPK --------------------------------------

    topk_rows = lb_train.head(cfg.top_k)


    topk = []
    for _, row in topk_rows.iterrows():
        topk.append({
            "score": float(row["score"]),
            "metrics": {
                k: float(row[k])
                for k in ("sharpe", "mdd", "cagr", "vol", "total_return_pct")
                if k in row
            },
            "params": row.get("params"),
            "combo": row.get("params_combo"),
        })

    best_row = lb_train.iloc[0]


    best = {
        "metrics": dict(best_row[["sharpe", "mdd", "cagr", "vol", "total_return_pct"]]),
        "score": float(best_row["score"]),
        "params": best_row["params"],
        "combo": best_row.get("params_combo", None),
    }

    # récupérer equity/decisions de l’exécution correspondante

    best_exec = results_train[lb_train.index[0]]

    if cfg.keep_artifacts or cfg.walk_mode == "carry":
        best["equity_df"] = best_exec.get("equity_df")
        best["decisions"] = best_exec.get("decisions")

    return {
        "lb_train": lb_train,
        "lb_test": lb_test,
        "best": best,
        "topk": topk,
    }



def run_walk_calibration_v2(
    *,
    splits: List[Dict[str, Clock]],
    price_series: Dict[str, pd.Series],
    base_strategy: StrategyCfg,
    cfg: CalibrationConfig,
) -> CalibrationReport:
    """
    Version V2 de run_walk_calibration :
      - base_strategy: StrategyCfg
      - utilise _train_and_select_v2
      - retourne un CalibrationReport avec summary via summarize_report
    """
    rep = CalibrationReport()


    for sp in tqdm(splits):
        res = _train_and_select_v2(
            train_clock=sp["train"],
            test_clock=sp["test"],
            price_series=price_series,
            base_strategy=base_strategy,
            cfg=cfg,
        )

        rep.splits.append(res)

    return summarize_report(rep)
