import argparse
import json
import logging
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor

# Ensure repo root is importable when invoked as a script path.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from engines.soar_action_worker import process_batch
from engines.soar_executor import AdapterBackedExecutor, SimulationExecutor
from core.response_action_queue_store import get_queue_status_counts
from integrations.soar_adapters.config import SoarAdapterConfig
from integrations.soar_adapters.linux_firewall import LinuxFirewallDryRunAdapter
from integrations.soar_adapters.registry import SoarAdapterRegistry

DEFAULT_BATCH_SIZE = 10
MAX_BATCH_SIZE = 50
VALID_EXECUTION_MODES = {"simulation", "real"}
_KNOWN_STATUSES = ["pending", "running", "awaiting_approval", "failed", "skipped", "success"]


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Run one SOAR worker batch and exit.")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help=f"Override SOAR_RUNNER_BATCH_SIZE (1-{MAX_BATCH_SIZE})",
    )
    parser.add_argument(
        "--mode",
        choices=["simulation", "real"],
        default=None,
        help="Execution mode. Overrides SOAR_EXECUTION_MODE.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Emit all output as a single JSON object to stdout.",
    )
    parser.add_argument(
        "--dry-run-info",
        action="store_true",
        default=False,
        help="Print queue status counts and exit without processing any actions.",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv)
    logging.basicConfig(level=logging.INFO)

    try:
        _ensure_not_in_flask_context()
        if args.dry_run_info:
            return _run_dry_run_info(args)
        mode, batch_size = _load_and_validate_config(args)
        header = _build_header_dict(mode, batch_size)
        _print_start_header(header, json_mode=args.json)
        database_url = _read_database_url()
        executor = _build_executor(mode)
    except RunnerConfigError as error:
        if args.json:
            print(json.dumps({"error": str(error)}))
        else:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    conn = None
    try:
        conn = psycopg2.connect(database_url, cursor_factory=RealDictCursor)
        conn.autocommit = False
    except Exception as error:
        print(f"ERROR: Unable to connect to database: {error}", file=sys.stderr)
        return 1

    try:
        results = process_batch(conn, limit=batch_size, executor=executor)
        counts = _aggregate_results(results)
        if args.json:
            print(
                json.dumps(
                    {
                        "mode": mode,
                        "batch_size": batch_size,
                        "started_at": header["started_at"],
                        "results": results,
                        "summary": counts,
                    },
                    default=str,
                )
            )
        else:
            _print_summary(counts)
        return 0
    except Exception:
        traceback.print_exc()
        return 2
    finally:
        if conn is not None:
            conn.close()


class RunnerConfigError(Exception):
    pass


def _ensure_not_in_flask_context():
    try:
        from flask import current_app

        current_app._get_current_object()
        raise RunnerConfigError(
            "soar_worker_run must not be invoked from inside a Flask request context."
        )
    except RuntimeError:
        return


def _load_and_validate_config(args):
    raw_mode = (args.mode or os.getenv("SOAR_EXECUTION_MODE", "simulation")).strip().lower()
    if raw_mode not in VALID_EXECUTION_MODES:
        raise RunnerConfigError(
            f"SOAR_EXECUTION_MODE must be one of {sorted(VALID_EXECUTION_MODES)}; got '{raw_mode}'"
        )

    if args.batch_size is not None:
        raw_batch_size = str(args.batch_size)
    else:
        raw_batch_size = os.getenv("SOAR_RUNNER_BATCH_SIZE", str(DEFAULT_BATCH_SIZE)).strip()
    try:
        batch_size = int(raw_batch_size)
    except ValueError as error:
        raise RunnerConfigError("SOAR_RUNNER_BATCH_SIZE must be an integer") from error

    if batch_size < 1:
        raise RunnerConfigError("SOAR_RUNNER_BATCH_SIZE must be >= 1")

    if batch_size > MAX_BATCH_SIZE:
        logging.warning(
            "SOAR_RUNNER_BATCH_SIZE=%s exceeds max %s; clamping to %s",
            batch_size,
            MAX_BATCH_SIZE,
            MAX_BATCH_SIZE,
        )
        batch_size = MAX_BATCH_SIZE

    return raw_mode, batch_size


def _read_database_url():
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise RunnerConfigError("DATABASE_URL is required")
    return database_url


def _build_executor(mode):
    if mode == "simulation":
        return SimulationExecutor()

    if mode == "real":
        config = SoarAdapterConfig(
            execution_mode="real",
            action_to_adapter={"block_ip": os.getenv("SOAR_ADAPTER_BLOCK_IP", "").strip()},
            timeout_seconds=5,
            adapter_enabled={
                "linux_firewall_dry_run": os.getenv(
                    "SOAR_LINUX_FIREWALL_DRY_RUN_ENABLED", ""
                ).strip().lower()
                in {"1", "true", "yes", "on"}
            },
        )
        registry = SoarAdapterRegistry(config=config)
        registry.register(
            "linux_firewall_dry_run",
            LinuxFirewallDryRunAdapter(
                config={
                    "enabled": os.getenv("SOAR_LINUX_FIREWALL_DRY_RUN_ENABLED", "").strip().lower()
                    in {"1", "true", "yes", "on"},
                    "firewall_tool": os.getenv("SOAR_LINUX_FIREWALL_TOOL", "ufw"),
                }
            ),
        )
        return AdapterBackedExecutor(registry)

    raise RunnerConfigError(f"Unknown execution mode: {mode}")


def _aggregate_results(results):
    if not isinstance(results, list):
        raise Exception("process_batch must return a list")
    for item in results:
        if not isinstance(item, dict):
            raise Exception("process_batch result items must be dicts")
        if "outcome" not in item:
            raise Exception("process_batch result item missing outcome")

    return {
        "processed": len(results),
        "success": sum(1 for row in results if row.get("outcome") == "success"),
        "failed": sum(1 for row in results if row.get("outcome") == "failed"),
        "skipped": sum(1 for row in results if row.get("outcome") == "skipped"),
        "requeued": sum(1 for row in results if row.get("outcome") == "requeued"),
    }


def _build_header_dict(mode, batch_size):
    started_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return {"mode": mode, "batch_size": batch_size, "started_at": started_at}


def _print_start_header(header, json_mode=False):
    if json_mode:
        return
    print("=== SOAR Worker Runner ===")
    print(f"Mode:        {header['mode']}")
    print(f"Batch size:  {header['batch_size']}")
    print(f"Started at:  {header['started_at']}")
    if header["mode"] == "real":
        print("WARNING: Real execution mode is active. Actions will be dispatched to adapters.")
    print("=========================")


def _print_summary(counts):
    print("--- SOAR Runner Summary ---")
    if counts["processed"] == 0:
        print("Processed:  0 (queue empty or all actions in terminal state)")
        print("Done.")
        return

    print(f"Processed:  {counts['processed']}")
    print(f"  Success:  {counts['success']}")
    print(f"  Failed:   {counts['failed']}")
    print(f"  Skipped:  {counts['skipped']}")
    print(f"  Requeued: {counts['requeued']}")
    print("Done.")


def _normalize_queue_counts(raw):
    return {status: raw.get(status, 0) for status in _KNOWN_STATUSES}


def _run_dry_run_info(args):
    try:
        database_url = _read_database_url()
    except RunnerConfigError as error:
        if args.json:
            print(json.dumps({"error": str(error)}))
        else:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    conn = None
    try:
        conn = psycopg2.connect(database_url, cursor_factory=RealDictCursor)
        conn.autocommit = False
        raw_counts = get_queue_status_counts(conn)
        counts = _normalize_queue_counts(raw_counts)

        if args.json:
            print(json.dumps({"mode": "dry_run_info", "queue_counts": counts}))
        else:
            print("=== SOAR Queue Status ===")
            print(f"  Pending:  {counts['pending']}")
            print(f"  Running:  {counts['running']}")
            print(f"  Awaiting approval: {counts['awaiting_approval']}")
            print(f"  Failed:   {counts['failed']}")
            print(f"  Skipped:  {counts['skipped']}")
            print(f"  Success:  {counts['success']}")
            print("=========================")
        return 0
    except Exception as error:
        if args.json:
            print(json.dumps({"error": str(error)}))
        else:
            print(f"ERROR: Unable to read queue status: {error}", file=sys.stderr)
        return 1
    finally:
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    sys.exit(main())
