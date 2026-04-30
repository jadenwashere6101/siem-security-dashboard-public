#!/usr/bin/env python3

import json
import os
import sys
from pathlib import Path

import requests

# Local .log file ingestion helper.
# Reads newline-based log files, forwards each new line to /ingest/web-log, and
# tracks byte offsets to avoid duplicate ingestion across repeated runs.

STATE_FILENAME = ".ingest_state.json"
WEB_LOG_PATH = "/ingest/web-log"
REQUEST_TIMEOUT_SECONDS = 10


def print_error(message):
    print(f"Error: {message}", file=sys.stderr)


def load_config():
    ingest_dir_value = (os.environ.get("SIEM_LOG_INGEST_DIR") or "").strip()
    if not ingest_dir_value:
        raise ValueError("SIEM_LOG_INGEST_DIR is required")

    ingest_url = (os.environ.get("SIEM_LOG_INGEST_URL") or "").strip()
    if not ingest_url:
        raise ValueError("SIEM_LOG_INGEST_URL is required")

    ingest_api_key = (os.environ.get("SIEM_INGEST_API_KEY") or "").strip()
    if not ingest_api_key:
        raise ValueError("SIEM_INGEST_API_KEY is required")

    ingest_dir = Path(ingest_dir_value)
    if not ingest_dir.exists():
        raise ValueError(f"Configured log directory does not exist: {ingest_dir}")
    if not ingest_dir.is_dir():
        raise ValueError(f"Configured log path is not a directory: {ingest_dir}")

    base_url = ingest_url.rstrip("/")

    return ingest_dir, base_url, ingest_api_key


def load_state(state_path):
    if not state_path.exists():
        return {}

    try:
        with state_path.open("r", encoding="utf-8") as state_file:
            loaded = json.load(state_file)
    except (OSError, json.JSONDecodeError) as error:
        print(
            f"Warning: failed to load {state_path.name} ({type(error).__name__}: {error}); "
            "resetting all offsets to 0",
            file=sys.stderr,
        )
        return {}

    if not isinstance(loaded, dict):
        print(
            f"Warning: {state_path.name} is not a JSON object; resetting all offsets to 0",
            file=sys.stderr,
        )
        return {}

    normalized_state = {}
    for filename, offset in loaded.items():
        if not isinstance(filename, str):
            continue
        if isinstance(offset, int) and offset >= 0:
            normalized_state[filename] = offset

    return normalized_state


def write_state(state_path, state):
    with state_path.open("w", encoding="utf-8") as state_file:
        json.dump(state, state_file, indent=2, sort_keys=True)
        state_file.write("\n")


def iter_log_files(ingest_dir):
    return sorted(
        file_path
        for file_path in ingest_dir.iterdir()
        if file_path.is_file() and file_path.suffix == ".log"
    )


def post_line(base_url, api_key, line):
    response = requests.post(
        f"{base_url}{WEB_LOG_PATH}",
        headers={
            "Content-Type": "application/json",
            "X-API-Key": api_key,
        },
        json={"line": line},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    return response


def process_file(file_path, state, base_url, api_key, totals):
    filename = file_path.name
    file_size = file_path.stat().st_size
    recorded_offset = state.get(filename, 0)

    if recorded_offset > file_size:
        print(
            f"Warning: recorded offset for {filename} exceeds current file size; resetting to 0",
            file=sys.stderr,
        )
        recorded_offset = 0

    current_offset = recorded_offset
    line_index = 0

    with file_path.open("r", encoding="utf-8", errors="replace") as log_file:
        log_file.seek(recorded_offset)

        while True:
            line_start_offset = log_file.tell()
            raw_line = log_file.readline()
            if raw_line == "":
                break

            line_index += 1
            line_end_offset = log_file.tell()
            trimmed_line = raw_line.strip()

            if not trimmed_line:
                current_offset = line_end_offset
                continue

            try:
                response = post_line(base_url, api_key, trimmed_line)
            except requests.RequestException as error:
                totals["failures"] += 1
                print(
                    f"{filename}: line {line_index}: backend request failed ({type(error).__name__}: {error})",
                    file=sys.stderr,
                )
                break

            if 200 <= response.status_code < 300:
                totals["submitted"] += 1
                current_offset = line_end_offset
                continue

            if response.status_code == 400:
                totals["skipped"] += 1
                print(
                    f"{filename}: line {line_index}: malformed line skipped (400): {response.text.strip()}",
                    file=sys.stderr,
                )
                current_offset = line_end_offset
                continue

            if response.status_code in {401, 403}:
                raise PermissionError(
                    f"{filename}: line {line_index}: authentication failed with status {response.status_code}"
                )

            totals["failures"] += 1
            print(
                f"{filename}: line {line_index}: backend failure ({response.status_code}): {response.text.strip()}",
                file=sys.stderr,
            )
            break

    state[filename] = current_offset
    write_state(file_path.parent / STATE_FILENAME, state)


def main():
    try:
        ingest_dir, base_url, ingest_api_key = load_config()
    except ValueError as error:
        print_error(str(error))
        return 1

    state_path = ingest_dir / STATE_FILENAME
    state = load_state(state_path)
    totals = {
        "files_processed": 0,
        "submitted": 0,
        "skipped": 0,
        "failures": 0,
    }

    try:
        for file_path in iter_log_files(ingest_dir):
            totals["files_processed"] += 1
            process_file(file_path, state, base_url, ingest_api_key, totals)
    except PermissionError as error:
        print_error(str(error))
        return 1
    except OSError as error:
        print_error(f"File processing error: {error}")
        return 1

    print(
        "Completed log ingestion: "
        f"files processed: {totals['files_processed']}, "
        f"lines submitted: {totals['submitted']}, "
        f"lines skipped: {totals['skipped']}, "
        f"failures: {totals['failures']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
