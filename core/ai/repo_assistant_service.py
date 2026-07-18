from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any

from core.ai.config import AiGatewayConfig, load_ai_gateway_config
from core.ai.gateway import AiGateway
from core.ai.models import AI_STATUS_SUCCESS, AiGatewayRequest, AiRequestMetadata, estimate_tokens
from core.ai.repo_index import DEFAULT_TOP_K, RepoChunk, RepoIndex
from core.ai.repo_sources import LABEL_HISTORICAL, historical_context_requested

AI_STATUS_INSUFFICIENT_EVIDENCE = "insufficient_evidence"
AI_STATUS_GROUNDING_FAILURE = "grounding_failure"

MAX_REPO_MESSAGE_CHARS = 2000
MAX_HISTORY_ITEMS = 8
MAX_HISTORY_ITEM_CHARS = 600
MAX_SNIPPET_CHARS = 1200
_CITATION_RE = re.compile(r"\[([A-Za-z0-9_./ -]+):(\d+)-(\d+)\]")
_DEFAULT_INDEX: RepoIndex | None = None


@dataclass(frozen=True)
class RepoAssistantValidationError(Exception):
    message: str
    status_code: int = 400
    error_code: str = "invalid_request"

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True)
class RepoAssistantResult:
    payload: dict[str, Any]
    status_code: int = 200


def get_repo_assistant_status(*, index: RepoIndex | None = None) -> dict[str, Any]:
    resolved_index = index or _default_index()
    return {
        "status": "available",
        "assistant": "repo-aware-architecture-assistant",
        "read_only": True,
        "scope": "repository_architecture",
        **resolved_index.status(refresh=False),
    }


def answer_repo_question(
    payload: dict[str, Any],
    *,
    gateway: AiGateway | None = None,
    config: AiGatewayConfig | None = None,
    index: RepoIndex | None = None,
) -> RepoAssistantResult:
    message = _validate_payload(payload)
    history = _validate_history(payload.get("client_history", []))
    refresh = bool(payload.get("refresh", False))
    include_historical = historical_context_requested(message)
    resolved_config = config if config is not None else load_ai_gateway_config()
    resolved_index = index or _default_index()

    search = resolved_index.search(
        message,
        include_historical=include_historical,
        refresh=refresh,
        top_k=DEFAULT_TOP_K,
    )
    current_chunks = [chunk for chunk in search.chunks if chunk.label != LABEL_HISTORICAL]
    if not current_chunks:
        return RepoAssistantResult(
            _repo_response(
                status=AI_STATUS_INSUFFICIENT_EVIDENCE,
                answer="I do not have enough current repository evidence to answer safely.",
                insufficient_evidence=True,
                citations=[],
                retrieval=search.metadata(),
                metadata=_empty_metadata(AI_STATUS_INSUFFICIENT_EVIDENCE, mode=resolved_config.mode),
                error="No allowed current repository evidence matched the question.",
            )
        )

    prompt = _build_prompt(
        message,
        history=history,
        chunks=search.chunks,
        max_prompt_chars=resolved_config.max_prompt_chars,
    )
    if len(prompt) > resolved_config.max_prompt_chars:
        return RepoAssistantResult(
            _repo_response(
                status=AI_STATUS_INSUFFICIENT_EVIDENCE,
                answer="The relevant repository evidence is too large to send safely.",
                insufficient_evidence=True,
                citations=[chunk.citation() for chunk in current_chunks],
                retrieval={**search.metadata(), "prompt_truncated": True},
                metadata=_empty_metadata(AI_STATUS_INSUFFICIENT_EVIDENCE, mode=resolved_config.mode),
                error="Prompt exceeded configured AI size limit.",
            )
        )

    resolved_gateway = gateway if gateway is not None else AiGateway(config=resolved_config)
    gateway_response = resolved_gateway.generate(
        AiGatewayRequest(
            prompt=prompt,
            capability="text_generation",
            metadata={
                "context_type": "repository",
                "action": "repo_architecture_chat",
                "read_only": True,
            },
        )
    )
    response = gateway_response.as_dict()
    if response["status"] != AI_STATUS_SUCCESS:
        return RepoAssistantResult(
            _repo_response(
                status=response["status"],
                answer=response["content"],
                insufficient_evidence=False,
                citations=[chunk.citation() for chunk in search.chunks],
                retrieval=search.metadata(),
                metadata=response["metadata"],
                error=response["error"],
            )
        )

    citations = _validated_citations(response["content"] or "", search.chunks)
    if not citations:
        return RepoAssistantResult(
            _repo_response(
                status=AI_STATUS_GROUNDING_FAILURE,
                answer=None,
                insufficient_evidence=True,
                citations=[],
                retrieval=search.metadata(),
                metadata=_empty_metadata(AI_STATUS_GROUNDING_FAILURE, mode=resolved_config.mode),
                error="AI answer did not include valid citations from retrieved repository evidence.",
            )
        )

    return RepoAssistantResult(
        _repo_response(
            status=AI_STATUS_SUCCESS,
            answer=response["content"],
            insufficient_evidence=False,
            citations=citations,
            retrieval=search.metadata(),
            metadata=response["metadata"],
            error=None,
        )
    )


def _validate_payload(payload: dict[str, Any]) -> str:
    if not isinstance(payload, dict):
        raise RepoAssistantValidationError("JSON object body is required.")
    message = str(payload.get("message") or "").strip()
    if not message:
        raise RepoAssistantValidationError("message is required.")
    if len(message) > MAX_REPO_MESSAGE_CHARS:
        raise RepoAssistantValidationError("message is too large.")
    if "refresh" in payload and not isinstance(payload.get("refresh"), bool):
        raise RepoAssistantValidationError("refresh must be a boolean.")
    return message


def _validate_history(raw_history: Any) -> list[dict[str, str]]:
    if raw_history is None:
        return []
    if not isinstance(raw_history, list):
        raise RepoAssistantValidationError("client_history must be a list.")
    history: list[dict[str, str]] = []
    for item in raw_history[-MAX_HISTORY_ITEMS:]:
        if not isinstance(item, dict):
            raise RepoAssistantValidationError("client_history entries must be objects.")
        role = str(item.get("role") or "").strip().lower()
        content = str(item.get("content") or "").strip()
        if role not in {"user", "assistant"}:
            raise RepoAssistantValidationError("client_history role is unsupported.")
        if len(content) > MAX_HISTORY_ITEM_CHARS:
            content = content[:MAX_HISTORY_ITEM_CHARS]
        history.append({"role": role, "content": content})
    return history


def _build_prompt(
    message: str,
    *,
    history: list[dict[str, str]],
    chunks: list[RepoChunk],
    max_prompt_chars: int,
) -> str:
    snippets: list[dict[str, object]] = []
    for chunk in chunks:
        candidate = {
            "path": chunk.path,
            "line_start": chunk.line_start,
            "line_end": chunk.line_end,
            "trust_tier": chunk.trust_tier,
            "source_kind": chunk.source_kind,
            "label": chunk.label,
            "excerpt": chunk.text[:MAX_SNIPPET_CHARS],
        }
        candidate_prompt = _format_prompt(message, history=history, snippets=[*snippets, candidate])
        if snippets and len(candidate_prompt) > max_prompt_chars:
            break
        snippets.append(candidate)
    return _format_prompt(message, history=history, snippets=snippets)


def _format_prompt(
    message: str,
    *,
    history: list[dict[str, str]],
    snippets: list[dict[str, object]],
) -> str:
    return (
        "You are a read-only repository architecture assistant for this SIEM.\n"
        "Use only the supplied repository excerpts. If evidence is missing, say you do not have enough current evidence.\n"
        "Do not claim to edit files, run commands, access the VM, deploy, commit, push, query databases, or mutate production.\n"
        "Mac repository policy and Tier 0 sources override lower-trust docs. Current source overrides stale docs for implemented behavior.\n"
        "Every factual claim must include citations in the exact format [path:line_start-line_end].\n"
        "Historical sources are context only and must be labeled historical in the answer.\n\n"
        f"Question: {message}\n"
        f"Recent client-owned history: {json.dumps(history, sort_keys=True)}\n"
        f"Repository excerpts: {json.dumps(snippets, sort_keys=True)}\n\n"
        "Answer concisely with: Answer, Evidence, Uncertainty, Safe next steps."
    )


def _validated_citations(answer: str, chunks: list[RepoChunk]) -> list[dict[str, object]]:
    allowed = {(chunk.path, chunk.line_start, chunk.line_end): chunk for chunk in chunks}
    valid: dict[tuple[str, int, int], RepoChunk] = {}
    for match in _CITATION_RE.finditer(answer):
        path = match.group(1).strip()
        start = int(match.group(2))
        end = int(match.group(3))
        for (allowed_path, allowed_start, allowed_end), chunk in allowed.items():
            if path == allowed_path and allowed_start <= start <= end <= allowed_end:
                valid[(allowed_path, allowed_start, allowed_end)] = chunk
                break
    return [chunk.citation() for chunk in valid.values()]


def _repo_response(
    *,
    status: str,
    answer: str | None,
    insufficient_evidence: bool,
    citations: list[dict[str, object]],
    retrieval: dict[str, object],
    metadata: dict[str, Any],
    error: str | None,
) -> dict[str, Any]:
    return {
        "status": status,
        "answer": answer,
        "insufficient_evidence": insufficient_evidence,
        "citations": citations,
        "retrieval": retrieval,
        "metadata": metadata,
        "error": error,
    }


def _empty_metadata(status: str, *, mode: str = "disabled") -> dict[str, Any]:
    return AiRequestMetadata(
        provider=None,
        model=None,
        mode=mode,
        status=status,
        read_only=True,
        latency_ms=0,
        estimated_prompt_tokens=0,
        estimated_completion_tokens=0,
        estimated_cost_usd=None,
        local_request=False,
        paid_request=False,
        fallback_attempted=False,
        fallback_reason=None,
        error_code=status,
    ).as_dict()


def _default_index() -> RepoIndex:
    global _DEFAULT_INDEX
    if _DEFAULT_INDEX is None:
        _DEFAULT_INDEX = RepoIndex()
    return _DEFAULT_INDEX


__all__ = [
    "AI_STATUS_GROUNDING_FAILURE",
    "AI_STATUS_INSUFFICIENT_EVIDENCE",
    "RepoAssistantResult",
    "RepoAssistantValidationError",
    "answer_repo_question",
    "get_repo_assistant_status",
]
