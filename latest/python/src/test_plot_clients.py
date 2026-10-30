import warnings
warnings.filterwarnings("ignore", category=RuntimeWarning, module="pandas.core.nanops")
warnings.filterwarnings("ignore", category=FutureWarning)

from mvc_app.jobs import JobConfig, run_wf_update_job, get_backtest_view
from mvc_app.view import build_wf_oos_figure_from_oos, build_wf_oos_figure_price_only, export_profile_trades_csv, build_fusion_client_figure, SUGAR_STRATEGY_LABELS

from mvc_core.performances.trades_reconstruction import build_trades_dataframe, print_trades_summary
from mvc_core.engine.run.vectorized_backtest import run_fusion_backtest
from mvc_core.plotting.figures import plot_price_equity

from mvc_core.adapters.db_connection.postgres_connection import PostgresConfig, get_postgres, init_postgres
from mvc_core.adapters.IBKR.ibkr_services import fetch_and_upsert
from mvc_core.adapters.s3_AWS.s3_services import upload_file, generate_presigned_url, bulk_upload_calibrations
from mvc_core.observability import run_job, step

from dotenv import dotenv_values

import glob

def update_calibration(profile):
    job_cfg = JobConfig(profile_name=profile)
    _res = run_wf_update_job(job_cfg)


def cropped_view_client(profile):
    job_cfg = JobConfig(profile_name=profile)
    res = get_backtest_view(job_cfg)
    fig = build_wf_oos_figure_price_only(
        oos=res["oos"],
        instrument=res["instrument"],
        title_suffix="cropped calibration",
        start_date = f"2023-01-01",
        strategy_label=SUGAR_STRATEGY_LABELS.get(profile),
    )

    file_name = profile + '_client.html'
    file_path = '/tmp/' + file_name

    # auto_open=False: on the headless K8s pod, Plotly's auto_open spawns a
    # webbrowser subprocess that touches file_path in the background, racing
    # with the upload_file() call below. That race is the source of the
    # `IncompleteBody` error we saw on the S3 PutObject.
    fig.write_html(
        file_path,
        full_html=True,
        include_plotlyjs=True,
        auto_open=False,
    )

    upload_file(file_path, file_name)
    url = generate_presigned_url(file_name)
    print(url)


def cropped_view_client_fusion():
    """Fusion of the three sugar strategies; run after their calibrations."""
    fig = build_fusion_client_figure(start_date="2023-01-01")

    file_name = 'sb11_fusion_client.html'
    file_path = '/tmp/' + file_name

    fig.write_html(
        file_path,
        full_html=True,
        include_plotlyjs=True,
        auto_open=False,
    )

    upload_file(file_path, file_name)
    url = generate_presigned_url(file_name)
    print(url)


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
    with step("fetch_and_upsert", writes_data=True):
        fetch_and_upsert(nb_periods=20)

    for profile in ("wf_sb11", "wf_rsi_sb11", "sb11_rsi_fut_shifted"):
        with step(f"update_calibration({profile})"):
            update_calibration(profile)
        with step(f"cropped_view_client({profile})", writes_data=True):
            cropped_view_client(profile=profile)

    with step("cropped_view_client_fusion", writes_data=True):
        cropped_view_client_fusion()

    for profile in ("arabica_zscore_fut_shifted_wf", "robusta_zscore_fut_shifted_wf"):
        with step(f"update_calibration({profile})"):
            update_calibration(profile)
        with step(f"cropped_view_client({profile})", writes_data=True):
            cropped_view_client(profile=profile)


def main():
    run_job("[client]", run)


if __name__ == "__main__":
    main()

