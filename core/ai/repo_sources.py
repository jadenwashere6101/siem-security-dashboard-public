from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

TRUST_TIER_POLICY = 0
TRUST_TIER_CURRENT_SOURCE = 1
TRUST_TIER_CURRENT_DOCS = 2
TRUST_TIER_HISTORICAL = 3

LABEL_CURRENT = "current"
LABEL_HISTORICAL = "historical"

MAX_INDEXED_FILE_BYTES = 220_000

_TIER_0_FILES = {
    "AGENTS.md",
    "docs/mac-vm-source-of-truth-policy.md",
    "openspec/config.yaml",
    "openspec/spec-index.md",
}

_CURRENT_SOURCE_DIRS = (
    "core",
    "routes",
    "engines",
    "helpers",
    "adapters",
    "integrations",
    "scripts",
    "migrations",
)
_CURRENT_SOURCE_FILES = {"siem_backend.py", "schema.sql"}
_CURRENT_SOURCE_SUFFIXES = {".py", ".js", ".jsx", ".sql", ".yaml", ".yml", ".json"}
_DOC_SUFFIXES = {".md", ".txt", ".yaml", ".yml"}
_BINARY_OR_GENERATED_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".svg",
    ".ico",
    ".pdf",
    ".zip",
    ".gz",
    ".sqlite",
    ".db",
    ".pyc",
    ".map",
}
_EXCLUDED_PARTS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    "node_modules",
    "build",
    "coverage",
    ".mypy_cache",
    ".ruff_cache",
}
_SECRET_FILE_NAMES = {
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
    "id_rsa",
    "id_ed25519",
}
_SECRET_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".crt"}
_LOG_SUFFIXES = {".log"}
_GENERATED_REPORT_MARKERS = ("sonar", "coverage", "screenshot")
_HISTORICAL_MARKERS = (
    "handoff",
    "archive",
    "archived",
    "decomposition",
    "cleanup",
    "old",
    "legacy",
)


@dataclass(frozen=True)
class RepoFileClassification:
    path: str
    trust_tier: int
    source_kind: str
    label: str
    reason: str

    @property
    def is_historical(self) -> bool:
        return self.label == LABEL_HISTORICAL


@dataclass(frozen=True)
class ExcludedRepoPath:
    path: str
    reason: str


def normalize_repo_path(path: str | PurePosixPath) -> str:
    normalized = str(path).replace("\\", "/").strip("/")
    return "." if normalized in {"", "."} else normalized


def classify_repo_path(path: str, *, size: int | None = None) -> RepoFileClassification | None:
    normalized = normalize_repo_path(path)
    exclusion = excluded_repo_path(normalized, size=size)
    if exclusion:
        return None

    posix = PurePosixPath(normalized)
    suffix = posix.suffix.lower()
    parts = posix.parts
    lower_path = normalized.lower()

    if normalized in _TIER_0_FILES:
        return RepoFileClassification(normalized, TRUST_TIER_POLICY, "policy", LABEL_CURRENT, "tier_0_policy")

    if normalized in _CURRENT_SOURCE_FILES:
        return RepoFileClassification(normalized, TRUST_TIER_CURRENT_SOURCE, "source", LABEL_CURRENT, "current_source_file")

    if parts and parts[0] in _CURRENT_SOURCE_DIRS and suffix in _CURRENT_SOURCE_SUFFIXES:
        return RepoFileClassification(normalized, TRUST_TIER_CURRENT_SOURCE, "source", LABEL_CURRENT, "current_source_dir")

    if parts[:2] == ("frontend", "src") and suffix in _CURRENT_SOURCE_SUFFIXES:
        return RepoFileClassification(normalized, TRUST_TIER_CURRENT_SOURCE, "source", LABEL_CURRENT, "frontend_source")

    if parts and parts[0] == "tests" and suffix in {".py", ".sql", ".md"}:
        return RepoFileClassification(normalized, TRUST_TIER_CURRENT_SOURCE, "test", LABEL_CURRENT, "focused_tests")

    if parts and parts[0] == "openspec":
        if len(parts) > 1 and parts[1] == "archive":
            return RepoFileClassification(normalized, TRUST_TIER_HISTORICAL, "openspec", LABEL_HISTORICAL, "archived_openspec")
        if suffix in _DOC_SUFFIXES:
            return RepoFileClassification(normalized, TRUST_TIER_CURRENT_DOCS, "openspec", LABEL_CURRENT, "active_or_accepted_openspec")

    if parts and parts[0] == "docs" and suffix in _DOC_SUFFIXES:
        historical = _is_historical_doc(lower_path)
        return RepoFileClassification(
            normalized,
            TRUST_TIER_HISTORICAL if historical else TRUST_TIER_CURRENT_DOCS,
            "doc",
            LABEL_HISTORICAL if historical else LABEL_CURRENT,
            "historical_doc" if historical else "current_doc",
        )

    if normalized == "README.md":
        return RepoFileClassification(normalized, TRUST_TIER_CURRENT_DOCS, "doc", LABEL_CURRENT, "readme")

    return None


def excluded_repo_path(path: str, *, size: int | None = None) -> ExcludedRepoPath | None:
    normalized = normalize_repo_path(path)
    posix = PurePosixPath(normalized)
    parts = set(posix.parts)
    suffix = posix.suffix.lower()
    name = posix.name
    lower_name = name.lower()
    lower_path = normalized.lower()

    if size is not None and size > MAX_INDEXED_FILE_BYTES:
        return ExcludedRepoPath(normalized, "oversized_file")
    if parts & _EXCLUDED_PARTS:
        return ExcludedRepoPath(normalized, "excluded_runtime_or_generated_path")
    if name in _SECRET_FILE_NAMES or lower_name.startswith(".env"):
        return ExcludedRepoPath(normalized, "secret_file")
    if suffix in _SECRET_SUFFIXES:
        return ExcludedRepoPath(normalized, "credential_file")
    if suffix in _LOG_SUFFIXES:
        return ExcludedRepoPath(normalized, "log_file")
    if suffix in _BINARY_OR_GENERATED_SUFFIXES:
        return ExcludedRepoPath(normalized, "binary_or_generated_file")
    if suffix in {".json", ".csv"} and any(marker in lower_path for marker in _GENERATED_REPORT_MARKERS):
        return ExcludedRepoPath(normalized, "generated_report")
    if normalized.startswith("tmp_") or "/tmp_" in normalized:
        return ExcludedRepoPath(normalized, "temporary_file")
    return None


def trust_priority(classification: RepoFileClassification) -> tuple[int, int]:
    return (classification.trust_tier, 1 if classification.label == LABEL_HISTORICAL else 0)


def stronger_source(
    left: RepoFileClassification,
    right: RepoFileClassification,
) -> RepoFileClassification:
    return left if trust_priority(left) <= trust_priority(right) else right


def historical_context_requested(message: str) -> bool:
    lowered = str(message or "").lower()
    return any(term in lowered for term in ("historical", "history", "archived", "old", "legacy", "handoff"))


def _is_historical_doc(lower_path: str) -> bool:
    if lower_path.startswith("docs/internal-ai-notes/"):
        return True
    return any(marker in lower_path for marker in _HISTORICAL_MARKERS)


__all__ = [
    "ExcludedRepoPath",
    "LABEL_CURRENT",
    "LABEL_HISTORICAL",
    "MAX_INDEXED_FILE_BYTES",
    "RepoFileClassification",
    "TRUST_TIER_CURRENT_DOCS",
    "TRUST_TIER_CURRENT_SOURCE",
    "TRUST_TIER_HISTORICAL",
    "TRUST_TIER_POLICY",
    "classify_repo_path",
    "excluded_repo_path",
    "historical_context_requested",
    "normalize_repo_path",
    "stronger_source",
    "trust_priority",
]
