import argparse
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MIGRATIONS_DIR = REPO_ROOT / "migrations"
DEFAULT_SCHEMA_FILE = REPO_ROOT / "schema.sql"

MIGRATION_FILENAME_RE = re.compile(r"^(?P<version>\d{4})_[a-z0-9_]+\.sql$")
SCHEMA_MARKER_RE = re.compile(
    r"^\s*--\s*Schema snapshot version:\s*(?P<version>\d{4})\s*$",
    re.MULTILINE,
)


class SchemaSnapshotValidationError(Exception):
    pass


def _resolve_repo_path(path, *, expected_name=None):
    resolved = Path(path).expanduser().resolve()
    try:
        resolved.relative_to(REPO_ROOT)
    except ValueError as exc:
        raise SchemaSnapshotValidationError(
            f"Path must stay within repository root: {path}"
        ) from exc
    if expected_name and resolved.name != expected_name:
        raise SchemaSnapshotValidationError(
            f"Expected {expected_name}, got {resolved.name}"
        )
    return resolved


def highest_migration_version(migrations_dir):
    versions = []
    for path in Path(migrations_dir).glob("*.sql"):
        match = MIGRATION_FILENAME_RE.match(path.name)
        if match:
            versions.append(int(match.group("version")))
    if not versions:
        raise SchemaSnapshotValidationError(
            f"No migration files found in {migrations_dir}"
        )
    return max(versions)


def schema_snapshot_version(schema_file):
    text = Path(schema_file).read_text(encoding="utf-8")
    match = SCHEMA_MARKER_RE.search(text)
    if not match:
        raise SchemaSnapshotValidationError(
            f"Missing schema snapshot marker in {schema_file}. "
            "Expected: -- Schema snapshot version: NNNN"
        )
    return int(match.group("version"))


def validate_schema_snapshot(schema_file=DEFAULT_SCHEMA_FILE, migrations_dir=DEFAULT_MIGRATIONS_DIR):
    migration_version = highest_migration_version(migrations_dir)
    snapshot_version = schema_snapshot_version(schema_file)
    if snapshot_version != migration_version:
        raise SchemaSnapshotValidationError(
            "schema.sql snapshot version does not match latest migration: "
            f"schema.sql={snapshot_version:04d}, migrations={migration_version:04d}"
        )
    return snapshot_version


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Validate schema.sql snapshot marker matches latest migration version."
    )
    parser.add_argument(
        "--schema-file",
        default=str(DEFAULT_SCHEMA_FILE),
        help="Path to schema.sql. Defaults to repo-root schema.sql.",
    )
    parser.add_argument(
        "--migrations-dir",
        default=str(DEFAULT_MIGRATIONS_DIR),
        help="Path to migrations directory. Defaults to repo-root migrations/.",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        version = validate_schema_snapshot(
            schema_file=_resolve_repo_path(args.schema_file, expected_name="schema.sql"),
            migrations_dir=_resolve_repo_path(args.migrations_dir),
        )
    except SchemaSnapshotValidationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"schema.sql snapshot version matches latest migration: {version:04d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
