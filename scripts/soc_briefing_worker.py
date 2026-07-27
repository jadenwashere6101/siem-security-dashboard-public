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

from core.ai.soc_briefing_worker import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_MATERIALIZE_LIMIT,
    DEFAULT_MAX_RUNTIME_SECONDS,
    DEFAULT_STALE_RECOVERY_LIMIT,
    SocBriefingWorkerConfig,
    SocBriefingWorkerShutdown,
    install_shutdown_signal_handlers,
    run_soc_briefing_worker,
)


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Run one bounded scheduled SOC briefing runtime batch.")
    parser.add_argument("--batch-size", type=int, default=_env_int("SOC_BRIEFING_BATCH_SIZE", DEFAULT_BATCH_SIZE))
    parser.add_argument(
        "--materialize-limit",
        type=int,
        default=_env_int("SOC_BRIEFING_MATERIALIZE_LIMIT", DEFAULT_MATERIALIZE_LIMIT),
    )
    parser.add_argument(
        "--stale-recovery-limit",
        type=int,
        default=_env_int("SOC_BRIEFING_STALE_RECOVERY_LIMIT", DEFAULT_STALE_RECOVERY_LIMIT),
    )
    parser.add_argument(
        "--max-runtime-seconds",
        type=int,
        default=_env_int("SOC_BRIEFING_MAX_RUNTIME_SECONDS", DEFAULT_MAX_RUNTIME_SECONDS),
    )
    parser.add_argument("--json", action="store_true", default=False)
    parser.add_argument("--log-level", default=os.getenv("SOC_BRIEFING_LOG_LEVEL", "INFO"))
    return parser.parse_args(argv)


def _env_int(name: str, default: int) -> int:
    try:
        return int(str(os.getenv(name, "")).strip())
    except ValueError:
        return default


def _database_url() -> str:
    return str(os.getenv("DATABASE_URL") or "").strip()


def _connect():
    db_url = _database_url()
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
    shutdown = SocBriefingWorkerShutdown()
    install_shutdown_signal_handlers(shutdown)
    try:
        stats = run_soc_briefing_worker(
            config=SocBriefingWorkerConfig(
                batch_size=args.batch_size,
                materialize_limit=args.materialize_limit,
                stale_recovery_limit=args.stale_recovery_limit,
                max_runtime_seconds=args.max_runtime_seconds,
            ),
            shutdown=shutdown,
            connect=_connect,
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
