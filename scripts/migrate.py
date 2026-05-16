import argparse
import hashlib
import os
import socket
import sys
from dataclasses import dataclass
from pathlib import Path

import psycopg2


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MIGRATIONS_DIR = REPO_ROOT / "migrations"

SCHEMA_MIGRATIONS_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    id            SERIAL PRIMARY KEY,
    version       INTEGER NOT NULL UNIQUE,
    name          TEXT NOT NULL,
    applied_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    applied_by    TEXT,
    checksum      TEXT
);
"""


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    path: Path

    @property
    def display_version(self):
        return f"{self.version:04d}"

    @property
    def filename(self):
        return self.path.name


class MigrationError(Exception):
    pass


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Apply numbered SQL schema migrations.")
    parser.add_argument(
        "--db-url",
        default=None,
        help="PostgreSQL DSN. Defaults to DATABASE_URL.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print pending migrations without executing SQL.",
    )
    parser.add_argument(
        "--target",
        type=parse_target,
        default=None,
        help="Stop after applying this migration version, e.g. 0003.",
    )
    parser.add_argument(
        "--migrations-dir",
        default=str(DEFAULT_MIGRATIONS_DIR),
        help=argparse.SUPPRESS,
    )
    return parser.parse_args(argv)


def parse_target(value):
    try:
        target = int(str(value), 10)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--target must be a numeric version") from exc
    if target < 1:
        raise argparse.ArgumentTypeError("--target must be greater than zero")
    return target


def discover_migrations(migrations_dir):
    directory = Path(migrations_dir)
    if not directory.exists():
        raise MigrationError(f"Migration directory does not exist: {directory}")
    migrations = []
    for path in directory.glob("*.sql"):
        prefix, separator, slug = path.stem.partition("_")
        if not separator or len(prefix) != 4 or not prefix.isdigit() or not slug:
            raise MigrationError(
                f"Invalid migration filename '{path.name}'. Expected 0001_name.sql."
            )
        migrations.append(Migration(version=int(prefix), name=path.stem, path=path))
    migrations.sort(key=lambda migration: migration.version)
    validate_migration_sequence(migrations)
    return migrations


def validate_migration_sequence(migrations):
    if not migrations:
        return
    versions = [migration.version for migration in migrations]
    duplicates = sorted(
        {version for version in versions if versions.count(version) > 1}
    )
    if duplicates:
        formatted = ", ".join(f"{version:04d}" for version in duplicates)
        raise MigrationError(f"Duplicate migration version(s): {formatted}")
    expected = list(range(1, max(versions) + 1))
    if versions != expected:
        missing = sorted(set(expected) - set(versions))
        formatted = ", ".join(f"{version:04d}" for version in missing)
        raise MigrationError(f"Missing migration version(s): {formatted}")


def select_pending_migrations(migrations, applied_versions, target=None):
    pending = []
    for migration in migrations:
        if target is not None and migration.version > target:
            continue
        if migration.version not in applied_versions:
            pending.append(migration)
    return pending


def read_applied_versions(conn, create_table):
    with conn.cursor() as cur:
        if create_table:
            cur.execute(SCHEMA_MIGRATIONS_SQL)
            conn.commit()
        else:
            cur.execute("SELECT to_regclass('schema_migrations')")
            exists = cur.fetchone()[0] is not None
            if not exists:
                return set()
        cur.execute("SELECT version FROM schema_migrations ORDER BY version ASC")
        return {row[0] for row in cur.fetchall()}


def checksum_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as migration_file:
        for chunk in iter(lambda: migration_file.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def preview_sql(path, lines=5):
    with open(path, "r", encoding="utf-8") as migration_file:
        return "".join(migration_file.readlines()[:lines]).rstrip()


def applied_by():
    user = os.getenv("USER") or os.getenv("USERNAME") or "unknown"
    return f"{user}@{socket.gethostname()}"


def apply_migration(conn, migration):
    sql = migration.path.read_text(encoding="utf-8")
    checksum = checksum_file(migration.path)
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            cur.execute(
                """
                INSERT INTO schema_migrations (version, name, applied_by, checksum)
                VALUES (%s, %s, %s, %s)
                """,
                (migration.version, migration.name, applied_by(), checksum),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def current_version(applied_versions, applied_this_run=None):
    versions = set(applied_versions)
    if applied_this_run:
        versions.update(migration.version for migration in applied_this_run)
    return max(versions) if versions else 0


def format_version(version):
    return f"{version:04d}" if version else "0000"


def run(conn, migrations_dir=DEFAULT_MIGRATIONS_DIR, dry_run=False, target=None):
    migrations = discover_migrations(migrations_dir)
    applied_versions = read_applied_versions(conn, create_table=not dry_run)
    known_versions = {migration.version for migration in migrations}
    unknown_applied = sorted(applied_versions - known_versions)
    if unknown_applied:
        formatted = ", ".join(f"{version:04d}" for version in unknown_applied)
        raise MigrationError(f"DB has applied migration(s) missing locally: {formatted}")

    pending = select_pending_migrations(migrations, applied_versions, target=target)
    if dry_run:
        if not pending:
            print(
                f"Nothing to apply. DB at version {format_version(current_version(applied_versions))}."
            )
            return 0
        for migration in pending:
            print(f"Would apply migration {migration.display_version} {migration.name}")
            preview = preview_sql(migration.path)
            if preview:
                print(preview)
        print(
            f"Dry run complete. {len(pending)} pending migration(s). "
            f"DB at version {format_version(current_version(applied_versions))}."
        )
        return 0

    applied = []
    for migration in pending:
        print(f"Applying migration {migration.filename} ...")
        try:
            apply_migration(conn, migration)
        except Exception as exc:
            print(
                f"ERROR: Migration {migration.display_version} {migration.name} failed: {exc}",
                file=sys.stderr,
            )
            return 1
        applied.append(migration)
        print(f"Migration {migration.display_version} applied.")

    final_version = format_version(current_version(applied_versions, applied))
    if not applied:
        print(f"Nothing to apply. DB at version {final_version}.")
    else:
        print(f"Applied {len(applied)} migration(s). DB now at version {final_version}.")
    return 0


def main(argv=None):
    args = parse_args(argv)
    db_url = args.db_url or os.getenv("DATABASE_URL", "").strip()
    if not db_url:
        print("ERROR: --db-url or DATABASE_URL is required.", file=sys.stderr)
        return 1

    conn = None
    try:
        conn = psycopg2.connect(db_url)
        conn.autocommit = False
        return run(
            conn,
            migrations_dir=Path(args.migrations_dir),
            dry_run=args.dry_run,
            target=args.target,
        )
    except MigrationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"ERROR: Unable to run migrations: {exc}", file=sys.stderr)
        return 1
    finally:
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
