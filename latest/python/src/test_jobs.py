import warnings
warnings.filterwarnings("ignore", category=RuntimeWarning, module="pandas.core.nanops")
warnings.filterwarnings("ignore", category=FutureWarning)

from mvc_app.jobs import JobConfig, run_wf_update_job, get_backtest_view
from mvc_app.view import build_wf_oos_figure_from_oos, build_wf_oos_figure_price_only

from mvc_core.performances.trades_reconstruction import build_trades_dataframe, print_trades_summary
from mvc_core.engine.run.vectorized_backtest import run_fusion_backtest
from mvc_core.plotting.figures import plot_price_equity

from mvc_core.adapters.db_connection.postgres_connection import PostgresConfig, init_postgres
from mvc_core.adapters.IBKR.ibkr_services import fetch_and_upsert
from mvc_core.adapters.s3_AWS.s3_services import upload_file, generate_presigned_url, bulk_upload_calibrations

from dotenv import dotenv_values


def update(profile):
    job_cfg = JobConfig(profile_name=profile)
    res = run_wf_update_job(job_cfg)
    fig = build_wf_oos_figure_from_oos(
        oos=res["oos"],
        instrument=res["instrument"],
        title_suffix="cropped period calibration",
        start_date="2023-01-01",
    )
    fig.show()


def cropped_view(profile):
    job_cfg = JobConfig(profile_name=profile)
    res = get_backtest_view(job_cfg)
    fig = build_wf_oos_figure_from_oos(
        oos=res["oos"],
        instrument=res["instrument"],
        title_suffix="cropped calibration",
        start_date = f"2023-01-01"
    )

    fig.show()

    file_name = profile + '.html'
    file_path = '/tmp/' + file_name

    fig.write_html(
        file_path,
        full_html=True,
        include_plotlyjs=True,
        auto_open=True,
    )

    upload_file(file_path, file_name)
    url = generate_presigned_url(file_name)
    print(url)


def test_fusion_strat_signals():
    profiles = ["wf_sb11", "wf_rsi_sb11", "sb11_rsi_fut_shifted"]
    thresh = 1
    instrument = "SB11"

    fusion = run_fusion_backtest(
        profile_names=profiles,
        instrument=instrument,
        initial_inv=200_000_000,
        position_notional=30_000_000,
        threshold=thresh,
        start_date="2015-01-01",
        debug=False,
    )

    fig = plot_price_equity(
        price=fusion["price_aligned"],
        equity=fusion["equity_df"],
        instrument=instrument,
        decisions=fusion["all_decisions"],
        title=f"Fusion Strategy: {' + '.join(profiles)} (full period)",
    )
    fig.show()

    trades_df = build_trades_dataframe(fusion["trade_decisions"], initial_inv=30_000_000.0, include_open_positions=True)

    print("\n=== FUSION TRADES SUMMARY ===")
    print_trades_summary(trades_df, start_date="2024-01-01", end_date="2024-12-31")
    print_trades_summary(trades_df, start_date="2025-01-01", end_date="2025-12-31")

    fusion_cropped = run_fusion_backtest(
        profile_names=profiles,
        instrument=instrument,
        initial_inv=200_000_000,
        position_notional=30_000_000,
        threshold=thresh,
        start_date="2023-01-01",
        debug=False,
    )
    fig_cropped = plot_price_equity(
        price=fusion_cropped["price_aligned"],
        equity=fusion_cropped["equity_df"],
        instrument=instrument,
        decisions=fusion_cropped["all_decisions"],
        title=f"Fusion Strategy (cropped)",
    )
    fig_cropped.show()

    return fusion


def init_db():
    config = dotenv_values("/tmp/secrets/.env")
    pgconfig = PostgresConfig(host=config['POSTGRES_HOST'],port=int(config['POSTGRES_PORT']),database=config['POSTGRES_DATABASE'],username=config['POSTGRES_USERNAME'],password=config['POSTGRES_PASSWORD'])
    init_postgres(pgconfig)


def main():
    import glob
    bulk_upload_calibrations(glob.glob("save_wf_simu/calib_temp/*.json"))

    init_db()
    fetch_and_upsert()

    profile = "wf_sb11"  # zscore-spot
    cropped_view(profile)

    profile = "wf_rsi_sb11" # rsi-spot
    cropped_view(profile)

    profile = "sb11_rsi_fut_shifted" # rsi-futures
    cropped_view(profile)

    profile = "arabica_zscore_fut_shifted_wf" # zscore
    cropped_view(profile)

    profile = "robusta_zscore_fut_shifted_wf" # zscore
    cropped_view(profile)



if __name__ == "__main__":
    main()

