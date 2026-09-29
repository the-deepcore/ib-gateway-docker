"""
Méthodologie CEPEA vs Futures café (Arabica / Robusta).

Conversion du prix CEPEA (USD / sac 60 kg) :
  - Robusta : USD/sac -> USD/tonne         : x (1000 / 60)
  - Arabica : USD/sac -> cents/lb          : x (1000 / 60) / 22.0462

Différentiel = prix CEPEA converti - close du futures correspondant, le
futures étant choisi via un calendrier fixe (voir CONTRACT_CALENDARS).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional, Union

import pandas as pd
from ib_insync import IB, Future, util

DateLike = Union[str, date, datetime, pd.Timestamp]

# ---------------------------------------------------------------------------
# Coefficients de conversion
# ---------------------------------------------------------------------------
LBS_PER_TONNE_DIV = 22.0462  # USD/t / 22.0462 = cents/lb

CONVERSION_COEFS = {
    "robusta": 1000.0 / 60.0,                    # ≈ 16.6667
    "arabica": 1000.0 / 60.0 / LBS_PER_TONNE_DIV,  # ≈ 0.7560
}

# Symboles IBKR 
IBKR_SYMBOLS = {
    "arabica": {"symbol": "KC", "exchange": "NYBOT"},
    "robusta": {"symbol": "D", "exchange": "ICEEUSOFT"},
}

MONTH_CODE_TO_NUM = {
    "F": 1, "G": 2, "H": 3, "J": 4, "K": 5, "M": 6,
    "N": 7, "Q": 8, "U": 9, "V": 10, "X": 11, "Z": 12,
}

# ---------------------------------------------------------------------------
# Calendriers fixes : ((mois_debut, jour_debut), (mois_fin, jour_fin), code)
# Les bornes sont inclusives et indépendantes de l'année. Une fenêtre qui
# chevauche le 1er janvier (ex. 1er nov -> 14 jan) est gérée par
# `_in_window`.
# ---------------------------------------------------------------------------
CONTRACT_CALENDARS = {
    "arabica": [
        ((1, 15), (3, 14), "K"),   # Mai
        ((3, 15), (4, 30), "N"),   # Juillet
        ((5, 1), (7, 31), "U"),    # Septembre
        ((8, 1), (10, 31), "Z"),   # Décembre
        ((11, 1), (1, 14), "H"),   # Mars (année suivante)
    ],
    "robusta": [
        ((1, 15), (3, 14), "K"),   # Mai
        ((3, 15), (4, 30), "N"),   # Juillet
        ((5, 1), (7, 31), "U"),    # Septembre
        ((8, 1), (9, 14), "X"),    # Novembre
        ((9, 15), (11, 30), "F"),  # Janvier (année suivante)
        ((12, 1), (1, 14), "H"),   # Mars (année suivante)
    ],
}


@dataclass(frozen=True)
class FuturesContract:
    coffee_type: str
    month_code: str
    year: int

    @property
    def month(self) -> int:
        return MONTH_CODE_TO_NUM[self.month_code]

    @property
    def contract_month(self) -> str:
        """Format YYYYMM attendu par IBKR (lastTradeDateOrContractMonth)."""
        return f"{self.year}{self.month:02d}"

    @property
    def ticker(self) -> str:
        root = "KC" if self.coffee_type == "arabica" else "RM"
        return f"{root}{self.month_code}{self.year % 100:02d}"

    def __str__(self) -> str:
        return self.ticker


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _normalize_coffee_type(coffee_type: str) -> str:
    ct = coffee_type.strip().lower()
    aliases = {"kc": "arabica", "rc": "robusta", "rm": "robusta", "d": "robusta"}
    ct = aliases.get(ct, ct)
    if ct not in CONVERSION_COEFS:
        raise ValueError(f"coffee_type inconnu : {coffee_type!r} (attendu 'arabica' ou 'robusta')")
    return ct


def _to_date(d: DateLike) -> date:
    return pd.Timestamp(d).date()


def _in_window(d: date, start: tuple[int, int], end: tuple[int, int]) -> bool:
    md = (d.month, d.day)
    if start <= end:
        return start <= md <= end
    # fenêtre à cheval sur le 1er janvier
    return md >= start or md <= end


# ---------------------------------------------------------------------------
# Mapping date -> contrat
# ---------------------------------------------------------------------------
def get_contract_for_date(d: DateLike, coffee_type: str) -> FuturesContract:
    """Retourne le contrat futures à utiliser pour une date de donnée CEPEA."""
    ct = _normalize_coffee_type(coffee_type)
    dd = _to_date(d)
    for start, end, code in CONTRACT_CALENDARS[ct]:
        if _in_window(dd, start, end):
            # le contrat est la première échéance >= date de la donnée
            year = dd.year if MONTH_CODE_TO_NUM[code] >= dd.month else dd.year + 1
            return FuturesContract(ct, code, year)
    raise RuntimeError(f"Aucune fenêtre calendaire pour {dd} / {ct}")  # ne doit pas arriver


# ---------------------------------------------------------------------------
# Conversion élémentaire
# ---------------------------------------------------------------------------
def convert_cepea_price(price: float, coffee_type: str) -> float:
    """Prix CEPEA (USD/sac 60kg) -> unité du futures (USD/t robusta, c/lb arabica)."""
    ct = _normalize_coffee_type(coffee_type)
    return float(price) * CONVERSION_COEFS[ct]


def convert_cepea(d: DateLike, coffee_type: str, price: float) -> tuple[FuturesContract, float]:
    """Couple (date, coffee_type, prix) -> (contrat à retrancher, prix CEPEA converti)."""
    contract = get_contract_for_date(d, coffee_type)
    return contract, convert_cepea_price(price, coffee_type)


def compute_differential(d: DateLike, coffee_type: str, price: float, futures_close: float) -> dict:
    """Différentiel = prix CEPEA converti - close du futures correspondant (fourni par l'appelant)."""
    contract, converted = convert_cepea(d, coffee_type, price)
    return {
        "date": _to_date(d),
        "coffee_type": contract.coffee_type,
        "contract": contract.ticker,
        "contract_month": contract.contract_month,
        "cepea_price": float(price),
        "cepea_converted": converted,
        "futures_close": float(futures_close),
        "differential": converted - float(futures_close),
    }


# ---------------------------------------------------------------------------
# Récupération du close futures via IBKR
# ---------------------------------------------------------------------------
def fetch_futures_close(contract: FuturesContract, d: DateLike, ib: Optional[IB] = None,
                        host: str = "127.0.0.1", port: int = 4002, client_id: int = 1,
                        lookback_days: int = 10) -> tuple[date, float]:
    """
    Close du contrat à la date `d`. Si aucune barre n'existe ce jour-là (week-end,
    férié, donnée pas encore publiée), retourne le dernier close disponible <= d.
    Renvoie (date_effective_du_close, close).
    """
    dd = _to_date(d)
    spec = IBKR_SYMBOLS[contract.coffee_type]
    own_connection = ib is None
    if own_connection:
        ib = IB()
        ib.connect(host, port, clientId=client_id)
    try:
        fut = Future(symbol=spec["symbol"], lastTradeDateOrContractMonth=contract.contract_month,
                     exchange=spec["exchange"], includeExpired=True)
        if not ib.qualifyContracts(fut):
            raise RuntimeError(f"Contrat IBKR non qualifiable : {contract} ({spec})")

        # endDateTime au lendemain 00:00 pour inclure la barre daily de `dd`
        end_dt = datetime.combine(dd + timedelta(days=1), datetime.min.time())
        bars = ib.reqHistoricalData(
            fut,
            endDateTime=end_dt.strftime("%Y%m%d %H:%M:%S"),
            durationStr=f"{lookback_days} D",
            barSizeSetting="1 day",
            whatToShow="TRADES",
            useRTH=True,
            formatDate=1,
        )
        df = util.df(bars)
        if df is None or df.empty:
            raise RuntimeError(f"Aucune barre IBKR pour {contract} autour du {dd}")
        df["date"] = pd.to_datetime(df["date"]).dt.date
        df = df[df["date"] <= dd].sort_values("date")
        if df.empty:
            raise RuntimeError(f"Aucune barre IBKR <= {dd} pour {contract}")
        last = df.iloc[-1]
        return last["date"], float(last["close"])
    finally:
        if own_connection:
            ib.disconnect()


def compute_differential_ibkr(d: DateLike, coffee_type: str, price: float,
                              ib: Optional[IB] = None, host: str = "127.0.0.1",
                              port: int = 4002, client_id: int = 1) -> dict:
    """
    Comme `compute_differential`, mais va chercher lui-même le close du contrat
    associé à la date via IBKR. `ib` peut être passé pour réutiliser une connexion
    (ex. un appel arabica + un appel robusta le même jour).
    """
    contract = get_contract_for_date(d, coffee_type)
    close_date, futures_close = fetch_futures_close(contract, d, ib=ib, host=host,
                                                    port=port, client_id=client_id)
    result = compute_differential(d, coffee_type, price, futures_close)
    result["futures_close_date"] = close_date
    return result


def compute_daily_differentials(d: DateLike, arabica_price: float, robusta_price: float,
                                host: str = "127.0.0.1", port: int = 4002,
                                client_id: int = 1) -> pd.DataFrame:
    """Point d'entrée quotidien : les deux différentiels du jour en une seule connexion IBKR."""
    ib = IB()
    ib.connect(host, port, clientId=client_id)
    try:
        rows = [
            compute_differential_ibkr(d, "arabica", arabica_price, ib=ib),
            compute_differential_ibkr(d, "robusta", robusta_price, ib=ib),
        ]
    finally:
        ib.disconnect()
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Vérification sur les exemples des PDFs (sans IBKR)
# ---------------------------------------------------------------------------
if __name__ == "__main__":

    # # Robusta : 107.55 -> 1792.50 ; - 1535 = +257.50
    # r = compute_differential("2026-04-29", "robusta", 107.55, 1535)
    # print(r)
    # assert abs(r["cepea_converted"] - 1792.50) < 1e-6
    # assert abs(r["differential"] - 257.50) < 1e-6

    # # Arabica : 128.79 -> 97.3628 ; - 123.05 = -25.6872
    # a = compute_differential("2026-04-29", "arabica", 128.79, 123.05)
    # print(a)
    # assert abs(a["cepea_converted"] - 97.3628) < 1e-3
    # assert abs(a["differential"] - (-25.6872)) < 1e-3
    # assert a["contract"] == "KCN26"

    # # Bascule d'année
    # assert get_contract_for_date("2025-11-20", "arabica").ticker == "KCH26"
    # assert get_contract_for_date("2026-01-10", "arabica").ticker == "KCH26"
    # assert get_contract_for_date("2026-01-15", "arabica").ticker == "KCK26"
    # assert get_contract_for_date("2025-10-01", "robusta").ticker == "RMF26"
    # assert get_contract_for_date("2025-12-15", "robusta").ticker == "RMH26"
    # assert get_contract_for_date("2026-08-20", "robusta").ticker == "RMX26"
    # print("OK")

    import argparse

    parser = argparse.ArgumentParser(description="Différentiels CEPEA vs futures (IBKR)")
    parser.add_argument("--date", required=True, help="Date de la donnée CEPEA (YYYY-MM-DD)")
    parser.add_argument("--arabica", required=True, type=float, help="Prix CEPEA arabica (USD/sac 60kg)")
    parser.add_argument("--robusta", required=True, type=float, help="Prix CEPEA robusta (USD/sac 60kg)")
    args = parser.parse_args()

    # Nécessite IB Gateway sur 4002
    df = compute_daily_differentials(args.date, arabica_price=args.arabica, robusta_price=args.robusta)
    print(df.to_json(orient="records", date_format="iso"))
