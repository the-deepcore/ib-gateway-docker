from dataclasses import asdict, is_dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import pandas as pd

from mvc_core.domain.clock.clock_data import Clock
from mvc_core.optimize.calibration.calibration_data import CalibrationReport
from mvc_core.optimize.components.objective.objective_data import ObjectiveConfig
from mvc_core.optimize.components.search_space.search_space_data import SearchSpace
from mvc_core.optimize.components.splitter.splitter_data import SplitConfig

from .wf_history_data import SplitCalibrationSnapshot, WFCalibrationRun

# ---------------------------------------------------------------------------
# Helpers génériques de (dé)sérialisation
# ---------------------------------------------------------------------------

def _to_plain(obj: Any) -> Any:
    """
    Convertit récursivement un objet (dataclass, objet classique, list, dict)
    en structure JSON-serializable (dict/list/valeurs scalaires).

    On s'en sert pour split_config, search_space, objective_cfg.
    """
    if is_dataclass(obj):
        return asdict(obj)

    if isinstance(obj, dict):
        return {k: _to_plain(v) for k, v in obj.items()}

    if isinstance(obj, (list, tuple)):
        return [_to_plain(v) for v in obj]

    # objet "classique" avec __dict__
    if hasattr(obj, "__dict__"):
        return {
            k: _to_plain(v)
            for k, v in obj.__dict__.items()
            if not k.startswith("_")
        }

    # type primitif (str, int, float, bool, None, etc.)
    return obj


def _serialize_summary(summary: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transforme le summary de CalibrationReport en quelque chose de serialisable.

    On gère en particulier "oos_table" qui est un DataFrame dans la V2.
    """
    if summary is None:
        return {}

    out: Dict[str, Any] = dict(summary)

    oos_table = out.get("oos_table")
    if isinstance(oos_table, pd.DataFrame):
        # on le stocke en list[dict] (orient="records")
        out["oos_table"] = oos_table.to_dict(orient="records")

    return out


# ---------------------------------------------------------------------------
# Construction de l'artefact WF à partir de la calibration V2
# ---------------------------------------------------------------------------

def build_wf_calibration_run(
    *,
    use_case_name: str,
    run_id: Optional[str],
    split_config: SplitConfig,
    search_space: SearchSpace,
    objective: ObjectiveConfig,
    splits: List[Dict[str, Clock]],
    report: CalibrationReport,
) -> WFCalibrationRun:
    """
    Construit un WFCalibrationRun à partir :

      - du nom de use-case (ex: "wf_sb11")
      - d'un run_id (ou None pour auto-générer un timestamp)
      - de SplitConfig / SearchSpace / ObjectiveConfig
      - de la liste des splits (train/test clocks)
      - du CalibrationReport résultant de run_walk_calibration_v2

    Hypothèse : len(splits) == len(report.splits)
    """
    if run_id is None:
        run_id = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    created_at = datetime.utcnow().isoformat()

    split_cfg_dict = _to_plain(split_config)
    search_space_dict = _to_plain(search_space)
    objective_dict = _to_plain(objective)

    snapshots: List[SplitCalibrationSnapshot] = []

    for idx, (sp_clocks, sp_res) in enumerate(zip(splits, report.splits), start=1):
        train_clock: Clock = sp_clocks["train"]
        test_clock: Clock = sp_clocks["test"]

        train_idx = train_clock.index
        test_idx = test_clock.index

        # On récupère "best" tel que construit dans calibration_services._train_and_select_v2
        best = sp_res["best"]
        metrics_raw = best.get("metrics", {}) or {}
        # combo "canonique" = combo si dispo, sinon params
        params = best.get("combo") or best.get("params") or {}
        score = float(best.get("score", 0.0))

        # on nettoie les métriques en float purs
        metrics = {k: float(v) for k, v in metrics_raw.items()}

        snapshot = SplitCalibrationSnapshot(
            split_id=idx,
            train_start=train_idx[0].isoformat(),
            train_end=train_idx[-1].isoformat(),
            test_start=test_idx[0].isoformat(),
            test_end=test_idx[-1].isoformat(),
            best_params=params,
            best_score=score,
            metrics=metrics,
        )
        snapshots.append(snapshot)

    summary = _serialize_summary(report.summary)

    return WFCalibrationRun(
        use_case_name=use_case_name,
        run_id=run_id,
        created_at=created_at,
        split_config=split_cfg_dict,
        search_space_cfg=search_space_dict,
        objective_cfg=objective_dict,
        splits=snapshots,
        summary=summary,
    )


# ---------------------------------------------------------------------------
# Sauvegarde / chargement JSON
# ---------------------------------------------------------------------------

def wf_calibration_run_to_dict(run: WFCalibrationRun) -> Dict[str, Any]:
    """
    Conversion dataclass -> dict JSON-serializable.

    Format : { "1": {train_start, train_end, test_start, test_end, best_params}, ... }
    """
    result: Dict[str, Any] = {}
    for snap in run.splits:
        result[str(snap.split_id)] = {
            "train_start": snap.train_start,
            "train_end": snap.train_end,
            "test_start": snap.test_start,
            "test_end": snap.test_end,
            "best_params": dict(snap.best_params),
        }
    return result


def wf_calibration_run_from_dict(data: Dict[str, Any]) -> WFCalibrationRun:
    """
    Reconstruction d'un WFCalibrationRun à partir d'un dict (json.load(...)).

    Format attendu : { "1": {train_start, train_end, test_start, test_end, best_params}, ... }
    """
    splits: List[SplitCalibrationSnapshot] = []
    for split_id_str, split_data in sorted(data.items(), key=lambda x: int(x[0])):
        splits.append(SplitCalibrationSnapshot(
            split_id=int(split_id_str),
            train_start=split_data["train_start"],
            train_end=split_data["train_end"],
            test_start=split_data["test_start"],
            test_end=split_data["test_end"],
            best_params=split_data["best_params"],
            best_score=0.0,
            metrics={},
        ))

    return WFCalibrationRun(
        use_case_name="",
        run_id="",
        created_at="",
        split_config={},
        search_space_cfg={},
        objective_cfg={},
        splits=splits,
        summary={},
    )


def save_wf_calibration_run(run: WFCalibrationRun, path: Union[str, Path]) -> None:
    """
    Sauvegarde l'artefact JSON sur S3 (bucket thedeepcore/calibrations/).

    `path` est utilisé uniquement pour en extraire le nom de fichier (ex: wf_sb11_calibration.json).
    """
    from mvc_core.adapters.s3_AWS.s3_services import upload_json

    key = Path(path).name
    data = wf_calibration_run_to_dict(run)
    upload_json(data, key)


def load_wf_calibration_run(path: Union[str, Path]) -> WFCalibrationRun:
    """
    Charge un artefact WFCalibrationRun depuis S3 (bucket thedeepcore/calibrations/).
    """
    from mvc_core.adapters.s3_AWS.s3_services import download_json

    key = Path(path).name
    data = download_json(key)
    return wf_calibration_run_from_dict(data)




# ---------------------------------------------------------------------------
# Helpers pour exploiter l'artefact WF
# ---------------------------------------------------------------------------

from typing import Any, Dict, List

import pandas as pd

from mvc_core.optimize.calibration.calibration_data import CalibrationConfig, CalibrationReport
from mvc_core.optimize.calibration.calibration_services import (
    _train_and_select_v2,
    summarize_report,
)
from mvc_core.optimize.components.splitter.splitter_services import build_splits
from mvc_core.strategies.core.strategy_data import StrategyCfg

from .wf_history_data import SplitCalibrationSnapshot


def extend_wf_calibration_run_with_new_splits(
    *,
    wf_run: WFCalibrationRun,
    clock: Clock,
    price_series: Dict[str, pd.Series],
    base_strategy: StrategyCfg,
    cfg: CalibrationConfig,
    split_config: SplitConfig,
) -> WFCalibrationRun:
    """
    Étend un WFCalibrationRun existant si de nouveaux splits sont disponibles
    avec le clock courant.

    - Recalcule les splits théoriques à partir du SplitConfig fourni.
    - Si len(splits_nouveaux) == len(wf_run.splits), rien à faire -> on renvoie wf_run.
    - Si len(splits_nouveaux) > len(wf_run.splits), on calibre uniquement
      les splits manquants, on construit les nouveaux snapshots et on
      recalcule le summary.

    Retourne un NOUVEL objet WFCalibrationRun (l'ancien n'est pas muté).
    """

    # 1) Recalculer les splits théoriques à partir du clock actuel
    splits_all = build_splits(clock, split_config)

    prev_n = len(wf_run.splits)
    new_n = len(splits_all)

    # Aucun nouveau split -> WFRun inchangé
    if new_n <= prev_n:
        return wf_run

    # 2) Construire un CalibrationReport complet pour recalculer le summary
    rep = CalibrationReport()

    # D'abord, injecter les splits déjà calibrés (à partir des snapshots)
    for snap in wf_run.splits:
        m = snap.metrics or {}
        metrics = {
            "sharpe": float(m.get("sharpe", 0.0)),
            "mdd": float(m.get("mdd", 0.0)),
            "cagr": float(m.get("cagr", 0.0)),
            "vol": float(m.get("vol", 0.0)),
            "total_return_pct": float(m.get("total_return_pct", 0.0)),
        }
        best = {
            "score": float(snap.best_score),
            "metrics": metrics,
        }
        rep.splits.append({"best": best})

    # 3) Calibrer les nouveaux splits uniquement
    new_snapshots: List[SplitCalibrationSnapshot] = []


    for idx in range(prev_n, new_n):
        sp = splits_all[idx]
        train_clock = sp["train"]
        test_clock = sp["test"]

        # calibration V2 sur ce split
        res = _train_and_select_v2(
            train_clock=train_clock,
            test_clock=test_clock,
            price_series=price_series,
            base_strategy=base_strategy,
            cfg=cfg,

        )

        train_idx = train_clock.index
        test_idx = test_clock.index

        best = res["best"]
        metrics_raw = best.get("metrics", {}) or {}
        params = best.get("combo") or best.get("params") or {}
        score = float(best.get("score", 0.0))
        metrics = {k: float(v) for k, v in metrics_raw.items()}

        snap = SplitCalibrationSnapshot(
            split_id=idx + 1,
            train_start=train_idx[0].isoformat(),
            train_end=train_idx[-1].isoformat(),
            test_start=test_idx[0].isoformat(),
            test_end=test_idx[-1].isoformat(),
            best_params=params,
            best_score=score,
            metrics=metrics,
        )
        new_snapshots.append(snap)

        rep.splits.append(
            {
                "best": {
                    "score": score,
                    "metrics": metrics,
                }
            }
        )

    # 4) Recalculer le summary global (tous les splits)
    rep = summarize_report(rep)
    new_summary = _serialize_summary(rep.summary)

    # 5) Construire le nouvel artefact WF
    all_snaps = list(wf_run.splits) + new_snapshots

    return WFCalibrationRun(
        use_case_name=wf_run.use_case_name,
        run_id=wf_run.run_id,
        created_at=wf_run.created_at,
        split_config=wf_run.split_config,
        search_space_cfg=wf_run.search_space_cfg,
        objective_cfg=wf_run.objective_cfg,
        splits=all_snaps,
        summary=new_summary,
    )
