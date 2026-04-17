from ib_insync import IB, util

import os
import pandas as pd
import datetime

from mvc_core.adapters.IBKR.ibkr_services import (
    get_cont_contract,
    fetch_daily_history,
    fetch_and_upsert,
    IBKR_TO_DB_NAME,
)
from mvc_core.adapters.db_connection.postgres_connection import PostgresConfig, init_postgres
from mvc_core.adapters.db_connection import config


def init_db():
    pg_config = PostgresConfig(
        host=config.PGHOST,
        port=config.PGPORT,
        database=config.PGDATABASE,
        username=config.PGUSER,
        password=config.PGPASSWORD,
    )
    init_postgres(pg_config)

from mvc_core.adapters.IBKR import config as ibkr_config

def get_30m_sb_data():
    # ib = IB()
    # ib.connect("127.0.0.1", 4002, clientId=1)
    ib = IB()
    ib.connect(ibkr_config.HOST, ibkr_config.PORT, clientId=1)

    # n_year_ago = (datetime.datetime.now() - datetime.timedelta(days=365)).strftime("%Y%m%d-%H:%M:%S")
    contract = get_cont_contract("SB")
    bars_prev = ib.reqHistoricalData(
        contract,
        endDateTime="",
        durationStr="5 D",
        barSizeSetting="30 mins",
        whatToShow="TRADES",
        useRTH=False,
        formatDate=1,
    )
    df_prev = util.df(bars_prev)

    ib.disconnect()


    return df_prev




def main():
    # init_db()
    # fetch_and_upsert()

    df = get_30m_sb_data()
    print(df)
    for col in df.select_dtypes(include=["datetimetz"]).columns:
        df[col] = df[col].dt.tz_convert("Europe/Paris").dt.tz_localize(None)
    df.to_excel("sb_30m_data.xlsx", index=False)
    print("Saved to sb_30m_data.xlsx")


if __name__ == "__main__":
    main()

