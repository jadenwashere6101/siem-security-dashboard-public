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
        "why_important",
        "recommend_investigation",
        "summarize_incident",
        "recommend_next_steps",
        "explain_ip",
        "assess_reconnaissance",
        "summarize_activity",
        "explain_campaign",
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

    prompt = _build_prompt(ai_context, action=action, question=question, tools=tools, config=config)
    if len(prompt) > config.max_prompt_chars:
        return AiServiceResult(
            {
                "status": "insufficient_context",
                "answer": "The available SIEM context is too large to send safely.",
                "insufficient_context": True,
                "context": {
                    **ai_context.metadata(),
                    "truncated": True,
                    "insufficient_reason": "Prompt exceeded configured AI size limit.",
                },
                "metadata": _empty_metadata("insufficient_context", mode=config.mode),
                "tools": tools.as_dict(),
                "error": "Prompt exceeded configured AI size limit.",
            },
            status_code=200,
        )

    resolved_gateway = gateway if gateway is not None else AiGateway(config=config)
    gateway_response = resolved_gateway.generate(
        AiGatewayRequest(
            prompt=prompt,
            capability="text_generation",
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
) -> str:
    context_json = json.dumps(ai_context.data, default=str, sort_keys=True, indent=2)
    tool_budget = max(1000, (config.max_prompt_chars // 3 if config else 4000))
    tools_json = json.dumps(
        tool_summary_for_prompt(tools, max_chars=tool_budget) if tools else _empty_tools(),
        default=str,
        sort_keys=True,
        indent=2,
    )
    question_line = question or _default_question(action, ai_context.context_type)
    return (
        "You are a read-only SIEM analyst assistant.\n"
        "Use only the supplied SIEM context. If the context is incomplete, say what is missing.\n"
        "Do not claim you checked data that is not included. Do not execute or suggest commands that mutate production.\n"
        "Read-tool results are evidence only; do not say remediation, blocking, approval, or SOAR execution happened.\n"
        "Recommendations must be analyst next steps only; do not say an action was taken.\n\n"
        f"Action: {action}\n"
        f"Question: {question_line}\n"
        f"Context type: {ai_context.context_type}\n"
        f"Context sources: {json.dumps(ai_context.metadata(), default=str, sort_keys=True)}\n\n"
        f"SIEM context:\n{context_json}\n\n"
        f"Read-only SOC tool evidence:\n{tools_json}\n\n"
        "Answer with concise sections: Summary, Key Evidence, Uncertainty, Recommended Next Steps."
    )


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
