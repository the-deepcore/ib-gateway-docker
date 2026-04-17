
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from mvc_core.domain.clock.clock_data import Clock
from mvc_core.domain.enums import Action, Side
from mvc_core.optimize.calibration.calibration_data import CalibrationConfig, CalibrationReport
from mvc_core.performances.build_backtest_output import buy_and_hold_from_price
from mvc_core.strategies.components.features.feature_data import InputSpec
from mvc_core.strategies.components.features.feature_services import build_feature_set


def _derive_seed_from_decisions(decisions, instrument: str) -> Dict[str, Any]:
    """
    Déduit l'état final pour le signalizer (current_side + legs) à partir
    d'une liste de décisions ordonnées.
    """
    cur_side = None
    legs_long = 0
    legs_short = 0

    for s in (decisions or []):
        try:
            if getattr(s, "instrument", None) and instrument and s.instrument != instrument:
                continue
            action = getattr(s, "action", None)
            side = getattr(s, "side", None)
            meta = getattr(s, "meta", {}) or {}

            if action == Action.OPEN:
                if side == Side.LONG:
                    legs_before = int(meta.get("legs_before", 0) or 0)
                    legs_long = max(legs_long, legs_before + 1)
                    cur_side = Side.LONG
                    legs_short = 0
                elif side == Side.SHORT:
                    legs_before = int(meta.get("legs_before", 0) or 0)
                    legs_short = max(legs_short, legs_before + 1)
                    cur_side = Side.SHORT
                    legs_long = 0

            elif action == Action.CLOSE:
                if side == Side.LONG:
                    legs_long = 0
                    if cur_side == Side.LONG:
                        cur_side = None
                elif side == Side.SHORT:
                    legs_short = 0
                    if cur_side == Side.SHORT:
                        cur_side = None

        except Exception:
            continue

    if cur_side == Side.LONG:
        return {"current_side": Side.LONG, "legs": max(1, legs_long)}
    if cur_side == Side.SHORT:
        return {"current_side": Side.SHORT, "legs": max(1, legs_short)}
    return {"current_side": None, "legs": 0}


def _choose_combo(split_topk: List[Dict[str, Any]], rank: int = 1) -> Dict[str, Any]:
    if not split_topk:
        raise ValueError("split_topk is empty")
    row = split_topk[rank - 1] if rank - 1 < len(split_topk) else split_topk[0]
    # tolerate different key names
    return row.get("combo") or row.get("params_combo") or row.get("params") or {}



















from dataclasses import replace

from mvc_core.engine.run.run_data import RunCfg, RunResult
from mvc_core.engine.run.run_services import run_full
from mvc_core.strategies.build.build_services import build_runtime_strategy
from mvc_core.strategies.core.strategy_data import StrategyCfg


def infer_seed_from_portfolio(pf, instrument: str) -> Optional[Dict[str, Any]]:
    """
    Extrait un seed minimal à partir des positions ouvertes sur `instrument`.
    Reprend la logique V1.
    """
    if pf is None:
        return None

    open_positions = []
    for pos in getattr(pf, "positions", []):
        if getattr(pos, "instrument", None) != instrument:
            continue
        if getattr(pos, "status", None).name != "OPEN":
            continue
        open_positions.append(pos)

    if not open_positions:
        return None

    if len(open_positions) == 1:
        pos = open_positions[0]
        side = pos.side
        return {"current_side": side, "legs": 1}

    open_positions.sort(key=lambda p: p.entry_date)
    last = open_positions[-1]
    side = last.side
    return {"current_side": side, "legs": 1}



def _bench_key_from_strategy(strategy: StrategyCfg) -> Optional[str]:
    """
    Version V2 : récupère la clé future de bench depuis StrategyCfg.input_spec.base_keys.
    """
    try:
        input_spec = strategy.input_spec
        if hasattr(input_spec, "base_keys"):
            return input_spec.base_keys.get("fut_close")
    except Exception:
        pass
    return None


def compute_source_by_split_v2(
    *,
    test_clock: Clock,
    price_series: Dict[str, pd.Series],
    base_strategy: StrategyCfg,
    cfg: CalibrationConfig,
    combo: Dict[str, Any],
) -> Tuple[pd.Series, Optional[pd.Series], Optional[pd.Series]]:
    """
    Version V2 : même logique que compute_source_by_split mais avec StrategyCfg.

    - base_strategy : StrategyCfg 'de base'
    - cfg.bind_fn : doit être bind_params
    - combo : dict des hyperparamètres sélectionnés pour ce split
    """
    from mvc_core.domain.clock.clock_services import build_from_index

    overrides = cfg.bind_fn(combo, base_strategy)
    unknown = overrides.pop("__unknown_keys__", [])
    overrides.pop("__applied_keys__", None)

    if cfg.strict_params and unknown:
        raise KeyError(f"Unknown param keys in combo (compute_source_by_split_v2): {unknown}")

    strategy_cfg: StrategyCfg = overrides["strategy_cfg"]

    input_spec = strategy_cfg.input_spec
    src_cfg = strategy_cfg.source_cfg
    src_fn = strategy_cfg.components.source_fn
    if src_fn is None:
        raise ValueError("StrategyCfg.source_fn is None in compute_source_by_split_v2")

    # --- Determine if we need extended clock for lookback (KNN warm-up) ---
    lookback_bars = getattr(src_cfg, "lookback_bars", 0)
    feature_clock = test_clock

    if lookback_bars > 0:
        # Find a reference price series to get historical dates
        ref_key = next(iter(price_series.keys()), None)
        if ref_key is not None:
            ref_series = price_series[ref_key]
            # Get dates before test_clock start
            test_start = test_clock.index[0]
            hist_dates = ref_series.index[ref_series.index < test_start]
            if len(hist_dates) >= lookback_bars:
                # Take last lookback_bars dates before test_clock
                lookback_dates = hist_dates[-lookback_bars:]
                extended_index = lookback_dates.append(test_clock.index).unique().sort_values()
                feature_clock = build_from_index(extended_index)


    mode = getattr(src_cfg, "mode", None)
    if mode == "by_feature_key":
        fk = getattr(src_cfg, "feature_key", None)
        if fk is None or fk not in input_spec.recipes:
            raise KeyError("feature_key absent dans input_spec.recipes")

        mk = getattr(src_cfg, "modifier_key", None)
        wanted = {fk: input_spec.recipes[fk]}
        if mk and mk in input_spec.recipes:
            wanted[mk] = input_spec.recipes[mk]

        spec_min = InputSpec(
            base_keys=dict(input_spec.base_keys),
            recipes={fk: input_spec.recipes[fk]},
            extras=None,
        )
    else:
        spec_min = InputSpec(
            base_keys=dict(input_spec.base_keys),
            recipes={},
            extras=None,
        )

    feature_set = build_feature_set(feature_clock, price_series, spec_min, fill_method="dropna")

    src_out = src_fn(feature_set, src_cfg)
    z = src_out.scores if hasattr(src_out, "scores") else src_out
    z = z.astype(float)
    z.index = pd.to_datetime(z.index)

    # Slice back to test_clock if we used extended clock
    if lookback_bars > 0:
        z = z.loc[z.index.isin(test_clock.index)]

    th_up = combo.get("normalizer.high", combo.get("th_up"))
    th_dn = combo.get("normalizer.low",  combo.get("th_down"))
    if th_up is None or th_dn is None:
        # fallback: aller chercher dans la config du normalizer d'origine
        try:
            nc = strategy_cfg.normalizer_cfg
            if th_up is None:
                th_up = getattr(nc, "high", getattr(nc, "upper", None))
            if th_dn is None:
                th_dn = getattr(nc, "low", getattr(nc, "lower", None))
        except Exception:
            pass

    try:
        th_up = float(th_up) if th_up is not None else None
        th_dn = float(th_dn) if th_dn is not None else None
    except Exception:
        pass

    th_up_s = pd.Series(th_up, index=z.index) if th_up is not None else None
    th_dn_s = pd.Series(th_dn, index=z.index) if th_dn is not None else None

    return z, th_up_s, th_dn_s


def reconstruct_oos_equity_v2(
    *,
    report: CalibrationReport,
    splits: List[Dict[str, Clock]],
    price_series: Dict[str, pd.Series],
    instrument: str,
    base_strategy: StrategyCfg,
    cfg: CalibrationConfig,
    use_rank: int = 1,
    build_indicator: bool = False,
) -> Dict[str, Any]:
    """
    Version V2 de reconstruct_oos_equity :
      - base_strategy : StrategyCfg (au lieu de base: Dict)
      - utilise RunCfg + run_full + bind_params
    """

    per_split: List[Dict[str, Any]] = []
    equity_segments: List[pd.Series] = []
    bench_segments: List[pd.Series] = []

    decisions_all: List[Dict[str, Any]] = []

    fut_key = _bench_key_from_strategy(base_strategy)
    fut_price = price_series.get(fut_key) if fut_key else None

    indicator_series = None
    th_up_ser = None
    th_dn_ser = None

    # NB : on ne gère pas pour l'instant le walk_mode == "carry" au niveau des
    # portfolios (RunCfg ne supporte pas encore les seeds / carry_pf).
    # On conserve néanmoins la logique de concaténation de segments d'équity.

    carry_pf = None
    seed_in: Optional[Dict[str, Any]] = None

    for i, split in enumerate(report.splits, 1):
        # clock du split
        test_clock = splits[i - 1]["test"]

        # combo sélectionné sur ce split
        topk = split.get("topk", [])
        combo = _choose_combo(topk, rank=use_rank)

        # binding StrategyCfg
        overrides = cfg.bind_fn(combo, base_strategy)
        unknown = overrides.pop("__unknown_keys__", [])
        overrides.pop("__applied_keys__", None)
        if cfg.strict_params and unknown:
            raise KeyError(f"Unknown param keys in combo (reconstruct_oos_equity_v2): {unknown}")

        strategy_cfg: StrategyCfg = overrides["strategy_cfg"]


        # --- WALK-FORWARD : mode "carry" -> on injecte le seed dans la stratégie ---
        if cfg.walk_mode == "carry":
            # priorité à l'état réel du portefeuille
            seed_start = infer_seed_from_portfolio(carry_pf, instrument)
            if seed_start is None:
                seed_start = seed_in

            if seed_start is not None:
                # on travaille sur une copie des extras pour ne pas polluer base_strategy
                new_extras = dict(strategy_cfg.extras or {})
                new_extras["seed_state"] = seed_start
                strategy_cfg = replace(strategy_cfg, extras=new_extras)




        # build runtime strategy
        built = build_runtime_strategy(
            clock=test_clock,
            price_series=price_series,
            strategy_cfg=strategy_cfg,
        )

        # RunCfg + run_full : on garde keep_artifacts=True pour récupérer equity + décisions
        # propagate notional and display capital for bench sizing and rebasing
        strat_notional = None
        try:
            strat_notional = float(strategy_cfg.sizer_cfg.meta.get("notional_usd"))  # type: ignore[attr-defined]
        except Exception:
            strat_notional = None

        display_initial_value = strategy_cfg.extras.get("display_initial_value") if strategy_cfg.extras else None

        run_cfg = RunCfg(
            clock=test_clock,
            price_series=price_series,
            built_strat=built,
            bench_key=cfg.bench_key,
            initial_inv=cfg.initial_inv,
            tick_size=cfg.tick_size,
            keep_artifacts=True,
            tags={
                "split_idx": i,
                "display_initial_value": display_initial_value if display_initial_value is not None else cfg.initial_inv,
                "bench_notional": strat_notional,
            },
            initial_portfolio=(
                carry_pf if (cfg.walk_mode == "carry" and carry_pf is not None) else None
            ),
        )

        res: RunResult = run_full(run_cfg)
        eq_df = res.artifacts.equity_df

        # segments d'equity
        equity_segments.append(eq_df["TotalValue"])

        # segment buy & hold (utilise buy_and_hold_from_price pour calcul correct avec lots entiers)
        bench_key = cfg.bench_key or fut_key
        bench_notional = strat_notional if strat_notional is not None else cfg.initial_inv
        if bench_key is not None and bench_key in price_series:
            px = price_series[bench_key].astype(float)
            px_win = px.loc[px.index.intersection(test_clock.index)]
            if not px_win.empty:
                bh_seg = buy_and_hold_from_price(
                    bench_price=px_win,
                    clock_index=test_clock.index,
                    initial_inv=float(bench_notional),
                    bench_notional=float(bench_notional),
                    bench_key=bench_key,
                    start_date=str(px_win.index[0]),
                )
                if not bh_seg.empty:
                    bench_segments.append(bh_seg)

        # décisions
        decisions = res.artifacts.decisions
        if decisions is not None:
            if isinstance(decisions, list):
                decisions_all.extend(decisions)
            else:
                decisions_all.append(decisions)

        # mise à jour du seed et du portefeuille pour le mode "carry"
        if cfg.walk_mode == "carry":
            if decisions:
                seed_in = _derive_seed_from_decisions(decisions, instrument=instrument)
            # on récupère le portefeuille final pour l'utiliser comme seed du split suivant
            carry_pf = res.artifacts.portfolio


        # indicateur (zscore) + seuils, si demandé
        if build_indicator and combo:
            try:
                z, th_up_s, th_dn_s = compute_source_by_split_v2(
                    test_clock=test_clock,
                    price_series=price_series,
                    base_strategy=base_strategy,
                    cfg=cfg,
                    combo=combo,
                )
                indicator_series = z if indicator_series is None else pd.concat([indicator_series, z])
                if th_up_s is not None:
                    th_up_ser = th_up_s if th_up_ser is None else pd.concat([th_up_ser, th_up_s])
                if th_dn_s is not None:
                    th_dn_ser = th_dn_s if th_dn_ser is None else pd.concat([th_dn_ser, th_dn_s])
            except Exception:
                # on ne casse pas la reconstruction si l'indicateur plante
                pass

        per_split.append(
            {
                "split_idx": i,
                "combo": combo,
                "equity_df": eq_df,
            }
        )

    # ==== Reconstruction de l'équity OOS (TotalValue) =======================
    level = float(cfg.initial_inv)
    parts = []
    for seg in equity_segments:
        s = pd.Series(seg, dtype=float)
        s.index = pd.to_datetime(s.index)
        if getattr(s.index, "tz", None) is not None:
            s.index = s.index.tz_localize(None)
        s = s.sort_index().dropna()
        if s.empty:
            continue
        delta = s - float(s.iloc[0])
        s_add = delta + level
        parts.append(s_add)
        level = float(s_add.iloc[-1])

    if parts:
        eq_oos = pd.concat(parts, axis=0).sort_index()
        eq_oos.name = "TotalValue"
    else:
        eq_oos = pd.Series(dtype=float, name="TotalValue")

    equity_df = pd.DataFrame({"TotalValue": eq_oos})

    # ==== Reconstruction Buy & Hold OOS =====================================
    # Le benchmark est calculé sur toute la période OOS avec un achat unique au début
    if bench_segments:
        blevel = float(bench_notional if bench_notional is not None else cfg.initial_inv)
        bparts = []
        for seg in bench_segments:
            s = pd.Series(seg, dtype=float)
            s.index = pd.to_datetime(s.index)
            if getattr(s.index, "tz", None) is not None:
                s.index = s.index.tz_localize(None)
            s = s.sort_index().dropna()
            if s.empty:
                continue

            # Le segment est déjà en valeur absolue grâce à buy_and_hold_from_price
            # On calcule le delta par rapport au niveau initial du segment
            delta = s - float(s.iloc[0])
            s_add = delta + blevel
            bparts.append(s_add)
            blevel = float(s_add.iloc[-1])

        if bparts:
            bh_oos = pd.concat(bparts, axis=0).sort_index()
            bh_oos.name = "Buy&Hold"
            equity_df["Buy&Hold"] = bh_oos

    return {
        "equity_oos_df": equity_df,
        "price": (fut_price if fut_price is not None else pd.Series(dtype=float)),
        "decisions": decisions_all,
        "indicator": indicator_series,
        "thresholds": (
            {"up": th_up_ser, "down": th_dn_ser}
            if build_indicator
            else None
        ),
        "per_split": per_split,
        "initial_inv": float(cfg.initial_inv),
        "display_initial_value": run_cfg.tags.get("display_initial_value") if run_cfg.tags else None,
        "bench_notional": bench_notional if bench_notional is not None else cfg.initial_inv,
    }


from mvc_core.domain.clock.clock_services import _to_naive, _to_tz_aware
from mvc_core.performances.build_backtest_output import crop_equity_series


def crop_oos_output(
    oos: Dict[str, Any],
    start_date: str,
    end_date: str,
    initial_value: Optional[float] = None,
    display_initial_value: Optional[float] = None,
) -> Dict[str, Any]:

    # need naive and tz-aware Timestamps depending on the index to crop
    # One should look for standardization of Timestamps indices...
    if start_date is None:
        start_date = oos["price"].index[0]
    if end_date is None:
        end_date = oos["price"].index[-1]
    start_date_tz_aware, end_date_tz_aware = _to_tz_aware(start_date), _to_tz_aware(end_date)


    # price index is tz-aware (UTC)
    price = oos['price'].loc[start_date_tz_aware:end_date_tz_aware]

    # crop function take non tz-aware Timestamps (naive Timestamp)
    # display_initial_value overrides everything (e.g., show equity starting at 200m while trading base is 30m)
    init_val = None
    if display_initial_value is not None:
        init_val = float(display_initial_value)
    elif initial_value is not None:
        init_val = float(initial_value)
    else:
        iv = float(oos.get("initial_inv", 0.0) or 0.0)
        init_val = iv if iv > 0 else None

    equity_df = crop_equity_series(
        oos["equity_oos_df"],
        start_date,
        end_date,
        initial_value=init_val,
    )

    # decisions is a list of dict, each dict is a decision (signal) and has a 'date' key (pd.Timestamp)
    decisions = [dec for dec in oos.get("decisions") if _to_naive(dec["date"]) >= _to_naive(pd.to_datetime(start_date)) and _to_naive(dec["date"]) <= _to_naive(pd.to_datetime(end_date))]

    # indicator index is tz-aware (UTC)
    indicator = oos.get("indicator").loc[start_date_tz_aware:end_date_tz_aware] if oos.get("indicator") is not None else None

    # thresholds indices are tz-aware (UTC)

    thresholds = oos.get("thresholds")
    if thresholds is not None:
        for thresh in thresholds:
            if thresholds[thresh] is not None:
                thresholds[thresh] = thresholds[thresh].loc[start_date_tz_aware:end_date_tz_aware]

    return {
        "equity_oos_df": equity_df,
        "price": price,
        "decisions": decisions,
        "indicator": indicator,
        "thresholds": thresholds,
    }


from typing import Any, Dict, List

import pandas as pd

from mvc_core.domain.clock.clock_data import Clock
from mvc_core.optimize.calibration.calibration_data import CalibrationConfig, CalibrationReport
from mvc_core.optimize.components.splitter.splitter_data import SplitConfig
from mvc_core.optimize.components.splitter.splitter_services import build_splits
from mvc_core.optimize.wf_history.wf_history_data import SplitCalibrationSnapshot, WFCalibrationRun
from mvc_core.strategies.core.strategy_data import StrategyCfg


def _build_report_from_history(run: WFCalibrationRun) -> CalibrationReport:
    """
    Adapte un WFCalibrationRun en un CalibrationReport artificiel,
    compatible avec reconstruct_oos_equity_v2.

    Hypothèse : pour chaque split on n'a qu'un seul combo (best_params).
    On construit donc un 'topk' de taille 1.
    """
    splits_report: List[Dict[str, Any]] = []

    # on s'assure que les splits sont dans l'ordre (1,2,3,...)
    snapshots: List[SplitCalibrationSnapshot] = sorted(
        run.splits,
        key=lambda sp: sp.split_id,
    )

    for snap in snapshots:
        metrics = dict(snap.metrics or {})

        best_entry = {
            "combo": dict(snap.best_params),
            "score": float(snap.best_score),
            "metrics": metrics,
        }

        split_entry: Dict[str, Any] = {
            "best": best_entry,
            "topk": [best_entry],  # top_k = 1
        }
        splits_report.append(split_entry)

    # summary : on peut réutiliser ce qui a été stocké dans WFCalibrationRun
    summary = dict(run.summary or {})

    return CalibrationReport(
        splits=splits_report,
        summary=summary,
    )


def reconstruct_oos_equity_from_history(
    *,
    wf_run: WFCalibrationRun,
    clock: Clock,
    price_series: Dict[str, pd.Series],
    instrument: str,
    base_strategy: StrategyCfg,
    cfg: CalibrationConfig,
    split_config: SplitConfig,
    build_indicator: bool = True,
) -> Dict[str, Any]:
    """
    Pont entre l'artefact persistant WFCalibrationRun et le moteur existant
    reconstruct_oos_equity_v2.

    Pipeline :
      - on reconstruit les splits à partir de clock + split_config
      - on adapte WFCalibrationRun -> CalibrationReport (compatible v2)
      - on délègue à reconstruct_oos_equity_v2 (même cœur que la calib live)

    => zéro duplication de logique de reconstruction.
    """

    # 1) Reconstruire les splits Clock à partir du clock courant
    splits = build_splits(clock, split_config)

    # 2) Construire un CalibrationReport artificiel à partir de l'historique
    report = _build_report_from_history(wf_run)

    # 2b) Limiter les splits du rapport à ceux disponibles dans le clock actuel
    n_available = len(splits)
    if len(report.splits) > n_available:
        report = CalibrationReport(
            splits=report.splits[:n_available],
            summary=report.summary,
        )

    # 3) Déléguer au moteur standard
    #    (on fixe use_rank=1 puisque WFCalibrationRun ne stocke que le "best")
    return reconstruct_oos_equity_v2(
        report=report,
        splits=splits,
        price_series=price_series,
        instrument=instrument,
        base_strategy=base_strategy,
        cfg=cfg,
        use_rank=1,
        build_indicator=build_indicator,
    )
