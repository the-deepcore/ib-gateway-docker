from typing import Any, Dict, Optional

import pandas as pd

from mvc_core.domain.clock.clock_data import Clock
from mvc_core.domain.enums import Action, Side
from mvc_core.domain.portfolio.portfolio_data import Portfolio
from mvc_core.domain.portfolio.portfolio_services import (
    close_position,
    find_open_positions,
    open_position,
    reduce_position_lots,
)
from mvc_core.engine.backtester.backtester_data import BacktesterCfg
from mvc_core.engine.signals.signal_data import TradeSignal


def current_price_map(clock: Clock, price_series: Dict[str, pd.Series]) -> Dict[str, float]:
    """Return {instrument: raw_price} at current clock timestamp."""
    ts = clock.index[clock.cursor]

    out: Dict[str, float] = {}
    for name, s in price_series.items():
        if ts in s.index:
            out[name] = float(s.loc[ts])

    return out





def execute_signal(
    pf: Portfolio,
    signal: TradeSignal,
    clock: Clock,
    price_map: Dict[str, float],
    tick_size: float,
    bt: Optional[BacktesterCfg],
) -> None:
    

    """Apply a TradeSignal to the portfolio."""
    instr = signal.instrument

    if instr not in price_map:
        return

    ts = clock.index[clock.cursor]
    px = float(price_map[instr])

    def _log(action_str: str, side_val: Optional[Side], price_val: float, lots: Optional[int] = None, 
             reduce_ratio: Optional[float] = None, meta: Optional[Dict[str, Any]] = None) -> None:
        if bt is None:
            return
        ev = {
            "date": ts,                              
            "instrument": instr,
            "action": action_str,                    
            "price": float(price_val),
        }
        if side_val is not None:
            ev["side"] = side_val.value
        if lots is not None:
            ev["lots"] = int(lots)
        if reduce_ratio is not None:
            ev["reduce_ratio"] = float(reduce_ratio)
        if meta is not None:
            ev["meta"] = dict(meta)            
        bt.trades_log.append(ev)



    if signal.action == Action.OPEN:
        if signal.side is None or signal.lots is None or int(signal.lots) <= 0:
            raise ValueError("OPEN requires side and lots > 0")
        
        lots = int(signal.lots)
        open_position(
            pf=pf,
            instrument=instr,
            side=signal.side,
            lots=lots,
            entry_date=ts,
            entry_price_raw=px,
            tick_size=tick_size,
        )
        _log(f"OPEN_{signal.side.value}", signal.side, px, lots=lots, meta=getattr(signal, "meta", None))

    elif signal.action == Action.CLOSE:
        opens = find_open_positions(pf, instrument=instr)
        to_close = [p for p in opens if p.side == signal.side]

        if not to_close:
            return

        closed_n = 0
        for pos in to_close:  
            close_position(
                pf=pf,
                position=pos,
                exit_date=ts,
                exit_price_raw=px,
                tick_size=tick_size,
            )
            closed_n += 1

        _log(
            "CLOSE",
            signal.side,
            px,
            meta={**(getattr(signal, "meta", {}) or {}), "closed_legs": closed_n},
        )


    elif signal.action == Action.REDUCE:
        rr = float(signal.reduce_ratio or 0.0)
        if rr <= 0.0 or rr > 1.0:
            return

        open_list = find_open_positions(pf, instrument=signal.instrument)
        legs = [p for p in open_list if p.side == signal.side]
        if not legs:
            return

        total_lots = sum(int(getattr(p, "lots", 0)) for p in legs)
        if total_lots <= 0:
            return

        reduced_legs = 0
        for pos in list(legs):
            leg_lots = int(getattr(pos, "lots", 0))
            reduce_lots = int(max(1, int(rr * leg_lots)))
            reduce_position_lots(
                pf=pf,
                position=pos,
                reduce_lots=reduce_lots,
                exit_date=ts,
                exit_price_raw=px,
                tick_size=tick_size,
            )
            reduced_legs += 1

        _log(
            f"REDUCE_{signal.side.value}",
            signal.side,
            px,
            reduce_ratio=rr,
            meta={**(getattr(signal, "meta", {}) or {}), "reduced_legs": reduced_legs},
        )



    elif signal.action == Action.REBALANCE:

        if signal.side is None or signal.lots is None:
            return

        target = int(signal.lots)
        open_list = find_open_positions(pf, instrument=instr)
        legs = [p for p in open_list if p.side == signal.side]

        current = int(sum(int(getattr(p, "lots", 0)) for p in legs))

        if target == current:
            _log(f"REBALANCE_{signal.side.value}_NOOP", signal.side, px,
                 lots=target, meta=getattr(signal, "meta", None))
            return

        if target <= 0:
            closed_n = 0
            for pos in list(legs):
                close_position(
                    pf=pf,
                    position=pos,
                    exit_date=ts,
                    exit_price_raw=px,
                    tick_size=tick_size,
                )
                closed_n += 1
            _log(f"REBALANCE_{signal.side.value}_CLOSE_ALL", signal.side, px,
                 lots=0, meta={**(getattr(signal, "meta", {}) or {}), "closed_legs": closed_n})
            return

        if target > current:
            add_lots = target - current
            open_position(
                pf=pf,
                instrument=instr,
                side=signal.side,
                lots=int(add_lots),
                entry_date=ts,
                entry_price_raw=px,
                tick_size=tick_size,
                meta=getattr(signal, "meta", None),
            )
            _log(f"REBALANCE_{signal.side.value}_ADD", signal.side, px,
                 lots=target, meta={**(getattr(signal, "meta", {}) or {}), "delta_lots": int(add_lots)})
        else:
            if current <= 0 or not legs:
                return
            reduce_total = current - target
            remaining = int(reduce_total)
            reduced_legs = 0
            for pos in list(legs):
                if remaining <= 0:
                    break
                leg_lots = int(getattr(pos, "lots", 0))
                r = min(leg_lots, remaining)
                if r <= 0:
                    continue
                reduce_position_lots(
                    pf=pf,
                    position=pos,
                    reduce_lots=int(r),
                    exit_date=ts,
                    exit_price_raw=px,
                    tick_size=tick_size,
                )
                remaining -= int(r)
                reduced_legs += 1

            _log(f"REBALANCE_{signal.side.value}_REDUCE", signal.side, px,
                 lots=target, meta={**(getattr(signal, "meta", {}) or {}), "reduce_lots": int(reduce_total), "reduced_legs": reduced_legs})


    elif signal.action == Action.HOLD:
        return

    else:
        raise ValueError("Unknown action")
