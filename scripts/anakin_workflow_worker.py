from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

import psycopg2

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.ai.workflow_request_worker import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_MAX_RUNTIME_SECONDS,
    DEFAULT_STALE_RECOVERY_LIMIT,
    AnakinWorkflowWorkerConfig,
    AnakinWorkflowWorkerShutdown,
    install_shutdown_signal_handlers,
    run_anakin_workflow_worker,
)


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Run one bounded Anakin async workflow worker batch.")
    parser.add_argument("--batch-size", type=int, default=_env_int("ANAKIN_WORKFLOW_BATCH_SIZE", DEFAULT_BATCH_SIZE))
    parser.add_argument(
        "--stale-recovery-limit",
        type=int,
        default=_env_int("ANAKIN_WORKFLOW_STALE_RECOVERY_LIMIT", DEFAULT_STALE_RECOVERY_LIMIT),
    )
    parser.add_argument(
        "--max-runtime-seconds",
        type=int,
        default=_env_int("ANAKIN_WORKFLOW_MAX_RUNTIME_SECONDS", DEFAULT_MAX_RUNTIME_SECONDS),
    )
    parser.add_argument(
        "--lease-duration-seconds",
        type=int,
        default=_env_int("ANAKIN_WORKFLOW_LEASE_DURATION_SECONDS", 240),
    )
    parser.add_argument("--json", action="store_true", default=False)
    parser.add_argument("--log-level", default=os.getenv("ANAKIN_WORKFLOW_LOG_LEVEL", "INFO"))
    return parser.parse_args(argv)


def _env_int(name: str, default: int) -> int:
    try:
        return int(str(os.getenv(name, "")).strip())
    except ValueError:
        return default


def _connect():
    db_url = str(os.getenv("DATABASE_URL") or "").strip()
    if db_url:
        return psycopg2.connect(db_url)
    from core.db import get_db_connection

    return get_db_connection()


def main(argv=None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    shutdown = AnakinWorkflowWorkerShutdown()
    install_shutdown_signal_handlers(shutdown)
    try:
        from siem_backend import app

        stats = run_anakin_workflow_worker(
            config=AnakinWorkflowWorkerConfig(
                batch_size=args.batch_size,
                stale_recovery_limit=args.stale_recovery_limit,
                max_runtime_seconds=args.max_runtime_seconds,
                lease_duration_seconds=args.lease_duration_seconds,
            ),
            shutdown=shutdown,
            connect=_connect,
            flask_app=app,
        )
    except Exception as error:
        if args.json:
            print(json.dumps({"status": "failed", "error": type(error).__name__}, sort_keys=True))
        return 2

    if args.json:
        print(json.dumps({"status": "ok", "summary": stats}, default=str, sort_keys=True))
    return 0 if stats.get("errors", 0) == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
