from typing import Any, Dict

from mvc_app.jobs.jobs_data import JobConfig
from mvc_app.usecases.profile_base.profile_services import get_profile
from mvc_core.optimize.calibration.calibration_services import run_walk_calibration_v2
from mvc_core.optimize.components.splitter.splitter_services import build_splits
from mvc_core.optimize.oos_reconstruction_services import (
    reconstruct_oos_equity_from_history,
    reconstruct_oos_equity_v2,
)
from mvc_core.optimize.wf_history.wf_history_services import (
    build_wf_calibration_run,
    extend_wf_calibration_run_with_new_splits,
    load_wf_calibration_run,
    save_wf_calibration_run,
)
from mvc_core.performances.metrics_by_split.split_stats_services import (
    compute_wf_window_stats,
)


def run_wf_full_calibration_job(job_cfg: JobConfig) -> Dict[str, Any]:
    """
    Job de calibration WF complète pour un use case donné.

    Étapes :
      - construit clock + price_series
      - construit StrategyCfg, CalibrationConfig, SplitConfig
      - build_splits + run_walk_calibration_v2
      - construit WFCalibrationRun + sauvegarde JSON
      - reconstruit l'OOS (equity, décisions, indicateur)
    """
    profile = get_profile(job_cfg.profile_name)

    if not profile.has_calibration:
        raise ValueError(
            f"Use case '{profile.name}' has no calibration (calib_builder/wf_json_path)."
        )

    # 1) Data + stratégie + calib + splits
    clock, price_series = profile.data_builder()
    base_strategy = profile.strategy_cfg_builder(clock, price_series)


    calib_cfg, split_cfg = profile.calib_builder()

    splits = build_splits(clock, split_cfg)

    # 2) Calibration walk-forward v2
    report = run_walk_calibration_v2(
        splits=splits,
        price_series=price_series,
        base_strategy=base_strategy,
        cfg=calib_cfg,
    )

    # 3) Artefact de calibration WF
    wf_run = build_wf_calibration_run(
        use_case_name=profile.name,
        run_id=job_cfg.run_id,
        split_config=split_cfg,
        search_space=calib_cfg.search_space,
        objective=calib_cfg.objective,
        splits=splits,
        report=report,
    )
    save_wf_calibration_run(wf_run, profile.wf_json_path)

    # 4) Reconstruction OOS "live" à partir du report
    oos = reconstruct_oos_equity_v2(
        report=report,
        splits=splits,
        price_series=price_series,
        instrument=base_strategy.instrument,
        base_strategy=base_strategy,
        cfg=calib_cfg,
        use_rank=1,
        build_indicator=True,
    )

    return {
        "wf_run": wf_run,
        "report": report,
        "oos": oos,
        "instrument": base_strategy.instrument,
        "wf_json_path": str(profile.wf_json_path),
    }


# ---------------------------------------------------------------------------
# Job 2 : update WF (extend + reconstruction OOS)
# ---------------------------------------------------------------------------


def run_wf_update_job(job_cfg: JobConfig) -> Dict[str, Any]:
    """
    Job d'update WF pour un use case :

      - charge clock + price_series + configs
      - charge WFCalibrationRun existant
      - étend WF si de nouveaux splits sont disponibles (calibration partielle)
      - sauvegarde le WF mis à jour si besoin
      - reconstruit l'OOS complète à partir de l'historique WF
    """
    profile = get_profile(job_cfg.profile_name)

    if not profile.has_calibration:
        raise ValueError(
            f"Use case '{profile.name}' has no calibration (calib_builder/wf_json_path)."
        )

    # 1) Data + stratégie + calib
    clock, price_series = profile.data_builder()
    base_strategy = profile.strategy_cfg_builder(clock, price_series)
    calib_cfg, split_cfg = profile.calib_builder()

    # 2) Charger l'artefact existant
    wf_run = load_wf_calibration_run(profile.wf_json_path)

    # 3) Étendre si de nouveaux splits sont possibles
    wf_run_extended = extend_wf_calibration_run_with_new_splits(
        wf_run=wf_run,
        clock=clock,
        price_series=price_series,
        base_strategy=base_strategy,
        cfg=calib_cfg,
        split_config=split_cfg,
    )

    if len(wf_run_extended.splits) != len(wf_run.splits):
        save_wf_calibration_run(wf_run_extended, profile.wf_json_path)
        wf_run = wf_run_extended

    # 4) Reconstruction OOS depuis l'historique WF
    oos = reconstruct_oos_equity_from_history(
        wf_run=wf_run,
        clock=clock,
        price_series=price_series,
        instrument=base_strategy.instrument,
        base_strategy=base_strategy,
        cfg=calib_cfg,
        split_config=split_cfg,
        build_indicator=True,
    )

    return {
        "wf_run": wf_run,
        "oos": oos,
        "instrument": base_strategy.instrument,
        "wf_json_path": str(profile.wf_json_path),
    }


# ---------------------------------------------------------------------------
# Job 3 : backtest view (OOS + stats par fenêtre)
# ---------------------------------------------------------------------------


def get_backtest_view(job_cfg: JobConfig) -> Dict[str, Any]:
    """
    Construit une vue complète du backtest OOS à partir d'un run WF existant.
    """
    profile = get_profile(job_cfg.profile_name)

    if not profile.has_calibration:
        raise ValueError(
            f"Use case '{profile.name}' has no calibration (calib_builder/wf_json_path)."
        )

    clock, price_series = profile.data_builder()
    base_strategy = profile.strategy_cfg_builder(clock, price_series)
    calib_cfg, split_cfg = profile.calib_builder()

    wf_run = load_wf_calibration_run(profile.wf_json_path)

    oos = reconstruct_oos_equity_from_history(
        wf_run=wf_run,
        clock=clock,
        price_series=price_series,
        instrument=base_strategy.instrument,
        base_strategy=base_strategy,
        cfg=calib_cfg,
        split_config=split_cfg,
        build_indicator=True,
    )
    equity_df = oos["equity_oos_df"]
    decisions = oos.get("decisions")

    split_stats = compute_wf_window_stats(
        wf_run=wf_run,
        equity_oos_df=equity_df,
        decisions=decisions,
    )

    return {
        "wf_run": wf_run,
        "oos": oos,
        "instrument": base_strategy.instrument,
        "wf_json_path": str(profile.wf_json_path),
        "splits_stats": split_stats,
        "price_series": price_series,
        "bench_key": calib_cfg.bench_key or profile.bench_key,
    }



