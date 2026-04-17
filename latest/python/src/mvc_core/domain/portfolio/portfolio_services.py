from typing import Any, Dict, List, Optional

import pandas as pd

from mvc_core.domain.enums import Side, Status
from mvc_core.domain.market.contract_specs import resolve_contract_spec
from mvc_core.domain.portfolio.portfolio_data import Portfolio
from mvc_core.domain.portfolio.position_data import Position

# ---------------- Helpers ----------------

def _sign(side: Side) -> int:
    """+1 for LONG, -1 for SHORT."""
    return 1 if side == Side.LONG else -1


def _name_of(instrument: Any) -> str:
    """Instrument name or str(instrument)."""
    return getattr(instrument, "name", str(instrument))


def _apply_tick(side: Side, price_raw: float, leg: str, tick_size: float) -> float:
    """Return price adjusted by one tick for fees on 'entry' or 'exit'."""
    if leg == "entry":
        if side == Side.LONG:
            return float(price_raw) + tick_size
        else:
            return float(price_raw) - tick_size
    elif leg == "exit":
        if side == Side.LONG:
            return float(price_raw) - tick_size
        else:
            return float(price_raw) + tick_size
    else:
        raise ValueError("leg must be 'entry' or 'exit'")


def _update_cash_with_borrowing(pf: Portfolio, new_cash: float) -> None:
    """Set cash and increment total_borrowed by the incremental negative part."""
    old_neg = -pf.cash if pf.cash < 0 else 0.0
    new_neg = -new_cash if new_cash < 0 else 0.0
    inc = new_neg - old_neg
    if inc > 0:
        pf.total_borrowed += inc
    pf.cash = new_cash


# ---------------- Trading Services ----------------

def open_position(
    pf: Portfolio,
    instrument: Any,
    side: Side,
    lots: int,
    entry_date: pd.Timestamp,
    entry_price_raw: float,
    tick_size: float = 0.01,
    meta: Optional[Dict[str, Any]] = None,
) -> Position:
    """Open a position sized in integer lots; adjust cash (allows negative cash)."""
    lots = int(lots)
    if lots <= 0:
        raise ValueError("lots must be > 0")

    spec = resolve_contract_spec(_name_of(instrument))
    multiplier = float(spec.multiplier)
    entry_eff = _apply_tick(side, float(entry_price_raw), leg="entry", tick_size=tick_size)

    entry_notional = float(lots) * multiplier * float(entry_eff)

    # cash update
    if side == Side.LONG:
        _update_cash_with_borrowing(pf, pf.cash - entry_notional)
    else:  # SHORT
        _update_cash_with_borrowing(pf, pf.cash + entry_notional)

    pos = Position(
        instrument=instrument,
        side=side,
        lots=int(lots),
        multiplier=multiplier,
        entry_date=pd.Timestamp(entry_date),
        entry_price_raw=float(entry_price_raw),
        entry_price_eff=entry_eff,
        meta=meta,
    )
    pf.positions.append(pos)
    return pos


def reduce_position_lots(
    pf: Portfolio,
    position: Position,
    reduce_lots: int,
    exit_date: pd.Timestamp,
    exit_price_raw: float,
    tick_size: float = 0.0,
) -> float:
    """Reduce position by an integer number of lots; return realized PnL (USD)."""
    if position.status != Status.OPEN:
        raise ValueError("position must be OPEN")

    reduce_lots = int(reduce_lots)
    if reduce_lots <= 0:
        return 0.0
    if reduce_lots > int(position.lots):
        reduce_lots = int(position.lots)

    exit_eff = _apply_tick(position.side, float(exit_price_raw), leg="exit", tick_size=tick_size)
    multiplier = float(position.multiplier)

    pnl_per_lot = (float(exit_eff) - float(position.entry_price_eff)) * multiplier
    pnl = float(_sign(position.side) * reduce_lots * pnl_per_lot)

    close_notional = float(reduce_lots) * multiplier * float(exit_eff)
    if position.side == Side.LONG:
        _update_cash_with_borrowing(pf, pf.cash + close_notional)
    else:
        _update_cash_with_borrowing(pf, pf.cash - close_notional)

    position.realized_pnl += pnl
    position.lots = int(position.lots) - int(reduce_lots)

    if int(position.lots) <= 0:
        position.lots = 0
        position.exit_date = pd.Timestamp(exit_date)
        position.exit_price_raw = float(exit_price_raw)
        position.exit_price_eff = float(exit_eff)
        position.status = Status.CLOSED

    return pnl


def close_position(
    pf: Portfolio,
    position: Position,
    exit_date: pd.Timestamp,
    exit_price_raw: float,
    tick_size: float = 0.0,
) -> float:
    """Close all remaining lots; update cash; return realized PnL (USD)."""
    if position.status != Status.OPEN:
        return 0.0
    return reduce_position_lots(
        pf,
        position,
        reduce_lots=int(position.lots),
        exit_date=exit_date,
        exit_price_raw=exit_price_raw,
        tick_size=tick_size,
    )


# ---------------- Query / Valuation ----------------

def get_total_value(pf: Portfolio, current_prices: Dict[str, float]) -> float:
    """Return cash + MtM of open positions using raw prices."""
    total = pf.cash
    for pos in pf.positions:
        if pos.status == Status.OPEN:
            name = _name_of(pos.instrument)
            if name not in current_prices:
                raise KeyError(f"Missing price for {name}")
            p_raw = float(current_prices[name])
            total += float(_sign(pos.side) * int(pos.lots) * float(pos.multiplier) * p_raw)
    return float(total)


def find_open_positions(pf: Portfolio, instrument: Optional[str] = None) -> List[Position]:
    """Return open positions optionally filtered by instrument name."""
    out: List[Position] = []
    for p in pf.positions:
        if p.status == Status.OPEN:
            if instrument is None or _name_of(p.instrument) == instrument:
                out.append(p)
    return out


