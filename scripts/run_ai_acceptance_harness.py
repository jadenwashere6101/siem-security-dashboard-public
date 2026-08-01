#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"
if VENV_PYTHON.exists() and Path(sys.executable) != VENV_PYTHON:
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), *sys.argv])

from core.ai.acceptance_harness import (
    render_live_sweep_markdown,
    render_markdown_report,
    run_acceptance_harness,
    run_live_backend_sweep,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run offline Anakin AI acceptance coverage and optional live Ollama smoke checks.")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    parser.add_argument("--output", help="Optional report output path. Defaults to stdout.")
    parser.add_argument("--no-live-smoke", action="store_true", help="Skip optional live-smoke reporting entirely.")
    parser.add_argument("--live-backend-sweep", action="store_true", help="Run the explicitly gated authenticated backend sweep on the VM.")
    parser.add_argument("--base-url", default=None, help="Backend base URL for live backend sweep.")
    parser.add_argument("--session-cookie", default=None, help="Authenticated session cookie for live backend sweep. Prefer AI_ACCEPTANCE_SESSION_COOKIE.")
    parser.add_argument("--throttle-seconds", type=float, default=2.0, help="Delay between live backend sweep requests.")
    parser.add_argument(
        "--create-manual-briefing-job",
        action="store_true",
        help="Opt-in mutation for manual briefing lifecycle acceptance. Defaults to status-only inspection.",
    )
    args = parser.parse_args()

    if args.live_backend_sweep:
        result = run_live_backend_sweep(
            base_url=args.base_url,
            session_cookie=args.session_cookie,
            throttle_seconds=args.throttle_seconds,
            create_manual_briefing_job=args.create_manual_briefing_job,
        )
        rendered = json.dumps(result, indent=2, sort_keys=True) + "\n" if args.format == "json" else render_live_sweep_markdown(result)
        failed = bool(result.get("failures_by_root_cause"))
    else:
        report = run_acceptance_harness(include_live_smoke=not args.no_live_smoke)
        rendered = json.dumps(report.as_dict(), indent=2, sort_keys=True) + "\n" if args.format == "json" else render_markdown_report(report)
        failed = bool(report.failures_by_root_cause)

    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
