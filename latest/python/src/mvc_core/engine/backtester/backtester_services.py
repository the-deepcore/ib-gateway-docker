from typing import Callable, Dict, Optional

import pandas as pd

from mvc_core.domain.clock.clock_services import tick
from mvc_core.strategies.build.callable_types import RiskFn, SignalFn

from ..signals.signal_services import current_price_map, execute_signal
from .backtester_data import BacktesterCfg


def run_backtest(
    bt: BacktesterCfg,
    signal_fn: SignalFn,
    on_step: Optional[Callable[[pd.Timestamp, Dict[str, float], object], None]] = None,
    risk_fn: Optional[RiskFn] = None, 

) -> None:
    """Iterate the Clock, execute signals; call on_step(ts, prices, portfolio) if provided."""
    clk = bt.clock
    n = len(clk.index)

    while True:
        ts = clk.index[clk.cursor]
        prices = current_price_map(clk, bt.price_series)

        if risk_fn is not None:
            
            risk_signals = risk_fn(ts, prices, bt.portfolio) or []
            for sig in risk_signals:
                execute_signal(
                    pf=bt.portfolio,
                    signal=sig,
                    clock=clk,
                    price_map=prices,
                    tick_size=bt.tick_size,
                    bt=bt,
                )


        signals = signal_fn(ts, prices) or []
        for sig in signals:
            execute_signal(
                pf=bt.portfolio,
                signal=sig,
                clock=clk,
                price_map=prices,
                tick_size=bt.tick_size,
                bt=bt,
            )
        if on_step is not None:
            on_step(ts, prices, bt.portfolio)

        if clk.cursor >= n - 1:
            break
        
        tick(clk)
