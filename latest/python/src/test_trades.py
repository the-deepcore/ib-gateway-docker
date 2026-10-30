import warnings
warnings.filterwarnings("ignore", category=RuntimeWarning, module="pandas.core.nanops")
warnings.filterwarnings("ignore", category=FutureWarning)

from mvc_app.view import export_profile_trades_csv, export_fusion_trades_csv
from mvc_core.adapters.db_connection.postgres_connection import PostgresConfig, get_postgres, init_postgres
from mvc_core.adapters.s3_AWS.s3_services import upload_file, generate_presigned_url
from mvc_core.adapters.IBKR.ibkr_services import fetch_and_upsert_trades, upsert_trades_csv
from mvc_core.observability import run_job, step

from dotenv import dotenv_values

def get_trades(profile: str):
    """Get trades from a walk-forward backtest profile and save to CSV."""
    file_name = f"trades_{profile}.csv"
    file_path = f"/tmp/{file_name}"
    export_profile_trades_csv(profile, file_path)
    upload_file(file_path, file_name)
    url = generate_presigned_url(file_name)
    print(url)


def get_fusion_trades():
    """Get the Fusion strategy's trades, save to CSV and upsert them into the database."""
    file_name = "trades_sb11_fusion.csv"
    file_path = f"/tmp/{file_name}"
    export_fusion_trades_csv(file_path)
    upload_file(file_path, file_name)
    url = generate_presigned_url(file_name)
    print(url)
    upsert_trades_csv("sb11_fusion", file_path)


def init_db():
    config = dotenv_values("/tmp/secrets/.env")
    pgconfig = PostgresConfig(
        host=config['POSTGRES_HOST'],
        port=int(config['POSTGRES_PORT']),
        database=config['POSTGRES_DATABASE'],
        username=config['POSTGRES_USERNAME'],
        password=config['POSTGRES_PASSWORD']
    )
    init_postgres(pgconfig)


def run():
    with step("init_db"):
        init_db()

    for profile in ("wf_sb11", "wf_rsi_sb11", "sb11_rsi_fut_shifted"):
        with step(f"get_trades({profile})", writes_data=True):
            get_trades(profile)
        with step(f"fetch_and_upsert_trades({profile})", writes_data=True):
            fetch_and_upsert_trades(profile)

    with step("get_fusion_trades", writes_data=True):
        get_fusion_trades()

    for profile in ("arabica_zscore_fut_shifted_wf", "robusta_zscore_fut_shifted_wf"):
        with step(f"get_trades({profile})", writes_data=True):
            get_trades(profile)
        with step(f"fetch_and_upsert_trades({profile})", writes_data=True):
            fetch_and_upsert_trades(profile)


def main():
    run_job("[trades]", run)


if __name__ == "__main__":
    main()

