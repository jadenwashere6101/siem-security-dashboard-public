import argparse
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
from integrations.soar_adapters.config import SoarAdapterConfig
from integrations.soar_adapters.linux_firewall import LinuxFirewallDryRunAdapter
from integrations.soar_adapters.registry import SoarAdapterRegistry

DEFAULT_BATCH_SIZE = 10
MAX_BATCH_SIZE = 50
VALID_EXECUTION_MODES = {"simulation", "real"}


def main():
    parser = argparse.ArgumentParser(description="Run one SOAR worker batch and exit.")
    parser.add_argument(
        "--batch-size",
        type=int,
        help=f"Override SOAR_RUNNER_BATCH_SIZE (1-{MAX_BATCH_SIZE})",
    )
    parser.parse_known_args()

    logging.basicConfig(level=logging.INFO)

    try:
        _ensure_not_in_flask_context()
        mode, batch_size = _load_and_validate_config()
        _print_start_header(mode, batch_size)
        database_url = _read_database_url()
        executor = _build_executor(mode)
    except RunnerConfigError as error:
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


def _load_and_validate_config():
    raw_mode = os.getenv("SOAR_EXECUTION_MODE", "simulation").strip().lower()
    if raw_mode not in VALID_EXECUTION_MODES:
        raise RunnerConfigError(
            f"SOAR_EXECUTION_MODE must be one of {sorted(VALID_EXECUTION_MODES)}; got '{raw_mode}'"
        )

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


def _print_start_header(mode, batch_size):
    started_at = datetime.now(timezone.utc).isoformat()
    print("=== SOAR Worker Runner ===")
    print(f"Mode:        {mode}")
    print(f"Batch size:  {batch_size}")
    print(f"Started at:  {started_at}")
    if mode == "real":
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


if __name__ == "__main__":
    sys.exit(main())

