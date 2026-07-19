from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import re
from typing import Any

from flask_login import current_user

from core.ai.config import AiGatewayConfig, load_ai_gateway_config
from core.ai.context_builder import (
    AiContextError,
    AiContextNotFoundError,
    AiContextPayload,
    AiContextValidationError,
    build_ai_context,
)
from core.ai.draft_schemas import (
    DEFAULT_DRAFT_LABELS,
    DRAFT_STATUS_INSUFFICIENT_CONTEXT,
    DRAFT_STATUS_INVALID_REQUEST,
    DRAFT_STATUS_PARSE_FAILED,
    DRAFT_STATUS_SUCCESS,
    DRAFT_STATUS_VALIDATION_FAILED,
    DraftRequest,
    DraftValidationError,
    build_draft_result,
    get_draft_definition,
    redact_draft_value,
    validate_client_request_id,
    validate_context_type_for_draft,
    validate_instruction,
    validate_draft_payload,
)
from core.ai.explainer_service import _empty_metadata
from core.ai.gateway import AiGateway
from core.ai.models import AiGatewayRequest
from core.ai.soc_tool_executor import (
    build_deterministic_tool_plan,
    execute_tool_plan,
    normalize_tool_policy,
    should_skip_tools_for_gateway,
    tool_summary_for_prompt,
)
from core.ai.soc_tools import SocToolExecutionSummary

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class DraftServiceResult:
    payload: dict[str, Any]
    status_code: int = 200


def create_draft(
    payload: dict[str, Any],
    *,
    gateway: AiGateway | None = None,
    config: AiGatewayConfig | None = None,
) -> DraftServiceResult:
    if not isinstance(payload, dict):
        raise DraftValidationError("JSON object body is required.")

    resolved_config = config if config is not None else load_ai_gateway_config()
    request = _parse_request(payload)
    definition = get_draft_definition(request.draft_type)

    ai_context = build_ai_context(
        context_type=request.context_type,
        context=request.context,
        config=resolved_config,
        question=request.instruction,
    )

    tools = _empty_tool_summary()
    if request.use_tools and not should_skip_tools_for_gateway(resolved_config):
        plan = build_deterministic_tool_plan(
            question=request.instruction,
            context_type=ai_context.context_type,
            context=request.context,
            tool_policy=request.tool_policy,
        )
        tools = execute_tool_plan(
            plan,
            actor_role=getattr(current_user, "role", None),
            config=resolved_config,
            tool_policy=request.tool_policy,
        )

    has_tool_evidence = any(call.status == "success" and call.data not in (None, {}, []) for call in tools.calls)
    if ai_context.insufficient_context and not has_tool_evidence:
        return _draft_state_response(
            DRAFT_STATUS_INSUFFICIENT_CONTEXT,
            request=request,
            ai_context=ai_context,
            tools=tools,
            metadata=_empty_metadata(DRAFT_STATUS_INSUFFICIENT_CONTEXT, mode=resolved_config.mode),
            error=ai_context.insufficient_reason or "Not enough SIEM context to draft safely.",
            status_code=200,
        )

    prompt = _build_draft_prompt(request, ai_context, tools, config=resolved_config)
    if len(prompt) > resolved_config.max_prompt_chars:
        return _draft_state_response(
            DRAFT_STATUS_INSUFFICIENT_CONTEXT,
            request=request,
            ai_context=ai_context,
            tools=tools,
            metadata=_empty_metadata(DRAFT_STATUS_INSUFFICIENT_CONTEXT, mode=resolved_config.mode),
            error="Draft context exceeded configured AI prompt limit.",
            status_code=200,
        )

    resolved_gateway = gateway if gateway is not None else AiGateway(config=resolved_config)
    gateway_response = resolved_gateway.generate(
        AiGatewayRequest(
            prompt=prompt,
            capability="text_generation",
            metadata={
                "context_type": ai_context.context_type,
                "action": "draft",
                "draft_type": request.draft_type,
                "read_only": True,
                "persisted": False,
                "applied": False,
            },
        )
    )
    gateway_payload = gateway_response.as_dict()
    if gateway_response.status != "success":
        return _draft_state_response(
            gateway_response.status,
            request=request,
            ai_context=ai_context,
            tools=tools,
            metadata=gateway_payload["metadata"],
            error=gateway_response.error,
            status_code=200,
        )

    parsed = _parse_provider_draft(gateway_response.content)
    if parsed is None:
        return _draft_state_response(
            DRAFT_STATUS_PARSE_FAILED,
            request=request,
            ai_context=ai_context,
            tools=tools,
            metadata=gateway_payload["metadata"],
            error="AI draft response was not valid JSON.",
            validation_errors=["AI draft response was not valid JSON."],
            status_code=200,
        )

    parsed = redact_draft_value(parsed)
    validation = validate_draft_payload(request.draft_type, parsed)
    if not validation.valid:
        return _draft_state_response(
            DRAFT_STATUS_VALIDATION_FAILED,
            request=request,
            ai_context=ai_context,
            tools=tools,
            metadata=gateway_payload["metadata"],
            error="AI draft response did not match the required schema.",
            validation_errors=validation.errors,
            status_code=200,
        )

    draft = build_draft_result(request.draft_type, parsed)
    _LOGGER.info(
        "ai_draft_generated draft_type=%s context_type=%s status=%s sources=%s tools=%s",
        request.draft_type,
        request.context_type,
        DRAFT_STATUS_SUCCESS,
        len(ai_context.sources),
        len(tools.calls),
    )
    return DraftServiceResult(
        {
            "status": DRAFT_STATUS_SUCCESS,
            "draft": draft.as_dict(),
            "context": ai_context.metadata(),
            "tools": tools.as_dict(),
            "metadata": gateway_payload["metadata"],
            "error": None,
        },
        status_code=200,
    )


def service_error_response(error: Exception) -> DraftServiceResult:
    status = getattr(error, "error_code", DRAFT_STATUS_INVALID_REQUEST)
    status_code = getattr(error, "status_code", 400)
    return DraftServiceResult(
        {
            "status": status,
            "draft": _empty_draft(status, validation_errors=[str(error)]),
            "context": {
                "context_type": None,
                "sources": [],
                "truncated": False,
                "omitted_count": 0,
                "insufficient_reason": str(error),
            },
            "tools": _empty_tool_summary().as_dict(),
            "metadata": _empty_metadata(status),
            "error": str(error),
        },
        status_code=status_code,
    )


def _parse_request(payload: dict[str, Any]) -> DraftRequest:
    definition = get_draft_definition(payload.get("draft_type"))
    context_type = validate_context_type_for_draft(definition, payload.get("context_type"))
    instruction = validate_instruction(payload.get("instruction"))
    context = payload.get("context")
    if context is None:
        context = {}
    if not isinstance(context, dict):
        raise DraftValidationError("context must be an object.")
    tool_policy = normalize_tool_policy(payload.get("tool_policy"))
    return DraftRequest(
        draft_type=definition.draft_type,
        instruction=instruction,
        context_type=context_type,
        context=redact_draft_value(context),
        use_tools=bool(payload.get("use_tools")),
        tool_policy=tool_policy,
        client_request_id=validate_client_request_id(payload.get("client_request_id")),
    )


def _build_draft_prompt(
    request: DraftRequest,
    ai_context: AiContextPayload,
    tools: SocToolExecutionSummary,
    *,
    config: AiGatewayConfig,
) -> str:
    definition = get_draft_definition(request.draft_type)
    context_json = json.dumps(redact_draft_value(ai_context.data), default=str, sort_keys=True, indent=2)
    schema_json = json.dumps(_schema_for_prompt(definition), sort_keys=True, indent=2)
    tool_budget = max(1000, config.max_prompt_chars // 3)
    tools_json = json.dumps(
        tool_summary_for_prompt(tools, max_chars=tool_budget),
        default=str,
        sort_keys=True,
        indent=2,
    )
    return (
        "You are a read-only SIEM drafting assistant.\n"
        "Use only the supplied SIEM context and read-only tool evidence.\n"
        "Return exactly one JSON object matching the requested draft schema. Do not wrap it in markdown.\n"
        "Do not claim anything was saved, applied, approved, executed, blocked, deployed, committed, or changed.\n"
        "Do not include secrets, credentials, shell commands, migration commands, or production-mutating payloads.\n"
        "Mark uncertainty and assumptions inside the requested schema fields.\n"
        "The draft is AI-generated review content only and requires analyst review before any future workflow.\n\n"
        f"Draft type: {request.draft_type}\n"
        f"Draft purpose: {definition.description}\n"
        f"Analyst instruction: {request.instruction}\n"
        f"Context type: {ai_context.context_type}\n"
        f"Context sources: {json.dumps(ai_context.metadata(), default=str, sort_keys=True)}\n\n"
        f"Required JSON schema shape:\n{schema_json}\n\n"
        f"SIEM context:\n{context_json}\n\n"
        f"Read-only SOC tool evidence:\n{tools_json}\n"
    )


def _schema_for_prompt(definition) -> dict[str, Any]:
    return {
        field.name: {
            "type": "array" if field.kind == "list" else "string",
            "required": field.required,
            "max_items": field.max_items,
        }
        for field in definition.fields
    }


def _parse_provider_draft(content: str | None) -> dict[str, Any] | None:
    if not content:
        return None
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return parsed if isinstance(parsed, dict) else None


def _draft_state_response(
    status: str,
    *,
    request: DraftRequest,
    ai_context: AiContextPayload,
    tools: SocToolExecutionSummary,
    metadata: dict[str, Any],
    error: str | None,
    validation_errors: list[str] | None = None,
    status_code: int = 200,
) -> DraftServiceResult:
    _LOGGER.info(
        "ai_draft_finished draft_type=%s context_type=%s status=%s sources=%s tools=%s error_code=%s",
        request.draft_type,
        request.context_type,
        status,
        len(ai_context.sources),
        len(tools.calls),
        status,
    )
    return DraftServiceResult(
        {
            "status": status,
            "draft": _empty_draft(request.draft_type, validation_errors=validation_errors or []),
            "context": ai_context.metadata(),
            "tools": tools.as_dict(),
            "metadata": metadata,
            "error": error,
        },
        status_code=status_code,
    )


def _empty_draft(draft_type: str | None, *, validation_errors: list[str] | None = None) -> dict[str, Any]:
    validation_errors = validation_errors or []
    title = "AI draft"
    if draft_type:
        try:
            title = get_draft_definition(draft_type).title
        except DraftValidationError:
            title = "AI draft"
    return {
        "draft_type": draft_type,
        "title": title,
        "payload": {},
        "validation": {"valid": False, "errors": validation_errors},
        "generated_at": None,
        "labels": dict(DEFAULT_DRAFT_LABELS),
    }


def _empty_tool_summary() -> SocToolExecutionSummary:
    return SocToolExecutionSummary(used=False)


__all__ = [
    "AiContextError",
    "AiContextNotFoundError",
    "AiContextValidationError",
    "DraftServiceResult",
    "DraftValidationError",
    "create_draft",
    "service_error_response",
]
