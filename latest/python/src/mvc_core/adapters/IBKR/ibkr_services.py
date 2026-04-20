from ib_insync import IB, ContFuture, util

import pandas as pd
import datetime

from mvc_core.adapters.db_connection.postgres_connection import get_postgres

from dotenv import dotenv_values

IBKR_TO_DB_NAME = {
    "KC": "arabica",
    "SB": "sb11",
    "RC": "robusta",
}


def get_cont_contract(asset: str):
    if asset == "KC":
        return ContFuture(symbol="KC", exchange="NYBOT")
    elif asset == "SB":
        return ContFuture(symbol="SB", exchange="NYBOT")
    elif asset == "RC":
        return ContFuture(symbol="D", exchange="ICEEUSOFT")
    else:
        raise ValueError(f"Unknown asset: {asset}")


def fetch_daily_history(ib: IB, asset: str, duration: str = "30 D", barSizeSetting: str = "1 day"):
    contract = get_cont_contract(asset)
    bars = ib.reqHistoricalData(
        contract,
        endDateTime="",
        durationStr=duration,
        barSizeSetting=barSizeSetting,
        whatToShow="TRADES",
        useRTH=False,
        formatDate=1,
    )
    return util.df(bars)


def to_db_str(value: float) -> str:
    """Convert a float price into str (cents)."""
    return str(int(round(value * 100)))


def upsert_futures_row(name: str, date: str, open_: str, high: str, low: str, close: str, volume: str):
    db = get_postgres()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")

    existing = db.select_from_query(
        f"SELECT id FROM public.data_market_intelligence_futures WHERE name = '{name}' AND date = '{date}' LIMIT 1"
    )

    if existing.empty:
        query = """
            INSERT INTO public.data_market_intelligence_futures
                (name, date, open, high, low, close, volume, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        db.execute_write_querry(query, (name, date, open_, high, low, close, volume, now, now))
    else:
        query = """
            UPDATE public.data_market_intelligence_futures
            SET open = %s, high = %s, low = %s, close = %s, volume = %s, updated_at = %s
            WHERE name = %s AND date = %s
        """
        db.execute_write_querry(query, (open_, high, low, close, volume, now, name, date))


def fetch_and_upsert():
    """
    Connect to IBKR, fetch the last 2 days of daily bars for each asset,
    and upsert T-1 (refresh yesterday) + T (today) into the database.
    """
    config = dotenv_values("/tmp/secrets/.env")

    ib = IB()
    ib.connect(config['IBGATEWAY_HOST'],config['IBGATEWAY_PORT'],clientId=1)

    date_today = datetime.datetime.now().date()
    date_yesterday = date_today - datetime.timedelta(days=1)
    results = {}

    for asset in ["KC", "SB", "RC"]:
        db_name = IBKR_TO_DB_NAME[asset]

        df = fetch_daily_history(ib, asset, duration="2 D")
        df.index = pd.to_datetime(df["date"]).dt.date

        # Upsert T-1 (yesterday) — refresh in case it was incomplete
        if date_yesterday in df.index:
            row_y = df.loc[df.index == date_yesterday].iloc[0]
            upsert_futures_row(
                name=db_name,
                date=str(date_yesterday),
                open_=to_db_str(row_y["open"]),
                high=to_db_str(row_y["high"]),
                low=to_db_str(row_y["low"]),
                close=to_db_str(row_y["close"]),
                volume=str(int(row_y["volume"])),
            )
            print(f"{asset} ({db_name}) -> upserted T-1 ({date_yesterday}): "
                  f"O={row_y['open']:.2f} H={row_y['high']:.2f} L={row_y['low']:.2f} C={row_y['close']:.2f} V={int(row_y['volume'])}")

        # Upsert T (today)
        if date_today not in df.index:
            print(f"Warning: No data for {asset} ({db_name}) on {date_today}. Skipping.")
            continue

        row = df.loc[df.index == date_today].iloc[0]
        results[asset] = row

        upsert_futures_row(
            name=db_name,
            date=str(date_today),
            open_=to_db_str(row["open"]),
            high=to_db_str(row["high"]),
            low=to_db_str(row["low"]),
            close=to_db_str(row["close"]),
            volume=str(int(row["volume"])),
        )
        print(f"{asset} ({db_name}) -> upserted T ({date_today}): "
              f"O={row['open']:.2f} H={row['high']:.2f} L={row['low']:.2f} C={row['close']:.2f} V={int(row['volume'])}")

    ib.disconnect()

    if not results:
        print(f"No data fetched for any asset on {date_today}.")
    else:
        print(f"Done. {len(results)} asset(s) upserted for {date_today}.")
