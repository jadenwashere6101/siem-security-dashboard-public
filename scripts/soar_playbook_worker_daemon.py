from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from engines.soar_playbook_worker import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_ERROR_BACKOFF_SECONDS,
    DEFAULT_IDLE_BACKOFF_SECONDS,
    DEFAULT_JITTER_SECONDS,
    DEFAULT_POLL_INTERVAL_SECONDS,
    DEFAULT_STALE_LIMIT,
    DEFAULT_STALE_RECOVERY_INTERVAL_SECONDS,
    PlaybookWorkerConfig,
    PlaybookWorkerShutdown,
    install_shutdown_signal_handlers,
    run_playbook_worker,
)


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Run the simulation-safe SOAR playbook worker daemon."
    )
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--poll-interval", type=float, default=DEFAULT_POLL_INTERVAL_SECONDS)
    parser.add_argument("--idle-backoff", type=float, default=DEFAULT_IDLE_BACKOFF_SECONDS)
    parser.add_argument("--jitter", type=float, default=DEFAULT_JITTER_SECONDS)
    parser.add_argument("--error-backoff", type=float, default=DEFAULT_ERROR_BACKOFF_SECONDS)
    parser.add_argument(
        "--stale-recovery-interval",
        type=float,
        default=DEFAULT_STALE_RECOVERY_INTERVAL_SECONDS,
    )
    parser.add_argument("--stale-limit", type=int, default=DEFAULT_STALE_LIMIT)
    parser.add_argument("--dry-run-recovery", action="store_true", default=False)
    parser.add_argument(
        "--max-loops",
        type=int,
        default=None,
        help="Test mode: exit after this many daemon loop iterations.",
    )
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    shutdown = PlaybookWorkerShutdown()
    install_shutdown_signal_handlers(shutdown)
    stats = run_playbook_worker(
        config=PlaybookWorkerConfig(
            batch_size=args.batch_size,
            poll_interval_seconds=args.poll_interval,
            idle_backoff_seconds=args.idle_backoff,
            jitter_seconds=args.jitter,
            error_backoff_seconds=args.error_backoff,
            stale_recovery_interval_seconds=args.stale_recovery_interval,
            stale_limit=args.stale_limit,
            dry_run_recovery=args.dry_run_recovery,
            max_loops=args.max_loops,
        ),
        shutdown=shutdown,
    )
    return 0 if stats["errors"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
