from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
import re
from pathlib import Path

from core.ai.repo_sources import (
    LABEL_HISTORICAL,
    ExcludedRepoPath,
    RepoFileClassification,
    classify_repo_path,
    excluded_repo_path,
)

DEFAULT_TOP_K = 8
MAX_CHUNK_LINES = 80
MAX_CHUNK_CHARS = 6000
_TOKEN_RE = re.compile(r"[A-Za-z0-9_./-]+")
_STRUCTURE_RE = re.compile(
    r"^\s*(?:async\s+)?(?:def|class|function)\s+([A-Za-z_][A-Za-z0-9_]*)|"
    r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_][A-Za-z0-9_]*)\s*=",
)
_ROUTE_RE = re.compile(r"@[\w.]+\.route\([\"']([^\"']+)")


@dataclass(frozen=True)
class RepoChunk:
    path: str
    line_start: int
    line_end: int
    text: str
    trust_tier: int
    source_kind: str
    label: str
    mtime: float
    size: int
    content_hash: str
    symbols: tuple[str, ...] = ()

    def citation(self) -> dict[str, object]:
        return {
            "path": self.path,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "trust_tier": self.trust_tier,
            "source_kind": self.source_kind,
            "label": self.label,
        }


@dataclass(frozen=True)
class RepoSearchResult:
    chunks: list[RepoChunk]
    indexed_files: int
    refreshed: bool
    excluded_matches: list[dict[str, str]]

    def metadata(self) -> dict[str, object]:
        return {
            "indexed_files": self.indexed_files,
            "matched_chunks": len(self.chunks),
            "refreshed": self.refreshed,
            "excluded_matches": list(self.excluded_matches),
        }


class RepoIndex:
    def __init__(self, repo_root: Path | str | None = None):
        default_root = Path(__file__).resolve().parents[2]
        self.repo_root = Path(repo_root or default_root).resolve()
        if not self.repo_root.exists() or not self.repo_root.is_dir():
            raise ValueError("repo_root must be an existing directory")
        self._fingerprints: dict[str, tuple[float, int, str]] = {}
        self._chunks_by_path: dict[str, list[RepoChunk]] = {}
        self._excluded: dict[str, ExcludedRepoPath] = {}
        self._indexed_files = 0

    def search(
        self,
        query: str,
        *,
        include_historical: bool = False,
        refresh: bool = False,
        top_k: int = DEFAULT_TOP_K,
    ) -> RepoSearchResult:
        refreshed = self.refresh() if refresh or not self._chunks_by_path else False
        query_terms = _tokenize(query)
        scored: list[tuple[float, RepoChunk]] = []
        for chunks in self._chunks_by_path.values():
            for chunk in chunks:
                if chunk.label == LABEL_HISTORICAL and not include_historical:
                    continue
                score = _score_chunk(query, query_terms, chunk)
                if score > 0:
                    scored.append((score, chunk))

        scored.sort(key=lambda item: (-item[0], item[1].trust_tier, item[1].path, item[1].line_start))
        excluded = self._matching_excluded(query_terms)
        return RepoSearchResult(
            chunks=[chunk for _score, chunk in scored[: max(1, top_k)]],
            indexed_files=self._indexed_files,
            refreshed=refreshed,
            excluded_matches=excluded,
        )

    def status(self, *, refresh: bool = False) -> dict[str, object]:
        refreshed = self.refresh() if refresh or not self._chunks_by_path else False
        return {
            "enabled": True,
            "indexed_files": self._indexed_files,
            "indexed_chunks": sum(len(chunks) for chunks in self._chunks_by_path.values()),
            "refreshed": refreshed,
        }

    def refresh(self) -> bool:
        changed = False
        seen: set[str] = set()
        next_excluded: dict[str, ExcludedRepoPath] = {}
        next_fingerprints: dict[str, tuple[float, int, str]] = {}
        next_chunks_by_path: dict[str, list[RepoChunk]] = {}

        for path in _iter_repo_files(self.repo_root, next_excluded):
            rel_path = _safe_relative_path(self.repo_root, path)
            if rel_path is None:
                skipped_path = _display_path(self.repo_root, path)
                next_excluded[skipped_path] = ExcludedRepoPath(skipped_path, "outside_repo_root")
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            exclusion = excluded_repo_path(rel_path, size=stat.st_size)
            if exclusion:
                next_excluded[rel_path] = exclusion
                continue
            classification = classify_repo_path(rel_path, size=stat.st_size)
            if classification is None:
                continue
            seen.add(rel_path)
            content = _read_text(path)
            if content is None:
                next_excluded[rel_path] = ExcludedRepoPath(rel_path, "non_text_file")
                continue
            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            fingerprint = (stat.st_mtime, stat.st_size, content_hash)
            if self._fingerprints.get(rel_path) == fingerprint:
                next_fingerprints[rel_path] = fingerprint
                next_chunks_by_path[rel_path] = self._chunks_by_path.get(rel_path, [])
                continue
            next_fingerprints[rel_path] = fingerprint
            next_chunks_by_path[rel_path] = _chunk_file(
                rel_path,
                content,
                classification,
                mtime=stat.st_mtime,
                size=stat.st_size,
                content_hash=content_hash,
            )
            changed = True

        if set(self._chunks_by_path) - seen:
            changed = True

        if next_excluded != self._excluded:
            changed = True

        self._fingerprints = next_fingerprints
        self._chunks_by_path = next_chunks_by_path
        self._excluded = next_excluded
        self._indexed_files = len(next_chunks_by_path)
        return changed

    def _matching_excluded(self, query_terms: set[str]) -> list[dict[str, str]]:
        if not query_terms:
            return []
        matches = []
        for path, exclusion in sorted(self._excluded.items()):
            path_terms = _tokenize(path)
            if query_terms & path_terms or any(term in path.lower() for term in query_terms):
                matches.append({"path": path, "reason": exclusion.reason})
            if len(matches) >= 8:
                break
        return matches


def _iter_repo_files(root: Path, excluded: dict[str, ExcludedRepoPath]):
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        current_dir = Path(dirpath)
        kept_dirs = []
        for dirname in sorted(dirnames):
            child = current_dir / dirname
            rel_path = _safe_relative_path(root, child) or _display_path(root, child)
            exclusion = excluded_repo_path(rel_path)
            if exclusion:
                excluded[rel_path] = exclusion
                continue
            kept_dirs.append(dirname)
        dirnames[:] = kept_dirs

        for filename in sorted(filenames):
            yield current_dir / filename


def _safe_relative_path(root: Path, path: Path) -> str | None:
    try:
        return path.resolve().relative_to(root).as_posix()
    except (OSError, ValueError):
        return None


def _display_path(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.name


def _read_text(path: Path) -> str | None:
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    if "\x00" in content:
        return None
    return content


def _chunk_file(
    path: str,
    content: str,
    classification: RepoFileClassification,
    *,
    mtime: float,
    size: int,
    content_hash: str,
) -> list[RepoChunk]:
    lines = content.splitlines()
    if not lines:
        return []
    starts = _chunk_starts(lines, path)
    chunks: list[RepoChunk] = []
    for index, start in enumerate(starts):
        end = starts[index + 1] - 1 if index + 1 < len(starts) else len(lines)
        while end - start + 1 > MAX_CHUNK_LINES:
            segment_end = start + MAX_CHUNK_LINES - 1
            chunks.append(_make_chunk(path, lines, start, segment_end, classification, mtime, size, content_hash))
            start = segment_end + 1
        chunks.append(_make_chunk(path, lines, start, end, classification, mtime, size, content_hash))
    return chunks


def _chunk_starts(lines: list[str], path: str) -> list[int]:
    starts = {1}
    suffix = Path(path).suffix.lower()
    for idx, line in enumerate(lines, start=1):
        if suffix in {".md", ".txt", ".yaml", ".yml"} and line.lstrip().startswith("#"):
            starts.add(idx)
        if suffix in {".py", ".js", ".jsx"} and (_STRUCTURE_RE.search(line) or _ROUTE_RE.search(line)):
            starts.add(idx)
    return sorted(starts)


def _make_chunk(
    path: str,
    lines: list[str],
    start: int,
    end: int,
    classification: RepoFileClassification,
    mtime: float,
    size: int,
    content_hash: str,
) -> RepoChunk:
    text = "\n".join(lines[start - 1 : end])[:MAX_CHUNK_CHARS]
    return RepoChunk(
        path=path,
        line_start=start,
        line_end=end,
        text=text,
        trust_tier=classification.trust_tier,
        source_kind=classification.source_kind,
        label=classification.label,
        mtime=mtime,
        size=size,
        content_hash=content_hash,
        symbols=tuple(sorted(_extract_symbols(text))),
    )


def _extract_symbols(text: str) -> set[str]:
    symbols = set()
    for line in text.splitlines():
        structure = _STRUCTURE_RE.search(line)
        if structure:
            symbols.add(next(group for group in structure.groups() if group))
        route = _ROUTE_RE.search(line)
        if route:
            symbols.add(route.group(1))
    return symbols


def _tokenize(value: str) -> set[str]:
    tokens: set[str] = set()
    for token in _TOKEN_RE.findall(str(value or "")):
        lowered = token.lower()
        if len(lowered) > 1:
            tokens.add(lowered)
        for part in re.split(r"[_./-]+", lowered):
            if len(part) > 1:
                tokens.add(part)
    return tokens


def _score_chunk(query: str, query_terms: set[str], chunk: RepoChunk) -> float:
    if not query_terms:
        return 0
    chunk_terms = _tokenize(f"{chunk.path} {' '.join(chunk.symbols)} {chunk.text}")
    overlap = {term for term in query_terms if _term_matches(term, chunk_terms)}
    if not overlap:
        return 0
    score = len(overlap) * 2.0
    lower_query = str(query or "").lower()
    lower_text = chunk.text.lower()
    lower_path = chunk.path.lower()
    if lower_query and lower_query in lower_text:
        score += 5
    if any(term in lower_path for term in query_terms):
        score += 4
    if any(term in {symbol.lower() for symbol in chunk.symbols} for term in query_terms):
        score += 4
    score += max(0, 3 - chunk.trust_tier)
    if chunk.label == LABEL_HISTORICAL:
        score -= 2
    return score


def _term_matches(term: str, candidates: set[str]) -> bool:
    if term in candidates:
        return True
    if len(term) > 3 and f"{term}s" in candidates:
        return True
    if term.endswith("s") and term[:-1] in candidates:
        return True
    return False


__all__ = ["RepoChunk", "RepoIndex", "RepoSearchResult"]
