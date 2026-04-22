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

from dotenv import dotenv_values

def init_db():
    config = dotenv_values("/tmp/secrets/.env")
    pgconfig = PostgresConfig(host=config['POSTGRES_HOST'],port=int(config['POSTGRES_PORT']),database=config['POSTGRES_DATABASE'],username=config['POSTGRES_USERNAME'],password=config['POSTGRES_PASSWORD'])
    init_postgres(pgconfig)

def get_30m_sb_data():
    config = dotenv_values("/tmp/secrets/.env")

    ib = IB()
    ib.connect(config['IBGATEWAY_HOST'],config['IBGATEWAY_PORT'],clientId=1)

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

