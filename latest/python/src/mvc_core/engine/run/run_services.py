from typing import Dict, Optional

import pandas as pd

from mvc_core.domain.clock.clock_services import build_from_index
from mvc_core.domain.portfolio.portfolio_data import Portfolio
from mvc_core.domain.portfolio.portfolio_services import get_total_value
from mvc_core.engine.backtester.backtester_data import BacktesterCfg
from mvc_core.engine.backtester.backtester_services import run_backtest
from mvc_core.engine.run.run_data import RunArtifacts, RunCfg, RunMetrics, RunResult
from mvc_core.performances.build_backtest_output import make_equity_df
from mvc_core.performances.metrics_services import (
    annualized_volatility,
    cagr,
    max_drawdown,
    sharpe_ratio,
    total_return_pct,
)
from mvc_core.strategies.build.build_data import BuiltStrategy
from mvc_core.strategies.build.callable_types import RiskFn, SignalFn

# ---------------------------------------------------------------------------#
# 1) Exécution : RunCfg -> RunArtifacts                                      #
# ---------------------------------------------------------------------------#


def run_execute(run_cfg: RunCfg) -> RunArtifacts:
    """
    Exécute un run à partir d'un RunCfg et renvoie uniquement les artefacts bruts.

    Comportement répliqué depuis l'ancien run_strategy_backtest + eval_single_run :
      - création d'un Portfolio(initial_inv=...)
      - BacktesterCfg(clock, portfolio, price_series, tick_size)
      - run_backtest avec signal_fn / risk_fn
      - reconstruction de l'equity via make_equity_df (TotalValue, Buy&Hold, ...)
    """
    clock_og = run_cfg.clock

    clock = build_from_index(clock_og.index)
    price_series = run_cfg.price_series
    built: BuiltStrategy = run_cfg.built_strat


    bench_key = run_cfg.bench_key

    initial_portfolio = run_cfg.initial_portfolio

    # derive bench notional from tags, then sizer meta, else fall back to capital
    bench_notional = None
    tag_notional = run_cfg.tags.get("bench_notional") if run_cfg.tags else None
    if tag_notional is not None:
        try:
            bench_notional = float(tag_notional)
        except Exception:
            bench_notional = None
    if bench_notional is None:
        try:
            bench_notional = float(built.strategy_cfg.sizer_cfg.meta.get("notional_usd"))  # type: ignore[attr-defined]
        except Exception:
            bench_notional = None
    if bench_notional is None:
        bench_notional = run_cfg.initial_inv

    # 1) Portfolio initial
    pf = initial_portfolio if initial_portfolio is not None else Portfolio(initial_inv=run_cfg.initial_inv)


    # 2) BacktesterCfg
    bt = BacktesterCfg(
        clock=clock,
        portfolio=pf,
        price_series=price_series,
        tick_size=run_cfg.tick_size,
    )

    # 3) Collecte des points d'equity pendant le backtest
    equity_points: Dict[pd.Timestamp, float] = {}

    from mvc_core.domain.clock.clock_services import _to_naive


    def _on_step(ts: pd.Timestamp, prices: Dict[str, float], portfolio: Portfolio) -> None:
        equity_points[_to_naive(ts)] = get_total_value(portfolio, prices)

    # 4) Exécution du backtest (signal_fn + risk_fn)
    signal_fn: SignalFn = built.signal_fn
    risk_fn: Optional[RiskFn] = built.risk_fn

    run_backtest(
        bt,
        signal_fn,
        on_step=_on_step,
        risk_fn=risk_fn,
    )

    # 5) Reconstruction de l'equity
    bench_price = price_series.get(bench_key, None) if bench_key is not None else None

    equity_df = make_equity_df(
        equity_points=equity_points,
        clock_index=clock.index,
        bench_price=bench_price,
        initial_inv=pf.initial_inv,
        bench_notional=bench_notional,
        display_initial_value=(run_cfg.tags.get("display_initial_value") if run_cfg.tags else None) or pf.initial_inv,
    )

    decisions = bt.trades_log

    portfolio_final = bt.portfolio

    return RunArtifacts(
        equity_df=equity_df,
        decisions=decisions,
        portfolio=portfolio_final,
    )


# ---------------------------------------------------------------------------#
# 2) Évaluation : RunArtifacts -> RunMetrics                                 #
# ---------------------------------------------------------------------------#

from mvc_core.domain.enums import Action


def run_evaluate(artifacts: RunArtifacts) -> RunMetrics:
    """
    Calcule les métriques de performance à partir des artefacts du run.

    On reproduit la logique de eval_single_run :
      - on prend equity_df["TotalValue"] comme série de référence,
      - on calcule Sharpe, MDD, CAGR, vol, total_return_pct.
    """
    eq_df = artifacts.equity_df
    dec = artifacts.decisions
    nb_trades = sum(1 for d in dec if d['action'] and d['action'] == Action.CLOSE)

    # Dans ton code, la colonne utilisée est 'TotalValue' 
    eq = eq_df["TotalValue"]

    metrics = RunMetrics(
        sharpe=float(sharpe_ratio(eq)),
        mdd=float(max_drawdown(eq)),
        cagr=float(cagr(eq)),
        vol=float(annualized_volatility(eq)),
        total_return_pct=float(total_return_pct(eq)),
        nb_trades = int(nb_trades)
    )

    return metrics


# ---------------------------------------------------------------------------#
# 3) Orchestrateur : RunCfg -> RunResult                                     #
# ---------------------------------------------------------------------------#


def run_full(run_cfg: RunCfg) -> RunResult:
    """
    Orchestrateur standard : RunCfg -> RunResult (via RunArtifacts + RunMetrics).
    """
    artifacts = run_execute(run_cfg)
    metrics = run_evaluate(artifacts)
    return RunResult(cfg=run_cfg, artifacts=artifacts, metrics=metrics)
