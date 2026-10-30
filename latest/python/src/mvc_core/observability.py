"""Observability helpers shared by the top-level job scripts.

Three building blocks:

  - ``step(name, writes_data=...)`` — a context manager wrapped around every
    top-level operation in ``main()``. It logs start/end/duration and tracks
    which steps completed and which ones wrote user-facing data.
  - ``write_crash_report`` / ``write_run_report`` — persist a text blob to
    S3 under ``mi_crashes/<slug>.txt`` so the full stdout tail + stack +
    environment survives a pod reload (the AKS cluster has no Container
    Insights, so stdout alone is lost once the pod goes).
  - ``format_failure_message`` / ``format_success_message`` — Slack text
    readable at a glance: a one-line header, the step we failed on, an
    ``Impact`` line that says whether the data was updated before the crash
    or not, a link to the full report, and the traceback tail.
  - ``send_slack_notification`` — the one Slack poster every script and
    app.py share; prefixes ``[staging]`` on staging.
  - ``run_job(label, body)`` — the wrapper every script's ``main()`` uses:
    stdout capture, report and Slack message around the job's steps.
"""
from __future__ import annotations

import contextlib
from typing import Callable
import datetime as _dt
import functools
import io
import os
import socket
import sys
import threading
import time
import traceback

from dotenv import dotenv_values
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# boto3 is heavy: import it lazily inside _s3_client so this module can be
# imported for unit tests on a machine where it is not installed.


# Slack's text field accepts up to 40k chars; this leaves plenty of room for
# the actual stack frames while staying well inside the limit.
TRACEBACK_SLACK_LIMIT = 3500

# Tail of stdout we keep in memory in case the pod is reloaded before anyone
# reads the live logs. Attached verbatim to the crash report.
STDOUT_BUFFER_BYTES = 60_000

# Mounted Kubernetes Secret holding the Slack / S3 / DB settings.
SECRETS_PATH = "/tmp/secrets/.env"

# S3 prefix under the shared bucket where crash + run reports live. The Rails
# admin page reads from the same prefix.
S3_REPORTS_PREFIX = "mi_crashes"

# Only these keys from /tmp/secrets/.env end up in a crash report. Everything
# else is treated as a secret.
SAFE_ENV_KEYS = (
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "POSTGRES_DATABASE",
    "S3_PREFIX",
    "SLACK_CHANNEL",
    "SLACK_USERNAME",
    "COMPASS_URL",
    "COMPASS_INDEX",
    "THEDEEPCORE_URL",
    "AWS_REGION",
    "AWS_BUCKET",
    "ADMIN_LOGS_BASE_URL",
)


class _RunState:
    """Per-process accumulator for everything the Slack / report formatters
    need to describe the run so far."""

    def __init__(self) -> None:
        # (name, elapsed_s) for every step that completed without raising.
        self.steps_ok: list[tuple[str, float]] = []
        # Names of completed steps marked writes_data=True, in order.
        self.data_updates: list[str] = []
        # The step currently running (set by the context manager on entry,
        # left in place after a failure so the formatter can report it).
        self.current_step: str | None = None
        self.started_at = time.monotonic()


# Each ``os.system('python3 /app/src/test_*.py')`` call from app.py spawns
# a fresh interpreter, so this module-level state only ever covers one run.
_RUN_STATE = _RunState()
_STDOUT_BUFFER = io.StringIO()
# Guards the shared buffer only, so concurrent writers (future Flask / threaded
# callers) can't interleave or race the trim. Terminal passthrough stays
# outside the lock to avoid serializing stdout.
_BUFFER_LOCK = threading.Lock()


class _TeeStream:
    """File-like wrapper that writes to the real stream AND keeps a bounded
    tail in memory. We attach the tail verbatim to the crash report so a
    pod reload no longer eats the diagnostic context."""

    def __init__(self, inner):
        self.inner = inner

    def write(self, data: str) -> int:
        written = self.inner.write(data)
        # Only the shared buffer needs serialization; the terminal passthrough
        # above stays lock-free.
        with _BUFFER_LOCK:
            _STDOUT_BUFFER.write(data)
            # Trim from the head when we grow past 2x the target size, to
            # avoid trimming on every write.
            if _STDOUT_BUFFER.tell() > STDOUT_BUFFER_BYTES * 2:
                tail = _STDOUT_BUFFER.getvalue()[-STDOUT_BUFFER_BYTES:]
                _STDOUT_BUFFER.seek(0)
                _STDOUT_BUFFER.truncate(0)
                _STDOUT_BUFFER.write(tail)
        return written

    def writelines(self, lines) -> None:
        # Route through write() so these lines reach the buffer too instead
        # of going straight to the inner stream via __getattr__.
        for line in lines:
            self.write(line)

    def flush(self) -> None:
        self.inner.flush()

    def __getattr__(self, name):
        # Delegate everything else (fileno, isatty, ...) to the underlying
        # stream so libraries that introspect sys.stdout still work.
        return getattr(self.inner, name)


def install_stdout_capture() -> None:
    """Pipe stdout + stderr through the tee buffer. Call this at the top of
    each top-level script's ``main()``, before anything else prints."""
    if not isinstance(sys.stdout, _TeeStream):
        sys.stdout = _TeeStream(sys.stdout)
    if not isinstance(sys.stderr, _TeeStream):
        sys.stderr = _TeeStream(sys.stderr)


@contextlib.contextmanager
def step(name: str, *, writes_data: bool = False):
    """Wrap a top-level operation. Logs start / duration, records completion
    into ``_RUN_STATE``, and leaves ``current_step`` on failure so the Slack
    message can name it. ``writes_data=True`` marks steps whose completion
    means user-facing artefacts (DB rows, S3 files, Compass allocations)
    have been published; drives the ``Impact`` line."""
    _RUN_STATE.current_step = name
    started = time.monotonic()
    print(f"[step={name}] start", flush=True)
    try:
        yield
    except Exception:
        elapsed = time.monotonic() - started
        print(f"[step={name}] FAILED in {elapsed:.2f}s", flush=True)
        raise
    else:
        elapsed = time.monotonic() - started
        _RUN_STATE.steps_ok.append((name, elapsed))
        if writes_data:
            _RUN_STATE.data_updates.append(name)
        print(f"[step={name}] done in {elapsed:.2f}s", flush=True)


def record_data_update(name: str) -> None:
    """Append to the ``data_updates`` tally after the fact. For callers that
    can only decide whether a step actually published something based on its
    return value (e.g. compass's post_latest_trade distinguishes a real new
    allocation from "already covered" / "nothing new")."""
    _RUN_STATE.data_updates.append(name)


@functools.lru_cache(maxsize=1)
def _config() -> dict:
    # Memoized: /tmp/secrets/.env is a mounted Kubernetes Secret, immutable
    # for the lifetime of the pod. Reading it on every helper call (env tag,
    # S3 client, bucket, admin URL, env dump) was wasted disk I/O.
    if not os.path.exists(SECRETS_PATH):
        # dotenv_values() returns {} for a missing file; say so once here
        # rather than leave a bare KeyError further down.
        print(f"[observability] {SECRETS_PATH} not found: no Slack message, no S3 report", flush=True)
    return dict(dotenv_values(SECRETS_PATH))


def _env_tag() -> str:
    """``[staging] `` on staging (from ``S3_PREFIX``), empty on production."""
    env = (_config().get("S3_PREFIX") or "").strip("/")
    return f"[{env}] " if env else ""


@functools.lru_cache(maxsize=1)
def _s3_client():
    # Memoized: boto3 clients hold their own connection pool, no reason to
    # rebuild one per report.
    import boto3
    cfg = _config()
    return boto3.client(
        "s3",
        region_name=cfg.get("AWS_REGION") or os.environ.get("AWS_REGION", "eu-west-3"),
        aws_access_key_id=cfg.get("S3_ACCESS_KEY") or os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=cfg.get("S3_SECRET_KEY") or os.environ.get("AWS_SECRET_ACCESS_KEY"),
    )


def _bucket() -> str:
    cfg = _config()
    return cfg.get("AWS_BUCKET") or cfg.get("S3_BUCKET") or "thedeepcore"


def _slug(label: str, status: str, when: _dt.datetime) -> str:
    """URL-safe slug used as both the S3 key stem and the admin route id.

    Encodes the status (``ok`` / ``failed``) so the admin index can render
    it from the key listing alone, without fetching every object.

    Example: ``2026-10-29T16-00-15Z-client-failed``.
    """
    stem = when.strftime("%Y-%m-%dT%H-%M-%SZ")
    clean_label = "".join(c for c in label if c.isalnum() or c in ("-", "_")).strip("-_")
    status_slug = status.lower()
    parts = [stem]
    if clean_label:
        parts.append(clean_label)
    parts.append(status_slug)
    return "-".join(parts)


def _admin_url(slug: str) -> str | None:
    cfg = _config()
    base = cfg.get("ADMIN_LOGS_BASE_URL") or os.environ.get("ADMIN_LOGS_BASE_URL")
    if not base:
        return None
    return f"{base.rstrip('/')}/{slug}"


def _env_dump() -> str:
    """Values of SAFE_ENV_KEYS only. The other keys are listed by name, never
    by value, so a setting missing from the allowlist is still visible in
    the report without risking a secret."""
    cfg = _config()
    lines = [f"{k}={cfg.get(k, '')}" for k in SAFE_ENV_KEYS]
    other_keys = sorted(k for k in cfg if k not in SAFE_ENV_KEYS)
    if other_keys:
        lines.append(f"(values withheld: {', '.join(other_keys)})")
    return "\n".join(lines)


def _progress_line() -> str:
    """Human-readable summary of what was published before the crash.
    Used verbatim in the Slack ``Impact`` field and in the report body."""
    data_updates = _RUN_STATE.data_updates
    if not data_updates:
        return "AUCUNE donnée publiée. Utilisateurs voient l'ancien contenu S3."
    return f"{len(data_updates)} étape(s) data OK avant crash : {', '.join(data_updates)}."


def _put_report(slug: str, body: str) -> bool:
    """Write ``body`` to ``s3://<bucket>/<prefix>/<slug>.txt``. Never raises:
    an upload failure must not add noise on top of the real problem."""
    key = f"{S3_REPORTS_PREFIX}/{slug}.txt"
    try:
        _s3_client().put_object(
            Bucket=_bucket(),
            Key=key,
            Body=body.encode("utf-8"),
            ContentType="text/plain; charset=utf-8",
        )
        return True
    except Exception as exc:
        # Never let the report upload failure mask the real problem.
        print(f"[observability] report upload failed: {exc}", flush=True)
        return False


def _report_body(*, status: str, label: str, exception: BaseException | None) -> str:
    now = _dt.datetime.now(_dt.timezone.utc).isoformat()
    elapsed = time.monotonic() - _RUN_STATE.started_at
    steps = ", ".join(f"{name}({elapsed:.2f}s)" for name, elapsed in _RUN_STATE.steps_ok) or "(none)"
    # Same lock as _TeeStream.write, so a concurrent write or trim can't
    # hand us a half-trimmed buffer.
    with _BUFFER_LOCK:
        stdout_tail = _STDOUT_BUFFER.getvalue().rstrip()

    sections = [
        "# Report",
        f"status          : {status}",
        f"label           : {label}",
        f"timestamp_utc   : {now}",
        f"pod_hostname    : {socket.gethostname()}",
        f"run_elapsed_s   : {elapsed:.2f}",
    ]

    if exception is not None:
        sections.extend([
            f"current_step    : {_RUN_STATE.current_step or '(none)'}",
            f"exception       : {type(exception).__name__}: {exception}",
        ])

    sections.extend([
        "",
        "# Progress",
        _progress_line(),
        f"All steps OK    : {steps}",
        "",
        "# Env (non-secret keys)",
        _env_dump(),
        "",
        f"# Last ~{STDOUT_BUFFER_BYTES} bytes of stdout",
        stdout_tail or "(empty)",
    ])

    if exception is not None:
        sections.extend([
            "",
            "# Full traceback",
            traceback.format_exc().rstrip(),
        ])

    return "\n".join(sections) + "\n"


def write_crash_report(label: str, exception: BaseException) -> tuple[str, str | None]:
    """Write the failure report to S3 and return (slug, admin_url)."""
    now = _dt.datetime.now(_dt.timezone.utc)
    slug = _slug(label, "failed", now)
    body = _report_body(status="FAILED", label=label, exception=exception)
    if not _put_report(slug, body):
        return slug, None
    return slug, _admin_url(slug)


def write_run_report(label: str) -> tuple[str, str | None]:
    """Write the success report to S3 and return (slug, admin_url). Called
    on every ✅ so the admin page has a full history, not just the crashes."""
    now = _dt.datetime.now(_dt.timezone.utc)
    slug = _slug(label, "ok", now)
    body = _report_body(status="OK", label=label, exception=None)
    if not _put_report(slug, body):
        return slug, None
    return slug, _admin_url(slug)


def _format_header(icon: str, label: str) -> str:
    # No [staging] tag here: send_slack_notification adds it.
    now = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    return f"{icon} {label} @ {now}"


def format_failure_message(label: str, exception: BaseException,
                           admin_url: str | None = None) -> str:
    """Rich Slack text for a top-level script failure, built to read at a
    glance in a crowded channel."""
    tb = traceback.format_exc()
    print(tb, flush=True)

    elapsed = time.monotonic() - _RUN_STATE.started_at
    lines = [
        _format_header("🔴", f"{label} FAILED"),
        f"Step   : {_RUN_STATE.current_step or '(unknown)'}",
        f"Elapsed: {elapsed:.1f}s",
        f"Pod    : {socket.gethostname()}",
        f"Error  : {type(exception).__name__}: {exception}",
        f"Impact : {_progress_line()}",
    ]
    if admin_url:
        lines.append(f"Détail : {admin_url}")
    lines.append(f"```\n{tb[-TRACEBACK_SLACK_LIMIT:]}\n```")
    return "\n".join(lines)


def format_success_message(label: str, note: str | None = None,
                           admin_url: str | None = None) -> str:
    """Rich Slack text for a successful run. ``note`` is a one-line summary
    the caller wants on top of the Published / No-data line (compass uses it
    for "already covered" / "nothing new")."""
    elapsed = time.monotonic() - _RUN_STATE.started_at
    lines = [_format_header("🟢", f"{label} OK — in {elapsed:.0f}s")]
    if note:
        lines.append(note)
    data_updates = _RUN_STATE.data_updates
    if data_updates:
        lines.append(f"Published {len(data_updates)}: {', '.join(data_updates)}.")
    elif not note:
        # Only state the no-op when we don't already have a note explaining
        # the outcome; otherwise it reads as redundant.
        lines.append("No data-writing step ran.")
    if admin_url:
        lines.append(f"Détail : {admin_url}")
    return "\n".join(lines)


def send_slack_notification(message: str) -> None:
    """Post ``message`` to the configured Slack channel, tagged ``[staging]``
    on staging so its alerts can't be mistaken for production's. Never
    raises: a Slack outage must not fail the job."""
    cfg = _config()
    missing = [key for key in ("SLACK_TOKEN", "SLACK_CHANNEL", "SLACK_USERNAME") if not cfg.get(key)]
    if missing:
        print(f"[observability] Slack notification not sent, {', '.join(missing)} missing "
              f"from {SECRETS_PATH}: {message}", flush=True)
        return
    try:
        WebClient(token=cfg["SLACK_TOKEN"]).chat_postMessage(
            channel=cfg["SLACK_CHANNEL"],
            text=f"{_env_tag()}{message}",
            username=cfg["SLACK_USERNAME"],
        )
    except SlackApiError as exc:
        print(f"[observability] Slack notification failed: {exc}", flush=True)


def run_job(label: str, body: Callable[[], str | None]) -> bool:
    """Run one top-level job the way every script needs it: capture stdout,
    run ``body``, then write the S3 run / crash report and post the matching
    Slack message. ``body`` may return a one-line note for the success
    message (compass uses it for the allocation outcome).

    Returns True on success, False if ``body`` raised (already reported, so
    callers only map it to an exit code)."""
    install_stdout_capture()
    try:
        note = body()
    except Exception as exc:
        # Both helpers read the active traceback: keep them inside except.
        _, admin_url = write_crash_report(label, exc)
        send_slack_notification(format_failure_message(label, exc, admin_url=admin_url))
        return False
    _, admin_url = write_run_report(label)
    send_slack_notification(format_success_message(label, note=note, admin_url=admin_url))
    return True
