
from typing import Any, Dict, List, Optional

import pandas as pd

from mvc_core.domain.market.contract_specs import resolve_contract_spec
from mvc_core.performances.metrics_services import (
    annualized_volatility,
    cagr,
    max_drawdown,
    sharpe_ratio,
    total_return_pct,
)


def _normalize_timestamp(ts) -> pd.Timestamp:
    ts = pd.Timestamp(ts)
    if ts.tzinfo is not None:
        ts = ts.tz_localize(None)
    return ts


def extract_position_series_from_decisions(
    decisions: List[Dict[str, Any]],
    clock_index: pd.DatetimeIndex,
    instrument: Optional[str] = None,
    debug: bool = False,
) -> pd.Series:

    if not decisions:
        if debug:
            print("[DEBUG] No decisions provided")
        return pd.Series(0, index=clock_index, name="position")
    
    if debug:
        print(f"[DEBUG] Processing {len(decisions)} decisions")
        print(f"[DEBUG] First decision: {decisions[0]}")
        print(f"[DEBUG] Last decision: {decisions[-1]}")
    

    position_by_date: Dict[str, int] = {}  # date string -> position
    current_position = 0
    
    for dec in decisions:
        action = str(dec.get("action", "")).upper()
        instr = dec.get("instrument")
        side = str(dec.get("side", "")).lower()
        raw_date = dec.get("date")
        

        if instrument and instr != instrument:
            continue
        

        ts = _normalize_timestamp(raw_date)
        date_str = ts.strftime("%Y-%m-%d")
        
        if action.startswith("OPEN"):
            if side == "long":
                current_position = 1
            elif side == "short":
                current_position = -1
            if debug and current_position != 0:
                print(f"[DEBUG] {date_str}: OPEN {side} -> position={current_position}")
        elif action == "CLOSE":
            if debug:
                print(f"[DEBUG] {date_str}: CLOSE {side} -> position=0")
            current_position = 0
        
        position_by_date[date_str] = current_position
    
    if debug:
        print(f"[DEBUG] Found {len(position_by_date)} unique dates with position changes")
        non_zero = sum(1 for v in position_by_date.values() if v != 0)
        print(f"[DEBUG] Non-zero positions: {non_zero}")
    

    clock_naive = clock_index.tz_localize(None) if clock_index.tz is not None else clock_index
    

    position_series = pd.Series(0, index=clock_naive, name="position", dtype=int)
    

    if position_by_date:

        change_dates = [pd.Timestamp(d) for d in sorted(position_by_date.keys())]
        change_values = [position_by_date[d] for d in sorted(position_by_date.keys())]
        

        changes = pd.Series(change_values, index=change_dates, dtype=int)
        

        combined_idx = changes.index.union(clock_naive)
        changes_reindexed = changes.reindex(combined_idx).ffill().fillna(0).astype(int)
        

        position_series = changes_reindexed.reindex(clock_naive).fillna(0).astype(int)
        position_series.name = "position"
    
    return position_series


def extract_position_series(job_cfg, debug: bool = False) -> pd.Series:


    from mvc_app.usecases.profile_base.profile_services import get_profile
    from mvc_core.optimize.oos_reconstruction_services import reconstruct_oos_equity_from_history
    from mvc_core.optimize.wf_history.wf_history_services import load_wf_calibration_run
    
    profile = get_profile(job_cfg.profile_name)
    
    if not profile.has_calibration:
        raise ValueError(f"Profile '{profile.name}' has no calibration.")
    
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
        build_indicator=False,
    )
    
    decisions = oos.get("decisions", [])
    
    if debug:
        print(f"[DEBUG] Profile '{job_cfg.profile_name}' returned {len(decisions)} decisions")
    
    return extract_position_series_from_decisions(
        decisions=decisions,
        clock_index=clock.index,
        instrument=base_strategy.instrument,
        debug=debug,
    )


def run_backtest_from_positions(
    position_series: pd.Series,
    price_series: pd.Series,
    instrument: str,
    initial_inv: float = 100_000.0,
    threshold: int = 1,
    fixed_notional: Optional[float] = None,
    debug: bool = False,
) -> Dict[str, Any]:

    def _normalize_index(idx: pd.DatetimeIndex) -> pd.DatetimeIndex:
        if idx.tz is not None:
            return idx.tz_localize(None)
        return idx
    
    pos_idx = _normalize_index(position_series.index)
    px_idx = _normalize_index(price_series.index)
    

    pos = position_series.copy()
    pos.index = pos_idx
    
    px = price_series.copy()
    px.index = px_idx
    

    common_idx = pos.index.intersection(px.index)
    
    if debug:
        print(f"[DEBUG] Position series: {len(pos)} dates, index type: {type(pos.index)}")
        print(f"[DEBUG] Price series: {len(px)} dates, index type: {type(px.index)}")
        print(f"[DEBUG] Common index: {len(common_idx)} dates")
        if len(common_idx) > 0:
            print(f"[DEBUG] Common range: {common_idx[0]} to {common_idx[-1]}")
    
    if len(common_idx) == 0:
        raise ValueError("No common dates between position_series and price_series")
    
    pos = pos.reindex(common_idx).fillna(0).astype(int)
    px = px.reindex(common_idx).ffill()
    

    effective_pos = pd.Series(0, index=common_idx, dtype=int)
    effective_pos[pos >= threshold] = 1
    effective_pos[pos <= -threshold] = -1
    
    if debug:
        print(f"[DEBUG] Effective positions after threshold={threshold}:")
        print(f"[DEBUG]   Distribution: {effective_pos.value_counts().sort_index().to_dict()}")
    

    try:
        spec = resolve_contract_spec(instrument)
        multiplier = spec.multiplier
    except KeyError:
        multiplier = 1.0
    

    lots_series = pd.Series(0, index=common_idx, dtype=int)
    current_lots = 0
    prev_pos = 0
    
    for ts in common_idx:
        curr_pos = effective_pos.loc[ts]
        price = px.loc[ts]
        

        if curr_pos != prev_pos:
            if curr_pos != 0:

                if fixed_notional:
                    current_lots = int(fixed_notional // (price * multiplier))
                else:
                    current_lots = int(initial_inv // (price * multiplier))
                current_lots = max(1, current_lots)
            else:

                current_lots = 0
        
        lots_series.loc[ts] = current_lots
        prev_pos = curr_pos
    

    price_changes = px.diff().fillna(0)
    

    pos_shifted = effective_pos.shift(1).fillna(0).astype(int)
    lots_shifted = lots_series.shift(1).fillna(0).astype(int)
    

    daily_pnl = pos_shifted * price_changes * lots_shifted * multiplier
    

    equity = initial_inv + daily_pnl.cumsum()
    equity.name = "TotalValue"
    
    equity_df = pd.DataFrame({"TotalValue": equity})
    

    decisions = _build_decisions_from_positions_dynamic(
        effective_pos=effective_pos,
        price_series=px,
        instrument=instrument,
        multiplier=multiplier,
        fixed_notional=fixed_notional,
        initial_inv=initial_inv,
    )
    

    metrics = {
        "sharpe": float(sharpe_ratio(equity)),
        "mdd": float(max_drawdown(equity)),
        "cagr": float(cagr(equity)),
        "vol": float(annualized_volatility(equity)),
        "total_return_pct": float(total_return_pct(equity)),
    }
    
    return {
        "equity_df": equity_df,
        "decisions": decisions,
        "metrics": metrics,
        "position_series": effective_pos,
        "lots_series": lots_series,  # Pour debug
    }


def _build_decisions_from_positions_dynamic(
    effective_pos: pd.Series,
    price_series: pd.Series,
    instrument: str,
    multiplier: float,
    fixed_notional: Optional[float] = None,
    initial_inv: float = 100_000,
) -> List[Dict[str, Any]]:

    decisions: List[Dict[str, Any]] = []
    prev_pos = 0
    current_lots = 0
    
    for ts, pos in effective_pos.items():
        if pos == prev_pos:
            continue
        
        price = float(price_series.loc[ts])
        

        if prev_pos != 0:
            side = "long" if prev_pos == 1 else "short"
            decisions.append({
                "date": ts,
                "instrument": instrument,
                "action": "CLOSE",
                "side": side,
                "price": price,
                "lots": current_lots,
            })
        

        if pos != 0:
            if fixed_notional:
                current_lots = int(fixed_notional // (price * multiplier))
            else:
                current_lots = int(initial_inv // (price * multiplier))
            current_lots = max(1, current_lots)
            
            side = "long" if pos == 1 else "short"
            decisions.append({
                "date": ts,
                "instrument": instrument,
                "action": f"OPEN_{side.upper()}",
                "side": side,
                "price": price,
                "lots": current_lots,
            })
        else:
            current_lots = 0
        
        prev_pos = pos
    
    return decisions



# ---------------------------------------------------------------------------
# 3) Utilities for fusion
# ---------------------------------------------------------------------------

def fuse_position_series(
    *series: pd.Series,
    method: str = "sum",
) -> pd.Series:

    if not series:
        raise ValueError("At least one series required")
    
    # Align all series on common index
    common_idx = series[0].index
    for s in series[1:]:
        common_idx = common_idx.intersection(s.index)
    
    aligned = [s.reindex(common_idx).fillna(0).astype(int) for s in series]
    
    if method == "sum":
        result = sum(aligned)
    
    elif method == "unanimous":
        # All must be same sign (and non-zero)
        stacked = pd.concat(aligned, axis=1)
        all_long = (stacked > 0).all(axis=1)
        all_short = (stacked < 0).all(axis=1)
        result = pd.Series(0, index=common_idx, dtype=int)
        result[all_long] = 1
        result[all_short] = -1
    
    elif method == "majority":
        stacked = pd.concat(aligned, axis=1)
        vote = stacked.sum(axis=1)
        n = len(aligned)
        result = pd.Series(0, index=common_idx, dtype=int)
        result[vote > n / 2] = 1
        result[vote < -n / 2] = -1
    
    else:
        raise ValueError(f"Unknown fusion method: {method}")
    
    result.name = "fused_position"
    return result


# ---------------------------------------------------------------------------
# 4) Get base strategy equity from calibrated profile
# ---------------------------------------------------------------------------

def get_base_strategy_equity(profile_name: str) -> pd.Series:

    from mvc_app.usecases.profile_base.profile_services import get_profile
    from mvc_core.optimize.oos_reconstruction_services import reconstruct_oos_equity_from_history
    from mvc_core.optimize.wf_history.wf_history_services import load_wf_calibration_run
    
    profile = get_profile(profile_name)
    
    if not profile.has_calibration:
        raise ValueError(f"Profile '{profile_name}' has no calibration.")
    
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
        build_indicator=False,
    )
    
    return oos["equity_oos_df"]["TotalValue"]


def _normalize_series_index(s: pd.Series) -> pd.Series:
    """Normalize a series index to naive timestamps."""
    s_copy = s.copy()
    if s_copy.index.tz is not None:
        s_copy.index = s_copy.index.tz_localize(None)
    return s_copy


def _build_flat_signals(
    effective_pos: pd.Series,
    price_series: pd.Series,
    instrument: str,
    lots_series: pd.Series,
) -> List[Dict[str, Any]]:

    pos_shifted = effective_pos.shift(1).fillna(0)
    lots_shifted = lots_series.shift(1).fillna(0).astype(int)
    flat_signals = []
    
    for ts in effective_pos.index:
        prev = pos_shifted.loc[ts]
        curr = effective_pos.loc[ts]
        if prev != 0 and curr == 0:
            price_at_ts = float(price_series.loc[ts]) if ts in price_series.index else None
            lots_at_ts = int(lots_shifted.loc[ts]) if ts in lots_shifted.index else 0
            flat_signals.append({
                "date": ts,
                "instrument": instrument,
                "action": "FLAT",
                "side": "long" if prev == 1 else "short",
                "price": price_at_ts,
                "lots": lots_at_ts,
            })
    
    return flat_signals


def _compute_buy_and_hold(
    price_series: pd.Series,
    instrument: str,
    initial_inv: float,
    notional: float,
) -> pd.Series:
    
    
    spec = resolve_contract_spec(instrument)
    first_price = price_series.dropna().iloc[0]
    lots_bh = int(notional // (first_price * spec.multiplier))
    bh_pnl = (price_series - first_price) * lots_bh * spec.multiplier
    bh_equity = initial_inv + bh_pnl
    bh_equity.name = "Buy&Hold"
    return bh_equity


def run_fusion_backtest(
    profile_names: List[str],
    instrument: str,
    initial_inv: float = 200_000_000,
    position_notional: float = 30_000_000,
    threshold: Optional[int] = None,
    fusion_method: str = "sum",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    debug: bool = False,
) -> Dict[str, Any]:
    """
    Run a complete fusion backtest combining multiple calibrated strategies.
    
    Args:
        profile_names: List of profile names to fuse
        instrument: Instrument key (e.g., "SB11")
        initial_inv: Initial investment (default 200M)
        position_notional: Notional per trade (default 30M)
        threshold: Minimum agreement to trade (default = len(profile_names))
        fusion_method: How to fuse positions ("sum", "unanimous", "majority")
        start_date: Optional start date for cropped view (normalizes equity to initial_inv)
        end_date: Optional end date for cropped view
        debug: Print debug info
    
    Returns:
        Dict with keys:
          - result: Backtest result dict
          - equity_df: DataFrame with Fusion, Buy&Hold, and base strategy equities
          - all_decisions: Decisions including FLAT signals
          - price_aligned: Price series aligned on equity index
          - metrics: Fusion strategy metrics
    """
    from mvc_app.jobs.jobs_data import JobConfig
    from mvc_app.usecases.profile_base.profile_services import get_profile
    
    if threshold is None:
        threshold = len(profile_names)
    
    # 1) Extract positions from all profiles
    position_series_list = []
    for name in profile_names:
        job = JobConfig(profile_name=name)
        if debug:
            print(f"Extracting positions from '{name}'...")
        pos = extract_position_series(job, debug=debug)
        position_series_list.append(pos)
        if debug:
            print(f"  -> {len(pos)} dates, {(pos != 0).sum()} non-flat days")
    
    pos_fusion = fuse_position_series(*position_series_list, method=fusion_method)
    if debug:
        print(f"\nFused positions: {len(pos_fusion)} dates")
        print(f"  Distribution: {pos_fusion.value_counts().sort_index().to_dict()}")
    
    profile = get_profile(profile_names[0])
    clock, price_series = profile.data_builder()
    px = price_series[instrument]
    
    if debug:
        print(f"\nRunning backtest with threshold={threshold}...")
    result = run_backtest_from_positions(
        position_series=pos_fusion,
        price_series=px,
        instrument=instrument,
        initial_inv=initial_inv,
        threshold=threshold,
        fixed_notional=position_notional,
        debug=debug,
    )
    
    equity_df = result["equity_df"]
    common_idx = equity_df.index
    px_aligned = _normalize_series_index(px).reindex(common_idx).ffill().bfill()
    
    bh_equity = _compute_buy_and_hold(px_aligned, instrument, initial_inv, position_notional)
    
    base_equities = {}
    for name in profile_names:
        if debug:
            print(f"Loading equity for '{name}'...")
        eq = get_base_strategy_equity(name)
        eq_aligned = _normalize_series_index(eq).reindex(common_idx).ffill().bfill()
        base_equities[name] = eq_aligned
    
    equity_df_full = equity_df.copy()
    equity_df_full.columns = ["TotalValue"]
    equity_df_full["Buy&Hold"] = bh_equity
    for name, eq in base_equities.items():
        equity_df_full[name] = eq
    
    flat_signals = _build_flat_signals(
        effective_pos=result["position_series"],
        price_series=px_aligned,
        instrument=instrument,
        lots_series=result["lots_series"],
    )
    all_decisions = result["decisions"] + flat_signals
    
    if debug:
        print(f"\n=== FUSION BACKTEST RESULTS ===")
        print(f"Sharpe:       {result['metrics']['sharpe']:.2f}")
        print(f"CAGR:         {result['metrics']['cagr']:.2%}")
        print(f"Max DD:       {result['metrics']['mdd']:.2%}")
        print(f"Volatility:   {result['metrics']['vol']:.2%}")
        print(f"Total Return: {result['metrics']['total_return_pct']:.2%}")
        nb_trades = len([d for d in result['decisions'] if 'OPEN' in d.get('action', '')])
        print(f"Nb trades:    {nb_trades}")
        print(f"Nb flat signals: {len(flat_signals)}")
    
    if start_date is not None or end_date is not None:
        equity_df_full, px_aligned, all_decisions = _crop_fusion_output(
            equity_df=equity_df_full,
            price=px_aligned,
            decisions=all_decisions,
            start_date=start_date,
            end_date=end_date,
            initial_value=initial_inv,
        )
        
        cropped_eq = equity_df_full["TotalValue"]
        result["metrics"] = {
            "sharpe": float(sharpe_ratio(cropped_eq)),
            "mdd": float(max_drawdown(cropped_eq)),
            "cagr": float(cagr(cropped_eq)),
            "vol": float(annualized_volatility(cropped_eq)),
            "total_return_pct": float(total_return_pct(cropped_eq)),
        }
        
        if debug:
            print(f"\n=== CROPPED RESULTS ({start_date} to {end_date}) ===")
            print(f"Sharpe:       {result['metrics']['sharpe']:.2f}")
            print(f"CAGR:         {result['metrics']['cagr']:.2%}")
            print(f"Max DD:       {result['metrics']['mdd']:.2%}")
    
    trade_decisions = [d for d in all_decisions if d.get("action") != "FLAT"]
    
    return {
        "result": result,
        "equity_df": equity_df_full,
        "all_decisions": all_decisions,  # Inclut FLAT pour le plot
        "trade_decisions": trade_decisions,  # Seulement OPEN/CLOSE pour build_trades_dataframe
        "price_aligned": px_aligned,
        "metrics": result["metrics"],
    }


def _crop_fusion_output(
    equity_df: pd.DataFrame,
    price: pd.Series,
    decisions: List[Dict[str, Any]],
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    initial_value: float = 200_000_000,
) -> tuple:

    if start_date is None:
        start_date = str(equity_df.index[0].date())
    if end_date is None:
        end_date = str(equity_df.index[-1].date())
    
    eq_slice = equity_df.loc[start_date:end_date]
    if eq_slice.empty:
        return equity_df, price, decisions
    
    df_rebased = pd.DataFrame(index=eq_slice.index)
    for col in eq_slice.columns:
        base_val = float(eq_slice[col].iloc[0])
        df_rebased[col] = eq_slice[col] - base_val + initial_value
    
    px_slice = price.loc[start_date:end_date]
    
    start_ts = pd.to_datetime(start_date)
    end_ts = pd.to_datetime(end_date)
    
    def _to_naive(ts):
        ts = pd.Timestamp(ts)
        if ts.tzinfo is not None:
            return ts.tz_localize(None)
        return ts
    
    decisions_cropped = [
        dec for dec in decisions
        if _to_naive(dec["date"]) >= start_ts and _to_naive(dec["date"]) <= end_ts
    ]
    
    return df_rebased, px_slice, decisions_cropped
