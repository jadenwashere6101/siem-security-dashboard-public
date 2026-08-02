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
from core.ai.anakin_persona import artifact_policy
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
from core.ai.profile_registry import profile_for_draft_type
from core.ai.soc_tool_executor import (
    build_deterministic_tool_plan,
    execute_tool_plan,
    normalize_tool_policy,
    should_skip_tools_for_gateway,
)
from core.ai.soc_tools import SocToolExecutionSummary
from core.ai.conversation_context import prompt_block

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
    profile_name = profile_for_draft_type(request.draft_type)
    profile = resolved_config.profile(profile_name)

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

    prompt = _build_draft_prompt(
        request,
        ai_context,
        tools,
        config=resolved_config,
        profile_max_prompt_chars=profile.max_prompt_chars,
        conversation_context=payload.get("conversation_context"),
    )
    if len(prompt) > profile.max_prompt_chars:
        return _draft_state_response(
            DRAFT_STATUS_INSUFFICIENT_CONTEXT,
            request=request,
            ai_context=ai_context,
            tools=tools,
            metadata=_empty_metadata(DRAFT_STATUS_INSUFFICIENT_CONTEXT, mode=resolved_config.mode),
            error="Draft context exceeded configured AI profile prompt limit.",
            status_code=200,
        )

    resolved_gateway = gateway if gateway is not None else AiGateway(config=resolved_config)
    gateway_response = resolved_gateway.generate(
        AiGatewayRequest(
            prompt=prompt,
            capability="text_generation",
            profile=profile_name,
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
    validation_errors: list[str] = []
    repair_attempted = False
    if parsed is None:
        repair_attempted = True
        repaired = _attempt_draft_repair(
            resolved_gateway,
            request=request,
            original_content=gateway_response.content,
            validation_errors=["AI draft response was not valid JSON."],
            profile_name=profile_name,
        )
        if repaired is not None:
            gateway_response = repaired
            gateway_payload = gateway_response.as_dict()
            parsed = _parse_provider_draft(gateway_response.content)
    if parsed is None:
        metadata = dict(gateway_payload["metadata"])
        metadata["repair_attempted"] = repair_attempted
        metadata["repair_count"] = 1 if repair_attempted else 0
        return _draft_state_response(
            DRAFT_STATUS_PARSE_FAILED,
            request=request,
            ai_context=ai_context,
            tools=tools,
            metadata=metadata,
            error="AI draft response was not valid JSON.",
            validation_errors=["AI draft response was not valid JSON."],
            status_code=200,
        )

    parsed = redact_draft_value(parsed)
    validation = validate_draft_payload(request.draft_type, parsed)
    if not validation.valid:
        validation_errors = list(validation.errors)
        repair_attempted = True
        repaired = _attempt_draft_repair(
            resolved_gateway,
            request=request,
            original_content=gateway_response.content,
            validation_errors=validation_errors,
            profile_name=profile_name,
        )
        if repaired is not None:
            gateway_response = repaired
            gateway_payload = gateway_response.as_dict()
            repaired_parsed = _parse_provider_draft(gateway_response.content)
            if repaired_parsed is not None:
                repaired_parsed = redact_draft_value(repaired_parsed)
                repaired_validation = validate_draft_payload(request.draft_type, repaired_parsed)
                if repaired_validation.valid:
                    parsed = repaired_parsed
                    validation = repaired_validation
                else:
                    validation_errors = list(repaired_validation.errors)
            else:
                validation_errors = ["AI draft repair response was not valid JSON."]
    if not validation.valid:
        metadata = dict(gateway_payload["metadata"])
        metadata["repair_attempted"] = repair_attempted
        metadata["repair_count"] = 1 if repair_attempted else 0
        return _draft_state_response(
            DRAFT_STATUS_VALIDATION_FAILED,
            request=request,
            ai_context=ai_context,
            tools=tools,
            metadata=metadata,
            error="AI draft response did not match the required schema.",
            validation_errors=validation_errors,
            status_code=200,
        )

    draft = build_draft_result(request.draft_type, parsed)
    metadata = dict(gateway_payload["metadata"])
    metadata["repair_attempted"] = repair_attempted
    metadata["repair_count"] = 1 if repair_attempted else 0
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
            "metadata": metadata,
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
    profile_max_prompt_chars: int | None = None,
    conversation_context: dict[str, Any] | None = None,
) -> str:
    definition = get_draft_definition(request.draft_type)
    schema_json = json.dumps(_schema_for_prompt(definition), sort_keys=True, separators=(",", ":"))
    required_fields = _required_fields_for_prompt(definition)
    example_json = json.dumps(_example_for_prompt(definition), sort_keys=True, separators=(",", ":"))
    prompt_limit = profile_max_prompt_chars or config.max_prompt_chars
    tool_budget = max(900, min(2200, prompt_limit // 6))
    tools_json = json.dumps(
        _draft_tool_evidence_for_prompt(tools, max_chars=tool_budget),
        default=str,
        sort_keys=True,
        separators=(",", ":"),
    )
    memory = prompt_block(conversation_context)
    fixed_budget = len(schema_json) + len(example_json) + len(tools_json) + len(artifact_policy()) + len(memory) + 1700
    context_budget = max(1200, min(3600, prompt_limit - fixed_budget))
    context_json = _draft_context_json_for_prompt(
        ai_context,
        max_chars=context_budget,
        draft_type=request.draft_type,
    )
    return (
        f"{artifact_policy()}"
        f"{memory}"
        "Return exactly one JSON object matching the requested schema; no markdown.\n"
        "Required fields must be present, non-empty, and use exact field names.\n"
        "Review-only: do not claim anything was saved, applied, approved, executed, blocked, deployed, committed, or changed.\n\n"
        f"Draft type: {request.draft_type}\n"
        f"Draft purpose: {definition.description}\n"
        f"Analyst instruction: {request.instruction}\n"
        f"Context type: {ai_context.context_type}\n"
        f"Context sources: {json.dumps(_source_identity_for_prompt(ai_context), default=str, sort_keys=True, separators=(',', ':'))}\n\n"
        f"Required fields that must appear exactly once: {', '.join(required_fields)}\n"
        f"Required JSON schema shape:\n{schema_json}\n\n"
        f"Valid JSON example matching this exact draft schema:\n{example_json}\n\n"
        f"Relevant SIEM evidence packet:\n{context_json}\n\n"
        f"Read-only SOC tool evidence summary:\n{tools_json}\n"
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


def _required_fields_for_prompt(definition) -> list[str]:
    return [field.name for field in definition.fields if field.required]


def _example_for_prompt(definition) -> dict[str, Any]:
    if definition.draft_type == "detection_rule_change":
        return {
            "title": "Tune repeated-deny detection threshold",
            "rationale": "Bounded SIEM evidence shows repeated deny activity; analyst review is needed before any rule change.",
            "target_rule": "pfsense_firewall_repeated_deny",
            "suggested_condition": "Require repeated deny events from the same source IP across multiple target ports within the observed window.",
            "severity": "high",
            "false_positive_notes": "Check for approved vulnerability scanners, internal monitoring, NAT gateways, and maintenance windows before treating this as malicious.",
            "test_ideas": [
                "Replay representative benign scanner events.",
                "Replay recent high-confidence deny bursts from the supplied evidence.",
            ],
            "rollback_notes": "Keep the existing rule parameters available and restore them if alert volume or false positives increase after review.",
            "source_references": ["alert:1001", "context:evidence"],
        }
    example: dict[str, Any] = {}
    for field in definition.fields:
        if field.kind == "list":
            example[field.name] = [f"Example {field.name.replace('_', ' ')} item"]
        else:
            example[field.name] = f"Example {field.name.replace('_', ' ')}"
    return example


def _draft_context_json_for_prompt(ai_context: AiContextPayload, *, max_chars: int, draft_type: str | None = None) -> str:
    packet = _draft_evidence_packet(ai_context, draft_type=draft_type, max_chars=max_chars)
    rendered = json.dumps(packet, default=str, sort_keys=True, separators=(",", ":"))
    if len(rendered) <= max_chars:
        return rendered
    packet = _draft_evidence_packet(ai_context, draft_type=draft_type, max_chars=max_chars, row_limit=3)
    rendered = json.dumps(packet, default=str, sort_keys=True, separators=(",", ":"))
    if len(rendered) <= max_chars:
        return rendered
    fallback = {
        "context_type": ai_context.context_type,
        "primary": _compact_draft_value(_primary_context_value(ai_context.data, ai_context.context_type), max_depth=2, max_items=3),
        "evidence_counts": _evidence_counts(ai_context.data),
        "source_identity": _source_identity_for_prompt(ai_context),
        "_context_bounds": {
            "included_sources": len(ai_context.sources),
            "truncated": True,
            "input_truncated": ai_context.truncated,
            "input_omitted_count": ai_context.omitted_count,
            "omitted_count": ai_context.omitted_count + _estimated_omitted_count(ai_context.data),
            "truncation_reason": "draft_prompt_budget",
            "max_chars": max_chars,
        },
    }
    return json.dumps(fallback, default=str, sort_keys=True, separators=(",", ":"))


def _draft_evidence_packet(
    ai_context: AiContextPayload,
    *,
    draft_type: str | None,
    max_chars: int,
    row_limit: int = 6,
) -> dict[str, Any]:
    data = redact_draft_value(ai_context.data)
    if not isinstance(data, dict):
        data = {"value": data}
    omitted = 0
    relevant_keys = _relevant_context_keys(ai_context.context_type, draft_type)
    relevant: dict[str, Any] = {}
    for key in relevant_keys:
        if key not in data:
            continue
        value, value_omitted = _compact_relevant_draft_value(key, data[key], row_limit=row_limit)
        relevant[key] = value
        omitted += value_omitted
    evidence_counts = _evidence_counts(data)
    packet = {
        "context_type": ai_context.context_type,
        "draft_type": draft_type,
        "primary": _compact_draft_value(_primary_context_value(data, ai_context.context_type), max_depth=2, max_items=4),
        "relevant_evidence": relevant,
        "evidence_counts": evidence_counts,
        "source_identity": _source_identity_for_prompt(ai_context),
        "_context_bounds": {
            "included_sources": len(ai_context.sources),
            "input_truncated": ai_context.truncated,
            "input_omitted_count": ai_context.omitted_count,
            "compacted": True,
            "truncated": ai_context.truncated or omitted > 0,
            "omitted_count": ai_context.omitted_count + omitted,
            "max_chars": max_chars,
        },
    }
    if "[REDACTED]" in json.dumps(data, default=str):
        packet["redaction"] = {"sensitive_values": "[REDACTED]"}
    return packet


def _relevant_context_keys(context_type: str, draft_type: str | None) -> tuple[str, ...]:
    if context_type == "alert" and draft_type == "investigation_checklist":
        return ("summary", "why_fired", "_evidence", "reputation", "signals", "related_events", "related_alerts")
    if draft_type == "detection_rule_change":
        return ("summary", "alert", "why_fired", "rule", "detection", "related_events", "related_alerts", "_evidence")
    if draft_type == "response_recommendation":
        return ("summary", "alert", "incident", "source_ip", "registry_record", "reputation", "outcome_history", "response_outcomes", "related_alerts", "_evidence")
    if draft_type in {"incident_note", "escalation_summary"}:
        return ("summary", "incident", "alert", "timeline", "linked_alerts", "related_alerts", "_evidence")
    if draft_type == "playbook_draft":
        return ("summary", "alert", "incident", "source_ip", "response_outcomes", "related_alerts", "related_events", "_evidence")
    return ("summary", "alert", "incident", "source_ip", "recon_activity", "registry_record", "related_events", "related_alerts", "_evidence")


def _primary_context_value(data: Any, context_type: str) -> Any:
    if not isinstance(data, dict):
        return data
    if context_type == "alert":
        return data.get("alert") or data.get("summary")
    if context_type == "incident":
        return data.get("incident") or data.get("summary")
    if context_type == "source_ip":
        return {"source_ip": data.get("source_ip"), "reputation": data.get("reputation")}
    if context_type == "recon_activity":
        return data.get("recon_activity") or data.get("summary")
    if context_type == "response_registry":
        return data.get("registry_record") or data.get("summary")
    return data.get("summary") or data.get("visible_context") or data


def _compact_relevant_draft_value(key: str, value: Any, *, row_limit: int) -> tuple[Any, int]:
    if isinstance(value, list):
        fields = _row_fields_for_key(key)
        rows = [_select_row_fields(item, fields) for item in value[:row_limit]]
        omitted = max(0, len(value) - len(rows))
        return {"count": len(value), "rows": rows, "omitted_count": omitted, "truncated": omitted > 0}, omitted
    if isinstance(value, dict):
        compacted = _compact_draft_value(value, max_depth=3, max_items=row_limit)
        omitted = _estimated_omitted_count(value, row_limit=row_limit)
        return compacted, omitted
    if isinstance(value, str) and len(value) > 320:
        return value[:320] + "... [truncated]", 1
    return value, 0


def _row_fields_for_key(key: str) -> tuple[str, ...]:
    if key in {"related_events", "timeline"}:
        return ("id", "timestamp", "created_at", "event_type", "source", "source_ip", "destination_ip", "target_ip", "destination_port", "target_port", "action", "outcome", "status", "severity")
    if key in {"related_alerts", "linked_alerts", "recent_alerts"}:
        return ("id", "alert_id", "alert_type", "severity", "status", "source_ip", "target_ip", "created_at", "timestamp")
    if key in {"outcome_history", "response_outcomes"}:
        return ("id", "action", "action_type", "status", "execution_state", "execution_mode", "external_executed", "tracking_recorded", "created_at")
    return ("id", "type", "name", "severity", "status", "source_ip", "target_ip", "count", "created_at", "timestamp")


def _select_row_fields(row: Any, fields: tuple[str, ...]) -> Any:
    if not isinstance(row, dict):
        return _compact_draft_value(row, max_depth=1, max_items=3)
    selected = {field: row[field] for field in fields if field in row and row[field] not in (None, "", [], {})}
    if not selected:
        selected = {key: row[key] for key in list(row.keys())[:4]}
    return _compact_draft_value(selected, max_depth=2, max_items=4)


def _evidence_counts(data: Any) -> dict[str, int]:
    if not isinstance(data, dict):
        return {}
    counts: dict[str, int] = {}
    for key, value in data.items():
        if isinstance(value, list):
            counts[key] = len(value)
        elif isinstance(value, dict):
            nested_count = value.get("count") or value.get("total") or value.get("observed")
            if isinstance(nested_count, int):
                counts[key] = nested_count
    return counts


def _estimated_omitted_count(value: Any, *, row_limit: int = 6) -> int:
    if isinstance(value, list):
        return max(0, len(value) - row_limit)
    if isinstance(value, dict):
        omitted = max(0, len(value) - 12)
        for nested in value.values():
            omitted += _estimated_omitted_count(nested, row_limit=row_limit)
        return omitted
    return 0


def _source_identity_for_prompt(ai_context: AiContextPayload) -> dict[str, Any]:
    return {
        "context_type": ai_context.context_type,
        "sources": [
            {
                "source_type": source.source_type,
                "source_path": source.source_path,
                "record_ids": source.record_ids[:8],
                "truncated": source.truncated,
                "omitted_count": source.omitted_count,
            }
            for source in ai_context.sources[:8]
        ],
        "source_count": len(ai_context.sources),
        "truncated": ai_context.truncated,
        "omitted_count": ai_context.omitted_count,
    }


def _draft_tool_evidence_for_prompt(tools: SocToolExecutionSummary, *, max_chars: int) -> dict[str, Any]:
    compact = {
        "used": tools.used,
        "read_only": tools.read_only,
        "truncated": tools.truncated,
        "omitted_count": tools.omitted_count,
        "error_code": tools.error_code,
        "sources": [
            {
                "tool_name": source.tool_name,
                "source_type": source.source_type,
                "source_path": source.source_path,
                "record_ids": source.record_ids[:8],
                "truncated": source.truncated,
                "omitted_count": source.omitted_count,
            }
            for source in tools.sources[:8]
        ],
        "calls": [_compact_tool_call(call) for call in tools.calls[:4]],
    }
    rendered = json.dumps(compact, default=str, sort_keys=True, separators=(",", ":"))
    if len(rendered) <= max_chars:
        return compact
    return {
        "used": tools.used,
        "read_only": True,
        "truncated": True,
        "omitted_count": tools.omitted_count + max(0, len(tools.calls) - 2),
        "sources": compact["sources"][:4],
        "calls": [
            {
                "tool_name": call.tool_name,
                "status": call.status,
                "truncated": True,
                "omitted_count": call.omitted_count,
                "source_paths": [source.source_path for source in call.sources[:3]],
            }
            for call in tools.calls[:2]
        ],
    }


def _compact_tool_call(call) -> dict[str, Any]:
    data = call.data if isinstance(call.data, dict) else {}
    summary: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, list):
            rows, omitted = _compact_relevant_draft_value(key, value, row_limit=4)
            summary[key] = rows
            if omitted:
                summary.setdefault("_omitted_count", 0)
                summary["_omitted_count"] += omitted
        elif key in {"summary", "counts", "alert", "incident", "source_ip", "reputation", "why_fired"}:
            summary[key] = _compact_draft_value(value, max_depth=2, max_items=4)
    return {
        "tool_name": call.tool_name,
        "status": call.status,
        "truncated": call.truncated,
        "omitted_count": call.omitted_count,
        "latency_ms": call.latency_ms,
        "error_code": call.error_code,
        "source_paths": [source.source_path for source in call.sources[:4]],
        "data_summary": summary,
    }


def _compact_draft_value(value: Any, *, max_depth: int, max_items: int = 8) -> Any:
    if max_depth <= 0:
        if isinstance(value, dict):
            return {"_omitted_fields": len(value)}
        if isinstance(value, list):
            return {"_omitted_items": len(value)}
        return value
    if isinstance(value, list):
        compacted = [_compact_draft_value(item, max_depth=max_depth - 1, max_items=max_items) for item in value[:max_items]]
        if len(value) > max_items:
            compacted.append({"_omitted_items": len(value) - max_items})
        return compacted
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        preferred = [
            "summary",
            "_evidence",
            "alert",
            "incident",
            "source_ip",
            "recon_activity",
            "registry_record",
            "why_fired",
            "reputation",
            "signals",
            "timeline",
            "linked_alerts",
            "related_alerts",
            "related_events",
            "recent_alerts",
            "outcome_history",
            "response_outcomes",
            "background_refresh",
            "visible_context",
            "workspace",
        ]
        keys = [key for key in preferred if key in value]
        keys.extend(key for key in value.keys() if key not in keys)
        for key in keys[:12]:
            result[key] = _compact_draft_value(value[key], max_depth=max_depth - 1, max_items=max_items)
        if len(value) > len(result):
            result["_omitted_fields"] = len(value) - len(result)
        return result
    if isinstance(value, str) and len(value) > 500:
        return value[:500] + "... [truncated]"
    return value


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


def _attempt_draft_repair(
    gateway: AiGateway,
    *,
    request: DraftRequest,
    original_content: str | None,
    validation_errors: list[str],
    profile_name: str,
):
    bounded_original = str(original_content or "")[:2400]
    bounded_errors = validation_errors[:8]
    repair_prompt = (
        "Repair this SIEM AI draft response. Return exactly one JSON object and no markdown.\n"
        f"{artifact_policy()}"
        "Use the requested draft schema implied by the error list. Do not add claims that anything was saved, applied, "
        "approved, executed, blocked, deployed, committed, or changed.\n"
        f"Draft type: {request.draft_type}\n"
        f"Validation errors: {json.dumps(bounded_errors, sort_keys=True)}\n"
        f"Original response:\n{bounded_original}\n"
    )
    repaired = gateway.generate(
        AiGatewayRequest(
            prompt=repair_prompt,
            capability="text_generation",
            profile=profile_name,
            metadata={
                "context_type": request.context_type,
                "action": "draft_repair",
                "draft_type": request.draft_type,
                "read_only": True,
                "persisted": False,
                "applied": False,
                "repair_attempt": 1,
            },
        )
    )
    return repaired if repaired.status == "success" else None


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
