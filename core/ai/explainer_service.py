from __future__ import annotations

from dataclasses import dataclass
import json
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
from core.ai.gateway import AiGateway
from core.ai.models import AiGatewayRequest, AiRequestMetadata
from core.ai.profile_registry import profile_for_explain_action
from core.ai.soc_tool_executor import (
    build_deterministic_tool_plan,
    execute_tool_plan,
    normalize_tool_policy,
    should_skip_tools_for_gateway,
    tool_summary_for_prompt,
)
from core.ai.soc_tools import SocToolExecutionSummary

ALLOWED_EXPLAIN_ACTIONS = frozenset(
    {
        "explain_alert",
        "ask_anakin",
        "summarize",
        "explain",
        "suggestedactions",
        "why_important",
        "recommend_investigation",
        "summarize_incident",
        "recommend_next_steps",
        "explain_ip",
        "assess_reconnaissance",
        "summarize_activity",
        "explain_campaign",
        "explain_recon_activity",
        "investigate_cluster",
        "explain_response",
        "ask_dashboard",
        "explain_anomaly",
        "explain_detection",
    }
)


@dataclass(frozen=True)
class AiServiceResult:
    payload: dict[str, Any]
    status_code: int = 200


def explain_context(
    payload: dict[str, Any],
    *,
    gateway: AiGateway | None = None,
    config: AiGatewayConfig | None = None,
) -> AiServiceResult:
    if not isinstance(payload, dict):
        raise AiContextValidationError("JSON object body is required.")

    context_type = str(payload.get("context_type") or "").strip().lower()
    action = str(payload.get("action") or "").strip().lower()
    question = str(payload.get("question") or "").strip()
    context = payload.get("context") if isinstance(payload.get("context"), dict) else {}

    if not context_type:
        raise AiContextValidationError("context_type is required.")
    if not action:
        raise AiContextValidationError("action is required.")
    if action not in ALLOWED_EXPLAIN_ACTIONS:
        raise AiContextValidationError("action is unsupported.")
    if len(question) > 2000:
        raise AiContextValidationError("question is too large.")

    resolved_config = config if config is not None else load_ai_gateway_config()
    use_tools = bool(payload.get("use_tools"))
    tool_policy = normalize_tool_policy(payload.get("tool_policy"))
    ai_context = build_ai_context(
        context_type=context_type,
        context=context,
        config=resolved_config,
        question=question,
    )
    return _answer_from_context(
        ai_context,
        action=action,
        question=question,
        gateway=gateway,
        config=resolved_config,
        use_tools=use_tools,
        tool_policy=tool_policy,
        planning_context=context,
    )


def chat_about_siem(
    payload: dict[str, Any],
    *,
    gateway: AiGateway | None = None,
    config: AiGatewayConfig | None = None,
) -> AiServiceResult:
    if not isinstance(payload, dict):
        raise AiContextValidationError("JSON object body is required.")

    message = str(payload.get("message") or "").strip()
    if not message:
        raise AiContextValidationError("message is required.")
    if len(message) > 2000:
        raise AiContextValidationError("message is too large.")

    history = payload.get("client_history", [])
    if history is None:
        history = []
    if not isinstance(history, list):
        raise AiContextValidationError("client_history must be a list.")
    visible_context = payload.get("visible_context") if isinstance(payload.get("visible_context"), dict) else {}

    resolved_config = config if config is not None else load_ai_gateway_config()
    use_tools = bool(payload.get("use_tools"))
    tool_policy = normalize_tool_policy(payload.get("tool_policy"))
    ai_context = build_ai_context(
        context_type="general",
        context=visible_context,
        config=resolved_config,
        question=message,
        client_history=history,
    )
    return _answer_from_context(
        ai_context,
        action="general_chat",
        question=message,
        gateway=gateway,
        config=resolved_config,
        use_tools=use_tools,
        tool_policy=tool_policy,
        planning_context=visible_context,
    )


def service_error_response(error: AiContextError) -> AiServiceResult:
    return AiServiceResult(
        {
            "status": error.error_code,
            "answer": None,
            "insufficient_context": isinstance(error, AiContextValidationError),
            "context": {
                "context_type": None,
                "sources": [],
                "truncated": False,
                "omitted_count": 0,
                "insufficient_reason": str(error),
            },
            "metadata": _empty_metadata(error.error_code),
            "tools": _empty_tools(),
            "error": str(error),
        },
        status_code=error.status_code,
    )


def _answer_from_context(
    ai_context: AiContextPayload,
    *,
    action: str,
    question: str,
    gateway: AiGateway | None,
    config: AiGatewayConfig,
    use_tools: bool = False,
    tool_policy: dict[str, Any] | None = None,
    planning_context: dict[str, Any] | None = None,
) -> AiServiceResult:
    profile_name = profile_for_explain_action(action)
    profile = config.profile(profile_name)
    tools = _empty_tool_summary()
    if use_tools and not should_skip_tools_for_gateway(config):
        plan = build_deterministic_tool_plan(
            question=question,
            context_type=ai_context.context_type,
            context=planning_context or {},
            tool_policy=tool_policy,
        )
        tools = execute_tool_plan(
            plan,
            actor_role=getattr(current_user, "role", None),
            config=config,
            tool_policy=tool_policy,
        )

    has_tool_evidence = any(call.status == "success" and call.data not in (None, {}, []) for call in tools.calls)
    if ai_context.insufficient_context and not has_tool_evidence:
        return AiServiceResult(
            {
                "status": "insufficient_context",
                "answer": "I do not have enough SIEM context to answer safely.",
                "insufficient_context": True,
                "context": ai_context.metadata(),
                "metadata": _empty_metadata("insufficient_context", mode=config.mode),
                "tools": tools.as_dict(),
                "error": ai_context.insufficient_reason,
            },
            status_code=200,
        )

    prompt = _build_prompt(
        ai_context,
        action=action,
        question=question,
        tools=tools,
        config=config,
        profile_max_prompt_chars=profile.max_prompt_chars,
    )
    if len(prompt) > profile.max_prompt_chars:
        return AiServiceResult(
            {
                "status": "insufficient_context",
                "answer": "The available SIEM context is too large to send safely.",
                "insufficient_context": True,
                "context": {
                    **ai_context.metadata(),
                    "truncated": True,
                    "insufficient_reason": "Prompt exceeded configured AI profile size limit.",
                },
                "metadata": _empty_metadata("insufficient_context", mode=config.mode),
                "tools": tools.as_dict(),
                "error": "Prompt exceeded configured AI profile size limit.",
            },
            status_code=200,
        )

    resolved_gateway = gateway if gateway is not None else AiGateway(config=config)
    gateway_response = resolved_gateway.generate(
        AiGatewayRequest(
            prompt=prompt,
            capability="text_generation",
            profile=profile_name,
            metadata={
                "context_type": ai_context.context_type,
                "action": action,
                "read_only": True,
            },
        )
    )
    response_payload = gateway_response.as_dict()
    return AiServiceResult(
        {
            "status": response_payload["status"],
            "answer": response_payload["content"],
            "insufficient_context": False,
            "context": ai_context.metadata(),
            "metadata": response_payload["metadata"],
            "tools": tools.as_dict(),
            "error": response_payload["error"],
        },
        status_code=200,
    )


def _build_prompt(
    ai_context: AiContextPayload,
    *,
    action: str,
    question: str,
    tools: SocToolExecutionSummary | None = None,
    config: AiGatewayConfig | None = None,
    profile_max_prompt_chars: int | None = None,
) -> str:
    budget = profile_max_prompt_chars or (config.max_prompt_chars if config else 12000)
    tool_budget = max(1000, budget // 3)
    tools_json = json.dumps(
        tool_summary_for_prompt(tools, max_chars=tool_budget) if tools else _empty_tools(),
        default=str,
        sort_keys=True,
        indent=2,
    )
    context_json = _context_json_for_prompt(ai_context, budget=budget, tools_json=tools_json)
    question_line = question or _default_question(action, ai_context.context_type)
    return (
        "You are a read-only SIEM analyst assistant.\n"
        "Use only the supplied SIEM context. If the context is incomplete, say what is missing.\n"
        "Do not claim you checked data that is not included. Do not execute or suggest commands that mutate production.\n"
        "Read-tool results are evidence only; do not say remediation, blocking, approval, or SOAR execution happened.\n"
        "Recommendations must be analyst next steps only; do not say an action was taken.\n\n"
        "Do not repeat the alert description, list every visible field, or define generic security terms unless asked.\n"
        "Avoid robotic filler and generic advice such as 'continue monitoring' unless you name exactly what to inspect.\n"
        "Do not fabricate correlations, attack stages, geography, identity, or intent.\n"
        "Prioritize: concise assessment, what stands out, why it matters here, relevant correlations, supporting evidence, "
        "contradicting or benign evidence, uncertainty/confidence, missing evidence, and concrete read-only next steps.\n\n"
        f"Action: {action}\n"
        f"Question: {question_line}\n"
        f"Context type: {ai_context.context_type}\n"
        f"Context sources: {json.dumps(ai_context.metadata(), default=str, sort_keys=True)}\n\n"
        f"SIEM context:\n{context_json}\n\n"
        f"Read-only SOC tool evidence:\n{tools_json}\n\n"
        "Use task-appropriate concise sections. Include support, contradiction/benign alternatives, uncertainty, gaps, and next steps when evidence allows."
    )


def _context_json_for_prompt(ai_context: AiContextPayload, *, budget: int, tools_json: str) -> str:
    static_budget = 3600
    max_context_chars = max(1200, budget - static_budget - len(tools_json))
    bounded = _bound_prompt_value(ai_context.data)
    context_json = json.dumps(bounded, default=str, sort_keys=True, indent=2)
    if len(context_json) <= max_context_chars:
        return context_json

    evidence = _extract_evidence(ai_context.data)
    summary = {
        "summary": "SIEM context was compacted before prompt serialization because it exceeded the selected AI profile budget.",
        "context_type": ai_context.context_type,
        "primary": _primary_prompt_summary(ai_context.data),
        "_evidence": evidence,
        "_prompt_compaction": {
            "original_chars": len(json.dumps(ai_context.data, default=str, sort_keys=True)),
            "max_context_chars": max_context_chars,
            "reason": "profile_prompt_budget",
        },
    }
    context_json = json.dumps(summary, default=str, sort_keys=True, indent=2)
    if len(context_json) <= max_context_chars:
        return context_json
    summary["primary"] = _short_prompt_text(summary["primary"], max_chars=max(300, max_context_chars // 2))
    return json.dumps(summary, default=str, sort_keys=True, indent=2)


def _bound_prompt_value(value, *, depth: int = 0):
    if depth > 4:
        return _short_prompt_text(value, max_chars=220)
    if isinstance(value, list):
        limit = 8 if depth <= 2 else 4
        bounded = [_bound_prompt_value(item, depth=depth + 1) for item in value[:limit]]
        omitted = max(0, len(value) - len(bounded))
        if omitted:
            return {
                "items": bounded,
                "_evidence": {
                    "included": len(bounded),
                    "omitted": omitted,
                    "truncated": True,
                },
            }
        return bounded
    if isinstance(value, dict):
        bounded = {}
        for key, child in value.items():
            if key in {"raw", "raw_events", "full_payload", "full_context", "map_markers"}:
                records = child if isinstance(child, list) else []
                bounded[key] = {
                    "summary": "Raw or high-volume field omitted from AI prompt.",
                    "_evidence": {
                        "included": 0,
                        "omitted": len(records),
                        "truncated": bool(records),
                    },
                }
                continue
            bounded[key] = _bound_prompt_value(child, depth=depth + 1)
        return bounded
    return _short_prompt_text(value, max_chars=360 if depth <= 2 else 180)


def _extract_evidence(value) -> dict[str, object]:
    if isinstance(value, dict) and isinstance(value.get("_evidence"), dict):
        return value["_evidence"]
    evidence = {"included": {}, "omitted": {}, "truncated": False}
    if isinstance(value, dict):
        for key, child in value.items():
            if isinstance(child, list):
                evidence["included"][key] = min(len(child), 8)
                omitted = max(0, len(child) - 8)
                if omitted:
                    evidence["omitted"][key] = omitted
                    evidence["truncated"] = True
    return evidence


def _primary_prompt_summary(value):
    if not isinstance(value, dict):
        return _short_prompt_text(value, max_chars=800)
    for key in (
        "alert",
        "incident",
        "source_ip",
        "recon_activity",
        "response_registry",
        "dashboard_summary",
        "visible_context",
        "primary",
    ):
        if key in value:
            return _bound_prompt_value(value[key])
    return _bound_prompt_value(value)


def _short_prompt_text(value, *, max_chars: int):
    if value is None:
        return None
    if isinstance(value, (int, float, bool)):
        return value
    text = value if isinstance(value, str) else json.dumps(value, default=str, sort_keys=True)
    if len(text) <= max_chars:
        return value
    return f"{text[: max(0, max_chars - 3)]}..."


def _default_question(action: str, context_type: str) -> str:
    return f"Explain this {context_type.replace('_', ' ')} for an analyst using the action {action}."


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


def _empty_tool_summary() -> SocToolExecutionSummary:
    return SocToolExecutionSummary(used=False)


def _empty_tools() -> dict[str, Any]:
    return _empty_tool_summary().as_dict()


__all__ = [
    "AiContextError",
    "AiContextNotFoundError",
    "AiContextValidationError",
    "AiServiceResult",
    "chat_about_siem",
    "explain_context",
    "service_error_response",
]
