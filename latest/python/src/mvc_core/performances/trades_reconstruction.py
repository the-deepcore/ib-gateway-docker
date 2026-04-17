from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from mvc_core.domain.enums import Side
from mvc_core.domain.market.contract_specs import resolve_contract_spec


@dataclass
class TradeRecord:
    """Une position complète (ouverture → fermeture)."""
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    side: Side
    entry_price: float
    exit_price: float
    lots: int
    multiplier: float
    realized_pnl: float  # PnL en USD (lots * multiplier * prix)
    realized_pnl_pct: float  # PnL en % du capital initial
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertir en dict pour DataFrame."""
        return {
            "entry_date": self.entry_date,
            "exit_date": self.exit_date,
            "duration_days": (self.exit_date - self.entry_date).days,
            "side": self.side.value if isinstance(self.side, Side) else self.side,
            "entry_price": round(self.entry_price, 4),
            "exit_price": round(self.exit_price, 4),
            "price_change": round(self.exit_price - self.entry_price, 4),
            "lots": int(self.lots),
            "multiplier": round(self.multiplier, 2),
            "realized_pnl": round(self.realized_pnl, 2),
            "realized_pnl_pct": round(self.realized_pnl_pct, 4),
        }


def _pair_open_close_trades(
    decisions: List[Dict[str, Any]]
) -> List[Tuple[Dict[str, Any], Optional[Dict[str, Any]]]]:
    """
    Apparie les signaux OPEN avec les signaux CLOSE correspondants.
    
    Retourne une liste de (open_signal, close_signal) pairs.
    
    Logique :
      - Parcourt les décisions chronologiquement
      - Pour chaque OPEN_LONG/OPEN_SHORT, cherche le prochain CLOSE du même side
      - Gère les multiples legs (accumulation)
    """
    paired: List[Tuple[Dict[str, Any], Optional[Dict[str, Any]]]] = []
    open_stack: Dict[str, List[Dict[str, Any]]] = {}  # (instrument, side) -> [opens]
    
    for dec in decisions:
        action = str(dec.get("action", "")).upper()
        instrument = dec.get("instrument")
        side = dec.get("side")
        
        if not instrument or not side:
            continue
        
        key = (instrument, side)
        
        # OPEN → ajouter à la stack
        if action.startswith("OPEN"):
            if key not in open_stack:
                open_stack[key] = []
            open_stack[key].append(dec)
        
        # CLOSE → appairer avec l'OPEN le plus ancien (FIFO)
        elif action == "CLOSE":
            if key in open_stack and open_stack[key]:
                open_dec = open_stack[key].pop(0)  # FIFO
                paired.append((open_dec, dec))
    
    # Les OPEN non fermés restent ouverts (exit_date = None)
    for opens_list in open_stack.values():
        for open_dec in opens_list:
            paired.append((open_dec, None))
    
    return paired


def _calculate_pnl(
    side: Side,
    entry_price: float,
    exit_price: float,
    lots: int,
    multiplier: float,
    initial_inv: float,
) -> Tuple[float, float]:
    """
    Calcule le PnL réalisé.
    
    Args:
        side: LONG ou SHORT
        entry_price: Prix d'entrée
        exit_price: Prix de sortie
        lots: Nombre de lots négociés
        multiplier: Multiplicateur du contrat
        initial_inv: Capital initial (pour normaliser le PnL%)
    
    Returns:
        (realized_pnl_abs, realized_pnl_pct)
    """
    sign = 1.0 if side == Side.LONG else -1.0
    pnl_abs = sign * float(lots) * float(multiplier) * (exit_price - entry_price)
    pnl_pct = (pnl_abs / float(initial_inv)) * 100 if initial_inv else 0.0
    
    return float(pnl_abs), float(pnl_pct)


def build_trades_dataframe(
    decisions: List[Dict[str, Any]],
    initial_inv: Optional[float] = None,
    include_open_positions: bool = False,
) -> pd.DataFrame:
    """
    Construit un DataFrame de trades complets à partir des décisions du backtest.

    Args:
        decisions: Liste brute des décisions (log backtester)
        initial_inv: Capital initial utilisé pour normaliser le PnL % (default: 200m)
        include_open_positions: Si True, inclut les positions encore ouvertes

    Returns:
        DataFrame avec colonnes: entry_date, exit_date, duration_days, side,
        entry_price, exit_price, price_change, lots, multiplier, realized_pnl,
        realized_pnl_pct
    """
    paired = _pair_open_close_trades(decisions)
    initial_inv_val = float(initial_inv) if initial_inv is not None else 0.0
    trades: List[TradeRecord] = []
    
    for open_dec, close_dec in paired:
        entry_date = pd.to_datetime(open_dec.get("date"))
        # Normalize to tz-naive to avoid tz-aware vs tz-naive issues
        if entry_date.tzinfo is not None:
            entry_date = entry_date.tz_localize(None)
        entry_price = float(open_dec.get("price", 0.0))
        lots = int(open_dec.get("lots", 0) or 0)
        if lots <= 0:
            continue
        side_str = open_dec.get("side", "")

        spec = resolve_contract_spec(open_dec.get("instrument"))
        multiplier = float(spec.multiplier if spec is not None else 1.0)
        
        # Déterminer le side
        try:
            side = Side[side_str.upper()] if isinstance(side_str, str) else side_str
        except (KeyError, AttributeError):
            side = Side.LONG  # Fallback
        
        # Si pas de close, skip (ou inclure comme position ouverte)
        if close_dec is None:
            if not include_open_positions:
                continue
            # Utiliser pd.Timestamp.now() tz-naive pour cohérence avec entry_date
            exit_date = pd.Timestamp.now()
            exit_price = entry_price  # Pas de prix de sortie
            pnl_abs, pnl_pct = 0.0, 0.0
        else:
            exit_date = pd.to_datetime(close_dec.get("date"))
            # Normalize to tz-naive
            if exit_date.tzinfo is not None:
                exit_date = exit_date.tz_localize(None)
            exit_price = float(close_dec.get("price", entry_price))
            pnl_abs, pnl_pct = _calculate_pnl(side, entry_price, exit_price, lots, multiplier, initial_inv_val)
        
        trades.append(TradeRecord(
            entry_date=entry_date,
            exit_date=exit_date,
            side=side,
            entry_price=entry_price,
            exit_price=exit_price,
            lots=lots,
            multiplier=multiplier,
            realized_pnl=pnl_abs,
            realized_pnl_pct=pnl_pct,
        ))
    
    if not trades:
        return pd.DataFrame(columns=[
            "entry_date", "exit_date", "duration_days", "side", "entry_price", 
            "exit_price", "price_change", "lots", "multiplier", "realized_pnl", "realized_pnl_pct"
        ])
    
    # Convertir en DataFrame
    rows = [t.to_dict() for t in trades]
    df = pd.DataFrame(rows)
    
    # Trier par date d'entrée
    df = df.sort_values("entry_date").reset_index(drop=True)
    
    # Formater les colonnes dates
    df["entry_date"] = pd.to_datetime(df["entry_date"]).dt.strftime("%Y-%m-%d %H:%M")
    df["exit_date"] = pd.to_datetime(df["exit_date"]).dt.strftime("%Y-%m-%d %H:%M")
    
    return df


def print_trades_summary(trades_df: pd.DataFrame, start_date: Optional[str] = None, end_date: Optional[str] = None) -> None:
    """
    Affiche un résumé lisible des trades.
    
    Args:
        trades_df: DataFrame généré par build_trades_dataframe
        start_date: Filtre optionnel (YYYY-MM-DD)
        end_date: Filtre optionnel (YYYY-MM-DD)
    """
    df = trades_df.copy()
    
    if start_date:
        df = df[df["entry_date"] >= start_date]
    if end_date:
        df = df[df["exit_date"] <= end_date]
    
    if df.empty:
        print("❌ Aucun trade dans cette période.")
        return
    
    print("\n" + "="*120)
    print(f"📊 TRADES SUMMARY ({len(df)} trades)")
    print("="*120)
    print(df.to_string(index=False))
    print("="*120)
    
    # Stats globales
    print(f"\n📈 STATISTIQUES")
    print(f"   Total trades: {len(df)}")
    print(f"   Winning trades: {len(df[df['realized_pnl_pct'] > 0])}")
    print(f"   Losing trades: {len(df[df['realized_pnl_pct'] < 0])}")
    print(f"   Win rate: {len(df[df['realized_pnl_pct'] > 0]) / len(df) * 100:.1f}%")
    print(f"   Avg PnL: {df['realized_pnl_pct'].mean():.2f}%")
    print(f"   Total PnL: {df['realized_pnl'].sum():.2f}")
    print(f"   Avg duration: {df['duration_days'].mean():.1f} jours")