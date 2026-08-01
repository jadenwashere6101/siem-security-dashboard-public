from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import os
from pathlib import Path
import re
import time
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

from core.ai.config import AI_MODE_LOCAL_ONLY, AiGatewayConfig, default_ai_profiles, load_ai_gateway_config
from core.ai.context_builder import AiContextPayload, AiContextSource
from core.ai.drafting_service import _build_draft_prompt
from core.ai.draft_schemas import DraftRequest
from core.ai.draft_schemas import validate_draft_payload
from core.ai.explainer_service import _build_prompt as build_explainer_prompt
from core.ai.gateway import AiGateway
from core.ai.investigation_planner import build_investigation_plan, classify_routing_profile
from core.ai.investigation_service import _build_correlation_prompt
from core.ai.profile_registry import (
    AI_INVOCATION_INVENTORY,
    AI_PROFILE_DEEP_BRIEFING,
    AI_PROFILE_DEVELOPER_ASSISTANT,
    AI_PROFILE_FAST_TRIAGE,
    AI_PROFILE_GUIDED_ANALYSIS,
    AiInvocationInventoryEntry,
    profile_for_chat,
    profile_for_draft_type,
    profile_for_explain_action,
    profile_for_investigation,
    profile_for_repo_assistant,
    profile_for_soc_briefing,
)
from core.ai.repo_assistant_service import _build_prompt as build_repo_prompt, classify_repo_question
from core.ai.repo_index import RepoChunk
from core.ai.soc_briefing_investigation_engine import InvestigationBudget
from core.ai.soc_tools import SocToolExecutionSummary

ROOT_CAUSE_PROMPT_TOO_LARGE = "prompt_too_large"
ROOT_CAUSE_STALE_CONTEXT = "stale_context"
ROOT_CAUSE_PROVIDER_TIMEOUT = "provider_timeout"
ROOT_CAUSE_INVALID_RESPONSE = "invalid_response"
ROOT_CAUSE_WORKER_UNAVAILABLE = "worker_unavailable"
ROOT_CAUSE_CITATION_CONTRACT = "citation_contract"
ROOT_CAUSE_FRONTEND_CONTRACT_MISMATCH = "frontend_contract_mismatch"

TERMINAL_MANUAL_BRIEFING_STATES = {"completed", "partial", "degraded", "failed", "blocked", "timed_out"}
LIVE_STATUS_ROUTE = "GET"
LIVE_SMOKE_ENV = "AI_ACCEPTANCE_LIVE_OLLAMA"
LIVE_SWEEP_ENV = "AI_ACCEPTANCE_LIVE_BACKEND_SWEEP"
LIVE_MANUAL_BRIEFING_MUTATION_ENV = "AI_ACCEPTANCE_CREATE_MANUAL_BRIEFING_JOB"
DEFAULT_LIVE_BASE_URL = "http://127.0.0.1:5051"
DEFAULT_LIVE_THROTTLE_SECONDS = 2.0
REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SOURCE_ROOT = REPO_ROOT / "frontend" / "src"
ENTITY_AI_CONTEXT_TYPES = {"alert", "source_ip", "incident", "recon_activity", "response_registry", "detection"}


@dataclass(frozen=True)
class FrontendAiOption:
    key: str
    source_file: str
    line_number: int
    options: dict[str, Any]


@dataclass(frozen=True)
class HarnessInventoryEntry:
    key: str
    frontend_surface: str
    backend_path: str
    selector_type: str
    selector: str
    profile: str
    notes: str = ""

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class AcceptanceCase:
    inventory_key: str
    action_name: str
    frontend_action_id: str
    backend_route: str
    context_type: str
    stale_policy: str
    sample_question: str
    frontend_options: dict[str, Any] = field(default_factory=dict)
    request_payload: dict[str, Any] = field(default_factory=dict)
    entity_id: str | int | None = None


@dataclass
class AcceptanceResult:
    action_button_name: str
    frontend_action_id: str
    backend_route: str
    context_type: str
    entity: str | int | None
    selected_profile: str
    selected_model: str
    prompt_size: int
    prompt_limit: int
    response_time_ms: int
    success: bool
    error_code: str | None
    stale_state_result: str
    response_usefulness_checks: dict[str, bool]
    root_cause: str | None = None
    notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AcceptanceReport:
    actions_discovered: int
    actions_covered: int
    results: list[AcceptanceResult]
    failures_by_root_cause: dict[str, list[str]] = field(default_factory=dict)
    live_smoke_results: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "actions_discovered": self.actions_discovered,
            "actions_covered": self.actions_covered,
            "failures_by_root_cause": dict(self.failures_by_root_cause),
            "results": [result.as_dict() for result in self.results],
            "live_smoke_results": list(self.live_smoke_results),
        }


def build_acceptance_cases() -> dict[str, AcceptanceCase]:
    inventory, frontend_options = build_complete_ai_inventory()
    return {entry.key: _case_for_entry(entry, frontend_options=frontend_options) for entry in inventory}


def build_complete_ai_inventory() -> tuple[tuple[HarnessInventoryEntry, ...], dict[str, dict[str, Any]]]:
    frontend_options: dict[str, dict[str, Any]] = {}
    entries: list[HarnessInventoryEntry] = []
    seen: set[str] = set()

    for discovered in discover_frontend_ai_option_entries():
        options = _with_large_entity_fixture(discovered.options, _normalize_context_type(discovered.options.get("contextType")))
        entry = _inventory_entry_for_frontend_option(discovered, options)
        if entry.key in seen:
            continue
        seen.add(entry.key)
        frontend_options[entry.key] = options
        entries.append(entry)

    for command in _default_command_contracts():
        entry = _inventory_entry_for_static_contract(command)
        if entry.key in seen:
            continue
        seen.add(entry.key)
        frontend_options[entry.key] = command
        entries.append(entry)

    for contract in _static_surface_contracts():
        entry = _inventory_entry_for_static_contract(contract)
        if entry.key in seen:
            continue
        seen.add(entry.key)
        frontend_options[entry.key] = contract
        entries.append(entry)

    return tuple(entries), frontend_options


def discover_frontend_ai_options(source_root: Path | None = None) -> dict[str, dict[str, Any]]:
    discovered: dict[str, dict[str, Any]] = {}
    for option in discover_frontend_ai_option_entries(source_root):
        discovered.setdefault(_frontend_contract_key(option.options, Path(option.source_file).name), option.options)
    for command in _default_command_contracts():
        discovered.setdefault(command["contract_key"], command)
    return discovered


def discover_frontend_ai_option_entries(source_root: Path | None = None) -> list[FrontendAiOption]:
    source_root = source_root or FRONTEND_SOURCE_ROOT
    discovered: list[FrontendAiOption] = []
    for path in sorted(source_root.glob("components/**/*.js")):
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(source_root).as_posix()
        for block, line_number in _extract_on_ask_ai_blocks(text):
            parsed = _parse_frontend_ai_options(block)
            if not parsed:
                continue
            key = _frontend_contract_key(parsed, path.name)
            unique = f"{key}.line_{line_number}"
            parsed = {**parsed, "contract_key": unique, "source_file": relative, "line_number": line_number}
            discovered.append(FrontendAiOption(unique, relative, line_number, parsed))
    return discovered


def run_offline_contract_tier(config: AiGatewayConfig | None = None) -> AcceptanceReport:
    resolved_config = config or _acceptance_config()
    inventory, _frontend_options = build_complete_ai_inventory()
    cases = build_acceptance_cases()
    results: list[AcceptanceResult] = []
    failures: dict[str, list[str]] = {}
    inventory_by_key = {entry.key: entry for entry in inventory}

    for key, entry in inventory_by_key.items():
        case = cases.get(key)
        if case is None:
            result = AcceptanceResult(
                action_button_name=entry.frontend_surface,
                frontend_action_id=entry.key,
                backend_route=entry.backend_path,
                context_type="unknown",
                entity=None,
                selected_profile=entry.profile,
                selected_model="unknown",
                prompt_size=0,
                prompt_limit=0,
                response_time_ms=0,
                success=False,
                error_code="missing_acceptance_case",
                stale_state_result="not_tested",
                response_usefulness_checks=_empty_usefulness(False),
                root_cause=ROOT_CAUSE_FRONTEND_CONTRACT_MISMATCH,
            )
        else:
            result = _run_case(entry, case, resolved_config)
        results.append(result)
        if not result.success and result.root_cause:
            failures.setdefault(result.root_cause, []).append(result.frontend_action_id)

    missing = sorted(set(inventory_by_key) - set(cases))
    for key in missing:
        failures.setdefault(ROOT_CAUSE_FRONTEND_CONTRACT_MISMATCH, []).append(key)

    return AcceptanceReport(
        actions_discovered=len(inventory_by_key),
        actions_covered=len(set(cases) & set(inventory_by_key)),
        results=results,
        failures_by_root_cause=failures,
    )


def run_optional_live_smoke_tier(config: AiGatewayConfig | None = None) -> list[dict[str, Any]]:
    if os.getenv(LIVE_SMOKE_ENV) != "1":
        return [
            {
                "enabled": False,
                "reason": f"Set {LIVE_SMOKE_ENV}=1 to run one live local Ollama smoke request per profile.",
            }
        ]

    resolved_config = config or load_ai_gateway_config()
    gateway = AiGateway(config=resolved_config)
    prompts = {
        AI_PROFILE_FAST_TRIAGE: "Reply with OK and one short SIEM triage note.",
        AI_PROFILE_GUIDED_ANALYSIS: "Reply with OK and one short evidence-gap note for a read-only SOC investigation.",
        AI_PROFILE_DEEP_BRIEFING: "Reply with OK and one short scheduled SOC briefing summary.",
        AI_PROFILE_DEVELOPER_ASSISTANT: "Reply with OK and one short repository architecture observation.",
    }
    results = []
    for profile_name, prompt in prompts.items():
        started = time.monotonic()
        try:
            from core.ai.models import AiGatewayRequest

            response = gateway.generate(AiGatewayRequest(prompt=prompt, profile=profile_name, capability="text_generation"))
            payload = response.as_dict()
            results.append(
                {
                    "enabled": True,
                    "profile": profile_name,
                    "model": payload["metadata"].get("model"),
                    "status": payload["status"],
                    "error": payload["error"],
                    "latency_ms": int((time.monotonic() - started) * 1000),
                }
            )
        except Exception as error:
            results.append(
                {
                    "enabled": True,
                    "profile": profile_name,
                    "status": "failed",
                    "error": str(error),
                    "latency_ms": int((time.monotonic() - started) * 1000),
                    "root_cause": ROOT_CAUSE_PROVIDER_TIMEOUT if "timeout" in str(error).lower() else "provider_error",
                }
            )
    return results


def run_acceptance_harness(*, include_live_smoke: bool = True, config: AiGatewayConfig | None = None) -> AcceptanceReport:
    report = run_offline_contract_tier(config=config)
    if include_live_smoke:
        report.live_smoke_results = run_optional_live_smoke_tier(config=config)
    return report


def run_live_backend_sweep(
    *,
    base_url: str | None = None,
    session_cookie: str | None = None,
    throttle_seconds: float = DEFAULT_LIVE_THROTTLE_SECONDS,
    create_manual_briefing_job: bool = False,
) -> dict[str, Any]:
    if os.getenv(LIVE_SWEEP_ENV) != "1":
        return {
            "enabled": False,
            "reason": f"Set {LIVE_SWEEP_ENV}=1 on the VM to run the authenticated production-safe live backend sweep.",
        }
    cookie = session_cookie or os.getenv("AI_ACCEPTANCE_SESSION_COOKIE", "")
    if not cookie:
        return {"enabled": True, "status": "blocked", "error": "AI_ACCEPTANCE_SESSION_COOKIE is required."}

    resolved_base_url = (base_url or os.getenv("AI_ACCEPTANCE_BASE_URL") or DEFAULT_LIVE_BASE_URL).rstrip("/")
    config = load_ai_gateway_config()
    ids = _discover_live_entities(resolved_base_url, cookie)
    inventory, _frontend_options = build_complete_ai_inventory()
    cases = build_acceptance_cases()
    representative_plan = _select_live_representative_cases(inventory, cases)
    rows: list[dict[str, Any]] = []
    failures: dict[str, list[str]] = {}

    status_rows = [
        _live_status_check(resolved_base_url, cookie, "/ai/status", "status.ai_gateway", config),
        _live_status_check(resolved_base_url, cookie, "/ai/repo/status", "status.repo_assistant", config),
    ]
    for row in status_rows:
        rows.append(row)
        if not row.get("success"):
            failures.setdefault(str(row.get("root_cause") or "other"), []).append(str(row.get("frontend_action_id")))

    for entry, case in representative_plan:
        if entry.backend_path == "soc_briefing_worker":
            row = _live_manual_briefing_check(
                resolved_base_url,
                cookie,
                entry,
                create_manual_briefing_job=create_manual_briefing_job or os.getenv(LIVE_MANUAL_BRIEFING_MUTATION_ENV) == "1",
            )
        else:
            row = _live_ai_action_check(resolved_base_url, cookie, entry, case, ids, config)
        rows.append(row)
        if not row.get("success"):
            failures.setdefault(str(row.get("root_cause") or "other"), []).append(str(row.get("frontend_action_id")))
        time.sleep(max(0.0, throttle_seconds))

    manual_briefing_mutation = create_manual_briefing_job or os.getenv(LIVE_MANUAL_BRIEFING_MUTATION_ENV) == "1"
    return {
        "enabled": True,
        "base_url": resolved_base_url,
        "offline_actions_discovered": len(inventory),
        "offline_actions_covered": len(cases),
        "actions_discovered": len(inventory),
        "representative_calls_planned": len(representative_plan) + len(status_rows),
        "actions_invoked": len(rows),
        "estimated_runtime_seconds": int((len(representative_plan) + len(status_rows)) * max(0.0, throttle_seconds) + 240),
        "entity_discovery": ids,
        "failures_by_root_cause": failures,
        "results": rows,
        "safety": {
            "offline_full_button_coverage": True,
            "live_strategy": "representative_unique_backend_execution_paths",
            "draft_routes_preview_only": True,
            "allow_automatic_draft_false": True,
            "manual_briefing_create_job": manual_briefing_mutation,
            "actions_confirm_route_skipped": True,
            "production_mutations_allowed": False,
        },
    }


def render_live_sweep_markdown(result: dict[str, Any]) -> str:
    lines = ["# Anakin Live Backend Acceptance Sweep", ""]
    if not result.get("enabled"):
        lines.append(f"Disabled: {result.get('reason')}")
        return "\n".join(lines) + "\n"
    lines.extend(
        [
            f"- Base URL: {result.get('base_url')}",
            f"- Offline actions covered: {result.get('offline_actions_covered', result.get('actions_discovered'))}",
            f"- Representative live calls planned: {result.get('representative_calls_planned', result.get('actions_invoked'))}",
            f"- Representative live calls invoked: {result.get('actions_invoked')}",
            f"- Estimated runtime seconds: {result.get('estimated_runtime_seconds')}",
            f"- Failures: {sum(len(items) for items in (result.get('failures_by_root_cause') or {}).values())}",
            "",
            "## Failures By Root Cause",
        ]
    )
    failures = result.get("failures_by_root_cause") or {}
    if not failures:
        lines.append("- None")
    for root_cause, action_ids in sorted(failures.items()):
        lines.append(f"- `{root_cause}`: {len(action_ids)}")
        for action_id in action_ids:
            lines.append(f"  - `{action_id}`")
    lines.extend(["", "## Results"])
    for row in result.get("results") or []:
        status = "PASS" if row.get("success") else f"FAIL {row.get('error_code') or row.get('error') or 'unknown'}"
        lines.append(
            f"- {status} `{row.get('frontend_action_id')}` {row.get('execution_path') or row.get('route')} "
            f"entity=`{row.get('entity')}` profile=`{row.get('profile')}` model=`{row.get('model')}` "
            f"prompt={row.get('prompt_size')}/{row.get('prompt_limit')} latency={row.get('latency_ms')}ms"
        )
    return "\n".join(lines) + "\n"


def _select_live_representative_cases(
    inventory: tuple[HarnessInventoryEntry, ...],
    cases: dict[str, AcceptanceCase],
) -> list[tuple[HarnessInventoryEntry, AcceptanceCase]]:
    by_key = {entry.key: entry for entry in inventory}
    selected: list[tuple[HarnessInventoryEntry, AcceptanceCase]] = []
    used: set[str] = set()

    def add(key: str) -> None:
        entry = by_key[key]
        selected.append((entry, cases[key]))
        used.add(key)

    def add_first(label: str, predicate) -> None:
        for entry in inventory:
            if entry.key in used:
                continue
            if predicate(entry):
                selected.append((entry, cases[entry.key]))
                used.add(entry.key)
                return
        raise ValueError(f"Missing live representative case: {label}")

    add_first(
        "POST /ai/explain fast_triage",
        lambda entry: entry.backend_path == "POST /ai/explain" and entry.profile == AI_PROFILE_FAST_TRIAGE,
    )
    add_first(
        "POST /ai/explain guided_analysis",
        lambda entry: entry.backend_path == "POST /ai/explain" and entry.profile == AI_PROFILE_GUIDED_ANALYSIS,
    )
    add_first("POST /ai/drafts", lambda entry: entry.backend_path == "POST /ai/drafts")
    add_first("POST /ai/investigations", lambda entry: entry.backend_path == "POST /ai/investigations")
    add("frontend.floating_chat.general")
    add("frontend.repo_architecture.chat.factual")
    add("frontend.repo_architecture.chat.evaluative")
    add("frontend.ai_action.preview.add_incident_note")
    add("worker.soc_briefing.manual_run_now")
    return selected


def _discover_live_entities(base_url: str, cookie: str) -> dict[str, Any]:
    alerts = _live_get_json(base_url, "/alerts?limit=1&offset=0", cookie)
    alert_row = _first_row(alerts, "alerts", "items", "results", "data")
    source_ip = alert_row.get("source_ip") if isinstance(alert_row, dict) else None
    incidents = _live_get_json(base_url, "/incidents?limit=1&offset=0", cookie)
    incident_row = _first_row(incidents, "incidents", "items", "results", "data")
    recon = _live_get_json(base_url, "/recon-activities?limit=1&offset=0", cookie)
    recon_row = _first_row(recon, "activities", "recon_activities", "items", "results", "data")
    registry = _live_get_json(base_url, "/response-registry?limit=1&offset=0", cookie)
    registry_row = _first_row(registry, "records", "items", "results", "data")
    return {
        "alert_id": _row_id(alert_row, "alert_id", "id"),
        "source_ip": source_ip or "127.0.0.1",
        "incident_id": _row_id(incident_row, "incident_id", "id"),
        "activity_id": _row_id(recon_row, "activity_id", "id"),
        "registry_id": _row_id(registry_row, "registry_id", "id"),
        "discovery_errors": [
            value.get("_error")
            for value in (alerts, incidents, recon, registry)
            if isinstance(value, dict) and value.get("_error")
        ],
    }


def _live_ai_action_check(
    base_url: str,
    cookie: str,
    entry: AiInvocationInventoryEntry,
    case: AcceptanceCase,
    ids: dict[str, Any],
    config: AiGatewayConfig,
) -> dict[str, Any]:
    payload = _live_payload_for_case(entry, case, ids)
    route = _route_path(entry.backend_path)
    profile = config.profile(entry.profile)
    prompt_size = case.prompt_size if hasattr(case, "prompt_size") else _safe_prompt_size(entry, case, config)
    started = time.monotonic()
    status_code = 0
    body: dict[str, Any] = {}
    error_text = None
    try:
        status_code, body = _live_post_json(base_url, route, payload, cookie)
    except Exception as error:
        error_text = str(error)
    latency_ms = int((time.monotonic() - started) * 1000)
    metadata = body.get("metadata") if isinstance(body.get("metadata"), dict) else {}
    status = body.get("status") or metadata.get("status")
    error_value = body.get("error") or error_text
    root_cause = _root_cause_from_live(status=status, error=error_value, http_status=status_code, body=body)
    success_statuses = {"success", "partial"}
    if entry.backend_path == "POST /ai/actions/preview":
        success_statuses.add("preview_ready")
    success = 200 <= status_code < 300 and status in success_statuses and not error_value
    return {
        "frontend_action_id": entry.key,
        "execution_path": entry.backend_path,
        "action": case.action_name,
        "route": route,
        "entity": _stable_ai_entity_id(payload.get("context") or payload.get("visible_context")),
        "context_type": payload.get("context_type") or "general",
        "profile": entry.profile,
        "model": metadata.get("model") or profile.model,
        "prompt_size": prompt_size,
        "prompt_limit": profile.max_prompt_chars,
        "latency_ms": latency_ms,
        "http_status": status_code,
        "provider_status": metadata.get("status") or status,
        "success": success,
        "error_code": status if not success else None,
        "error": error_value,
        "root_cause": None if success else root_cause,
    }


def _live_status_check(base_url: str, cookie: str, path: str, frontend_action_id: str, config: AiGatewayConfig) -> dict[str, Any]:
    started = time.monotonic()
    status_code = 0
    body: dict[str, Any] = {}
    error_text = None
    try:
        status_code, body = _live_get_json_with_status(base_url, path, cookie)
    except Exception as error:
        error_text = str(error)
    latency_ms = int((time.monotonic() - started) * 1000)
    gateway = body.get("gateway") if isinstance(body.get("gateway"), dict) else {}
    providers = body.get("providers") if isinstance(body.get("providers"), list) else []
    provider = providers[0] if providers and isinstance(providers[0], dict) else {}
    status = body.get("status") or provider.get("status") or gateway.get("mode") or ("success" if 200 <= status_code < 300 else "failed")
    error_value = body.get("error") or provider.get("error") or error_text
    success = 200 <= status_code < 300 and not error_value
    profile_name = AI_PROFILE_DEVELOPER_ASSISTANT if path == "/ai/repo/status" else AI_PROFILE_FAST_TRIAGE
    profile = config.profile(profile_name)
    return {
        "frontend_action_id": frontend_action_id,
        "execution_path": f"GET {path}",
        "action": f"Status check {path}",
        "route": path,
        "entity": None,
        "context_type": "status",
        "profile": profile_name,
        "model": provider.get("model") or gateway.get("local_model") or profile.model,
        "prompt_size": 0,
        "prompt_limit": profile.max_prompt_chars,
        "latency_ms": latency_ms,
        "http_status": status_code,
        "provider_status": status,
        "success": success,
        "error_code": None if success else status,
        "error": error_value,
        "root_cause": None if success else _root_cause_from_live(status=status, error=error_value, http_status=status_code, body=body),
    }


def _live_manual_briefing_check(
    base_url: str,
    cookie: str,
    entry: AiInvocationInventoryEntry,
    *,
    create_manual_briefing_job: bool,
) -> dict[str, Any]:
    started = time.monotonic()
    if create_manual_briefing_job:
        status_code, body = _live_post_json(base_url, "/soc-briefings/run-now", {}, cookie)
    else:
        status_code, body = _live_get_json_with_status(base_url, "/soc-briefings/control", cookie)
    lifecycle = body.get("manual_lifecycle") or body.get("lifecycle") or {}
    worker = body.get("worker") or body.get("worker_status") or {}
    status = lifecycle.get("status") or ("status_only" if status_code else "failed")
    success = bool(200 <= status_code < 300 and (status == "status_only" or status in TERMINAL_MANUAL_BRIEFING_STATES or status in {"queued", "running"}))
    root_cause = None if success else ROOT_CAUSE_WORKER_UNAVAILABLE
    return {
        "frontend_action_id": entry.key,
        "execution_path": "POST /soc-briefings/run-now" if create_manual_briefing_job else "GET /soc-briefings/control",
        "action": entry.frontend_surface,
        "route": "/soc-briefings/run-now" if create_manual_briefing_job else "/soc-briefings/control",
        "entity": lifecycle.get("job_id") or lifecycle.get("job", {}).get("id"),
        "context_type": "soc_briefing",
        "profile": entry.profile,
        "model": None,
        "prompt_size": None,
        "prompt_limit": None,
        "latency_ms": int((time.monotonic() - started) * 1000),
        "http_status": status_code,
        "provider_status": lifecycle.get("provider_status"),
        "worker_status": worker.get("status") if isinstance(worker, dict) else worker,
        "success": success,
        "error_code": None if success else status,
        "error": body.get("error"),
        "root_cause": root_cause,
        "mutation_performed": create_manual_briefing_job,
    }


def _live_repo_assistant_checks(base_url: str, cookie: str, config: AiGatewayConfig) -> list[dict[str, Any]]:
    rows = []
    profile = config.profile(AI_PROFILE_DEVELOPER_ASSISTANT)
    for label, question in (
        ("repo.factual.soar_worker", "Where is the SOAR worker implemented?"),
        ("repo.evaluative.impressive_feature", "What is my most impressive feature?"),
    ):
        started = time.monotonic()
        status_code, body = _live_post_json(base_url, "/ai/repo/chat", {"message": question}, cookie)
        metadata = body.get("metadata") if isinstance(body.get("metadata"), dict) else {}
        error_value = body.get("error")
        success = 200 <= status_code < 300 and body.get("status") == "success" and bool(body.get("answer"))
        rows.append(
            {
                "frontend_action_id": label,
                "action": question,
                "route": "/ai/repo/chat",
                "entity": "repository",
                "context_type": "repository",
                "profile": AI_PROFILE_DEVELOPER_ASSISTANT,
                "model": metadata.get("model") or profile.model,
                "prompt_size": None,
                "prompt_limit": profile.max_prompt_chars,
                "latency_ms": int((time.monotonic() - started) * 1000),
                "http_status": status_code,
                "provider_status": metadata.get("status") or body.get("status"),
                "success": success,
                "error_code": None if success else body.get("status"),
                "error": error_value,
                "root_cause": None if success else _root_cause_from_live(status=body.get("status"), error=error_value, http_status=status_code, body=body),
            }
        )
    return rows


def _live_payload_for_case(entry: AiInvocationInventoryEntry, case: AcceptanceCase, ids: dict[str, Any]) -> dict[str, Any]:
    payload = json.loads(json.dumps(case.request_payload, default=str))
    if entry.backend_path in {"POST /ai/chat", "POST /ai/repo/chat"}:
        return payload
    if entry.backend_path == "POST /ai/actions/preview":
        preview_payload = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
        if payload.get("action_type") == "add_incident_note" and ids.get("incident_id"):
            preview_payload["incident_id"] = ids["incident_id"]
        payload["payload"] = preview_payload
        return payload
    context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    context_type = payload.get("context_type") or case.context_type
    if context_type == "alert" and ids.get("alert_id"):
        context["alert_id"] = ids["alert_id"]
    if context_type == "incident" and ids.get("incident_id"):
        context["incident_id"] = ids["incident_id"]
    if context_type == "source_ip" and ids.get("source_ip"):
        context["source_ip"] = ids["source_ip"]
    if context_type == "recon_activity" and ids.get("activity_id"):
        context["activity_id"] = ids["activity_id"]
    if context_type == "response_registry" and ids.get("registry_id"):
        context["registry_id"] = ids["registry_id"]
    payload["context"] = context
    if entry.backend_path == "POST /ai/investigations":
        payload["allow_automatic_draft"] = False
    return payload


def _safe_prompt_size(entry: AiInvocationInventoryEntry, case: AcceptanceCase, config: AiGatewayConfig) -> int | None:
    try:
        return len(_prompt_for_case(entry, case, config))
    except Exception:
        return None


def _route_path(backend_path: str) -> str:
    if backend_path.startswith("POST "):
        return backend_path.split(" ", 1)[1]
    return backend_path


def _root_cause_from_live(*, status: Any, error: Any, http_status: int, body: dict[str, Any]) -> str:
    status_text = str(status or body.get("status") or "").lower()
    error_text = str(error or body.get("error") or body.get("error_code") or "").lower()
    text = f"{status_text} {error_text}"
    if "prompt" in text and ("too large" in text or "exceed" in text):
        return ROOT_CAUSE_PROMPT_TOO_LARGE
    if "stale" in text:
        return ROOT_CAUSE_STALE_CONTEXT
    if (
        status_text in {"provider_timeout", "timeout", "timed_out"}
        or error_text in {"provider_timeout", "timeout", "timed_out"}
        or "timed out" in error_text
        or "timeout" in error_text
    ):
        return ROOT_CAUSE_PROVIDER_TIMEOUT
    if "citation" in text or "grounding" in text:
        return ROOT_CAUSE_CITATION_CONTRACT
    if "worker" in text and ("unavailable" in text or "offline" in text):
        return ROOT_CAUSE_WORKER_UNAVAILABLE
    if http_status in {400, 404, 409, 422}:
        return ROOT_CAUSE_FRONTEND_CONTRACT_MISMATCH
    if "invalid" in text or "parse" in text or "schema" in text:
        return ROOT_CAUSE_INVALID_RESPONSE
    return "other"


def _live_get_json(base_url: str, path: str, cookie: str) -> dict[str, Any]:
    status, body = _live_get_json_with_status(base_url, path, cookie)
    if status >= 400:
        body.setdefault("_error", f"GET {path} returned {status}")
    return body


def _live_get_json_with_status(base_url: str, path: str, cookie: str) -> tuple[int, dict[str, Any]]:
    request = urllib_request.Request(f"{base_url}{path}", headers={"Cookie": cookie, "Accept": "application/json"})
    return _send_json_request(request)


def _live_post_json(base_url: str, path: str, payload: dict[str, Any], cookie: str) -> tuple[int, dict[str, Any]]:
    encoded = json.dumps(payload).encode("utf-8")
    request = urllib_request.Request(
        f"{base_url}{path}",
        data=encoded,
        method="POST",
        headers={"Cookie": cookie, "Accept": "application/json", "Content-Type": "application/json"},
    )
    return _send_json_request(request)


def _send_json_request(request: urllib_request.Request) -> tuple[int, dict[str, Any]]:
    try:
        with urllib_request.urlopen(request, timeout=240) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return int(response.status), _json_object(raw)
    except urllib_error.HTTPError as error:
        raw = error.read().decode("utf-8", errors="replace")
        return int(error.code), _json_object(raw)


def _json_object(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {"_raw": raw, "_error": "non_json_response"}
    return parsed if isinstance(parsed, dict) else {"data": parsed}


def _first_row(payload: dict[str, Any], *keys: str) -> dict[str, Any]:
    for key in keys:
        value = payload.get(key) if isinstance(payload, dict) else None
        if isinstance(value, list) and value and isinstance(value[0], dict):
            return value[0]
        if isinstance(value, dict):
            nested = _first_row(value, "items", "results", "data", "records", "alerts", "incidents")
            if nested:
                return nested
    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        return payload[0]
    return {}


def _row_id(row: Any, *keys: str) -> int | None:
    if not isinstance(row, dict):
        return None
    for key in keys:
        if row.get(key) not in (None, ""):
            try:
                return int(row[key])
            except (TypeError, ValueError):
                return None
    return None


def render_markdown_report(report: AcceptanceReport) -> str:
    lines = [
        "# Anakin AI Acceptance Harness Report",
        "",
        f"- Actions discovered: {report.actions_discovered}",
        f"- Actions covered: {report.actions_covered}",
        f"- Failures: {sum(len(items) for items in report.failures_by_root_cause.values())}",
        "",
        "## Failures By Root Cause",
    ]
    if report.failures_by_root_cause:
        for root_cause, action_ids in sorted(report.failures_by_root_cause.items()):
            lines.append(f"- `{root_cause}`: {len(action_ids)}")
            for action_id in action_ids:
                lines.append(f"  - `{action_id}`")
    else:
        lines.append("- None")

    lines.extend(["", "## Actions", ""])
    for result in report.results:
        status = "PASS" if result.success else f"FAIL {result.error_code or 'unknown'}"
        lines.append(
            f"- {status} `{result.frontend_action_id}` "
            f"{result.backend_route} profile=`{result.selected_profile}` "
            f"prompt={result.prompt_size}/{result.prompt_limit}ms={result.response_time_ms}"
        )

    lines.extend(["", "## Live Smoke", ""])
    for smoke in report.live_smoke_results:
        lines.append(f"- `{smoke.get('profile', 'all')}`: {json.dumps(smoke, sort_keys=True)}")
    return "\n".join(lines) + "\n"


def _run_case(entry: AiInvocationInventoryEntry, case: AcceptanceCase, config: AiGatewayConfig) -> AcceptanceResult:
    started = time.monotonic()
    profile = config.profile(entry.profile)
    try:
        prompt = _prompt_for_case(entry, case, config)
        prompt_error = None
    except Exception as error:
        prompt = ""
        prompt_error = str(error)
    response_time_ms = int((time.monotonic() - started) * 1000)
    prompt_size = len(prompt)
    usefulness = _usefulness_checks(_sample_response_for_case(entry, case))
    if entry.backend_path == "POST /ai/drafts":
        draft_type = str(case.request_payload.get("draft_type") or "investigation_checklist")
        try:
            parsed_sample = json.loads(_sample_response_for_case(entry, case))
        except json.JSONDecodeError:
            parsed_sample = None
        draft_validation = validate_draft_payload(draft_type, parsed_sample)
        usefulness["draft_schema_valid"] = draft_validation.valid
        if draft_validation.valid:
            usefulness["has_assessment_or_title"] = True
            usefulness["has_uncertainty_or_gaps"] = True
            usefulness["has_next_steps_or_checks"] = True
    stale_result = _stale_result(case)
    success = prompt_error is None and prompt_size <= profile.max_prompt_chars and all(usefulness.values()) and _stale_ok(stale_result)
    error_code = None
    root_cause = None
    if prompt_error is not None:
        error_code = "frontend_request_contract_failed"
        root_cause = ROOT_CAUSE_FRONTEND_CONTRACT_MISMATCH
    elif prompt_size > profile.max_prompt_chars:
        error_code = "prompt_exceeded_profile_limit"
        root_cause = ROOT_CAUSE_PROMPT_TOO_LARGE
    elif not all(usefulness.values()):
        error_code = "generic_or_empty_response_contract"
        root_cause = ROOT_CAUSE_INVALID_RESPONSE
    elif not _stale_ok(stale_result):
        error_code = "stale_state_contract_failed"
        root_cause = ROOT_CAUSE_STALE_CONTEXT

    return AcceptanceResult(
        action_button_name=case.action_name,
        frontend_action_id=case.frontend_action_id,
        backend_route=case.backend_route,
        context_type=case.context_type,
        entity=case.entity_id,
        selected_profile=entry.profile,
        selected_model=profile.model,
        prompt_size=prompt_size,
        prompt_limit=profile.max_prompt_chars,
        response_time_ms=response_time_ms,
        success=success,
        error_code=error_code,
        stale_state_result=stale_result,
        response_usefulness_checks=usefulness,
        root_cause=root_cause,
        notes=prompt_error or "",
    )


def _prompt_for_case(entry: AiInvocationInventoryEntry, case: AcceptanceCase, config: AiGatewayConfig) -> str:
    profile = config.profile(entry.profile)
    if entry.backend_path == "POST /ai/explain":
        payload = case.request_payload
        return build_explainer_prompt(
            _fixture_context(case.context_type),
            action=str(payload.get("action") or entry.selector),
            question=str(payload.get("question") or case.sample_question),
            config=config,
            profile_max_prompt_chars=profile.max_prompt_chars,
        )
    if entry.backend_path == "POST /ai/chat":
        return build_explainer_prompt(
            _fixture_context("general"),
            action="general_chat",
            question=case.sample_question,
            config=config,
            profile_max_prompt_chars=profile.max_prompt_chars,
        )
    if entry.backend_path == "POST /ai/drafts":
        payload = case.request_payload
        request = DraftRequest(
            draft_type=str(payload.get("draft_type") or "investigation_checklist"),
            instruction=str(payload.get("instruction") or case.sample_question),
            context_type=str(payload.get("context_type") or "alert"),
            context=payload.get("context") if isinstance(payload.get("context"), dict) else {"alert_id": 1001},
            client_request_id="acceptance-draft-1001",
        )
        return _build_draft_prompt(
            request,
            _fixture_context(request.context_type),
            SocToolExecutionSummary(used=False),
            config=config,
            profile_max_prompt_chars=profile.max_prompt_chars,
        )
    if entry.backend_path == "POST /ai/investigations":
        payload = case.request_payload
        context_type = str(payload.get("context_type") or "alert")
        request_context = payload.get("context") if isinstance(payload.get("context"), dict) else {"alert_id": 1001}
        context = _fixture_context(context_type)
        plan = build_investigation_plan(context_type=context_type, context=request_context, question=case.sample_question)
        routing = classify_routing_profile(
            workflow_type=plan.workflow_type,
            context_type=plan.context_type,
            context_payload=context,
            planned_tool_calls=len(plan.tool_calls),
            successful_sources=len(context.sources),
            failed_sources=0,
            truncated=context.truncated,
            draft_decision={"decision": "skipped", "reason": "acceptance contract"},
            config=config,
            remaining_timeout_seconds=60,
        )
        return _build_correlation_prompt(
            plan=plan,
            question=str(payload.get("question") or case.sample_question),
            ai_context=context,
            tools=SocToolExecutionSummary(used=False),
            routing=routing,
            config=config,
            profile_max_prompt_chars=profile.max_prompt_chars,
        )
    if entry.backend_path == "POST /ai/repo/chat":
        return build_repo_prompt(
            case.sample_question,
            history=[],
            chunks=_repo_chunks(),
            max_prompt_chars=profile.max_prompt_chars,
            question_type=classify_repo_question(case.sample_question),
        )
    if entry.backend_path == "POST /ai/actions/preview":
        return json.dumps(
            {
                "non_mutating_ai_action_preview_contract": True,
                "request": case.request_payload,
                "expected_status": "preview_ready",
                "confirm_route_requires_explicit_token": True,
                "production_mutation_allowed": False,
            },
            default=str,
            sort_keys=True,
            indent=2,
        )
    if entry.backend_path == "soc_briefing_worker":
        budget = InvestigationBudget(max_prompt_chars=min(8000, profile.max_prompt_chars), max_prompt_tokens=3000)
        evidence = _fixture_context("recon_activity").metadata()
        return (
            "You are generating a read-only manual/scheduled SOC briefing.\n"
            "Preserve queued, running, completed, partial, failed, blocked, and timed_out lifecycle visibility.\n"
            f"Budget: {json.dumps(budget.as_dict(), sort_keys=True)}\n"
            f"Evidence: {json.dumps(evidence, sort_keys=True)}\n"
            f"Question: {case.sample_question}\n"
        )
    raise ValueError(f"Unsupported acceptance backend path: {entry.backend_path}")


def _case_for_entry(
    entry: HarnessInventoryEntry | AiInvocationInventoryEntry,
    *,
    frontend_options: dict[str, dict[str, Any]],
) -> AcceptanceCase:
    fallback_context_type = _context_type_for_entry(entry)
    options = _frontend_options_for_entry(entry, fallback_context_type, frontend_options)
    context_type = _normalize_context_type(options.get("contextType")) or fallback_context_type
    payload, route = build_frontend_realistic_request(options, active_section=_active_section_for_context(context_type))
    if entry.backend_path in {"soc_briefing_worker", "POST /ai/repo/chat"}:
        route = entry.backend_path
    else:
        route = entry.backend_path
    return AcceptanceCase(
        inventory_key=entry.key,
        action_name=entry.frontend_surface,
        frontend_action_id=entry.key,
        backend_route=route,
        context_type=context_type,
        stale_policy=_stale_policy_for_entry(entry),
        sample_question=options.get("question") or options.get("instruction") or _question_for_entry(entry, context_type),
        frontend_options=options,
        request_payload=payload,
        entity_id=_stable_ai_entity_id(payload.get("context") or payload.get("visible_context") or options.get("context")),
    )


def build_frontend_realistic_request(options: dict[str, Any], *, active_section: str = "dashboard") -> tuple[dict[str, Any], str]:
    explicit_route = options.get("route")
    if explicit_route == "soc_briefing_worker":
        return {"mode": "status_only", "create_job": False}, "soc_briefing_worker"
    if explicit_route == "POST /ai/actions/preview":
        return (
            {
                "action_type": options.get("action_type") or "add_incident_note",
                "payload": options.get("payload") if isinstance(options.get("payload"), dict) else {"incident_id": 2002, "note_text": "Acceptance preview only."},
                "idempotency_key": options.get("idempotency_key") or "acceptance-preview-action-2002",
                "source_draft": options.get("source_draft") if isinstance(options.get("source_draft"), dict) else {"draft_type": "incident_note", "read_only": True},
            },
            "POST /ai/actions/preview",
        )
    if explicit_route == "POST /ai/chat":
        return (
            {
                "message": options.get("message") or options.get("question") or "What should I inspect first in this workspace?",
                "visible_context": options.get("visible_context") if isinstance(options.get("visible_context"), dict) else _visible_context_fixture(active_section),
                "client_history": options.get("client_history") if isinstance(options.get("client_history"), list) else [],
                "use_tools": options.get("useTools", True) is not False,
                "tool_policy": options.get("toolPolicy") or {"max_tool_calls": 5, "time_window_hours": 24},
            },
            "POST /ai/chat",
        )
    if explicit_route == "POST /ai/repo/chat":
        payload = {
            "message": options.get("message") or options.get("question") or "What is my most impressive feature?",
        }
        if isinstance(options.get("client_history"), list):
            payload["client_history"] = options["client_history"]
        if isinstance(options.get("refresh"), bool):
            payload["refresh"] = options["refresh"]
        return payload, "POST /ai/repo/chat"

    normalized_context_type = _normalize_context_type(options.get("contextType"))
    entity_context = options.get("context") if isinstance(options.get("context"), dict) else {}
    should_include_visible = normalized_context_type not in ENTITY_AI_CONTEXT_TYPES
    contextual_command = {
        "id": options.get("commandId") or f"contextual.{options.get('contextType') or 'workspace'}.{options.get('action') or options.get('draftType') or 'ask'}",
        "label": options.get("title") or options.get("action") or options.get("draftType") or "Ask Anakin",
        "intent": options.get("draftType") and "draft" or (options.get("investigation") and "investigate") or options.get("action") or "ask_anakin",
        "read_only": True,
    }
    context = {
        **(_visible_context_fixture(active_section) if should_include_visible else {"active_section": active_section}),
        "command": contextual_command,
        **entity_context,
    }
    if options.get("draftType"):
        return (
            {
                "draft_type": options.get("draftType"),
                "instruction": options.get("instruction") or options.get("question") or "",
                "context_type": options.get("contextType"),
                "context": context,
                "use_tools": options.get("useTools", True) is not False,
                "tool_policy": options.get("toolPolicy") or {"max_tool_calls": 3, "time_window_hours": 24},
            },
            "POST /ai/drafts",
        )
    if options.get("investigation"):
        return (
            {
                "context_type": options.get("contextType"),
                "context": context,
                "question": options.get("question") or "",
                "tool_policy": options.get("toolPolicy") or {"max_tool_calls": 5, "time_window_hours": 24},
                "allow_automatic_draft": False,
            },
            "POST /ai/investigations",
        )
    return (
        {
            "context_type": options.get("contextType"),
            "action": options.get("action"),
            "question": options.get("question") or "",
            "context": context,
        },
        "POST /ai/explain",
    )


def _inventory_entry_for_frontend_option(discovered: FrontendAiOption, options: dict[str, Any]) -> HarnessInventoryEntry:
    _payload, route = build_frontend_realistic_request(options, active_section=_active_section_for_context(_normalize_context_type(options.get("contextType"))))
    selector = str(options.get("draftType") or options.get("action") or "ask_anakin")
    if route == "POST /ai/drafts":
        selector_type = "draft_type"
        profile = profile_for_draft_type(selector)
    elif route == "POST /ai/investigations":
        selector_type = "investigation_workflow"
        profile = profile_for_investigation()
    elif route == "POST /ai/explain":
        selector_type = "explain_action"
        profile = profile_for_explain_action(selector)
    elif route == "POST /ai/actions/preview":
        selector_type = "action_preview"
        profile = profile_for_investigation()
    else:
        selector_type = "route"
        profile = profile_for_chat()
    label = options.get("title") or selector
    return HarnessInventoryEntry(
        key=discovered.key,
        frontend_surface=f"{discovered.source_file}:{discovered.line_number} {label}",
        backend_path=route,
        selector_type=selector_type,
        selector=selector,
        profile=profile,
        notes="Discovered from real frontend onAskAi payload construction.",
    )


def _inventory_entry_for_static_contract(options: dict[str, Any]) -> HarnessInventoryEntry:
    key = str(options["contract_key"])
    _payload, route = build_frontend_realistic_request(options, active_section=_active_section_for_context(_normalize_context_type(options.get("contextType"))))
    selector = str(options.get("draftType") or options.get("action") or options.get("selector") or "ask_anakin")
    if route == "POST /ai/chat":
        selector_type = "route"
        profile = profile_for_chat()
    elif route == "POST /ai/repo/chat":
        selector_type = "route"
        profile = profile_for_repo_assistant()
    elif route == "soc_briefing_worker":
        selector_type = "capability"
        profile = profile_for_soc_briefing()
    elif route == "POST /ai/drafts":
        selector_type = "draft_type"
        profile = profile_for_draft_type(selector)
    elif route == "POST /ai/investigations":
        selector_type = "investigation_workflow"
        profile = profile_for_investigation()
    elif route == "POST /ai/actions/preview":
        selector_type = "action_preview"
        profile = profile_for_investigation()
    else:
        selector_type = "explain_action"
        profile = profile_for_explain_action(selector)
    return HarnessInventoryEntry(
        key=key,
        frontend_surface=str(options.get("surface") or options.get("title") or key),
        backend_path=route,
        selector_type=selector_type,
        selector=selector,
        profile=profile,
        notes=str(options.get("source") or "static acceptance contract"),
    )


def _static_surface_contracts() -> list[dict[str, Any]]:
    return [
        {
            "contract_key": "frontend.floating_chat.general",
            "surface": "FloatingSiemChat Ask Anakin",
            "route": "POST /ai/chat",
            "message": "What should I inspect first in this workspace?",
            "visible_context": _visible_context_fixture("dashboard"),
            "client_history": [],
            "source": "FloatingSiemChat",
        },
        {
            "contract_key": "frontend.command_palette.ask",
            "surface": "AnakinCommandSurface Ask command",
            "route": "POST /ai/chat",
            "message": "What should I inspect first in this workspace?",
            "visible_context": _visible_context_fixture("analyst_workspace"),
            "client_history": [],
            "source": "AnakinCommandSurface.ask",
        },
        {
            "contract_key": "frontend.repo_architecture.chat.factual",
            "surface": "RepoArchitectureAssistantPanel factual question",
            "route": "POST /ai/repo/chat",
            "message": "Where is the SOAR worker implemented?",
            "source": "RepoArchitectureAssistantPanel",
        },
        {
            "contract_key": "frontend.repo_architecture.chat.evaluative",
            "surface": "RepoArchitectureAssistantPanel evaluative question",
            "route": "POST /ai/repo/chat",
            "message": "What is my most impressive feature?",
            "source": "RepoArchitectureAssistantPanel",
        },
        {
            "contract_key": "worker.soc_briefing.manual_run_now",
            "surface": "SocBriefingsPanel Run Anakin Briefing Now",
            "route": "soc_briefing_worker",
            "contextType": "soc_briefing",
            "action": "run_now",
            "source": "SocBriefingsPanel",
        },
        {
            "contract_key": "frontend.ai_action.preview.add_incident_note",
            "surface": "AiResponsePanel Preview action",
            "route": "POST /ai/actions/preview",
            "contextType": "incident",
            "selector": "add_incident_note",
            "action_type": "add_incident_note",
            "payload": {"incident_id": 2002, "note_text": "Acceptance preview only. Do not confirm."},
            "idempotency_key": "acceptance-preview-action-2002",
            "source_draft": {"draft_type": "incident_note", "read_only": True, "persisted": False, "applied": False},
            "source": "AiResponsePanel.previewAiAction",
        },
    ]


def _extract_on_ask_ai_blocks(text: str) -> list[tuple[str, int]]:
    blocks: list[tuple[str, int]] = []
    start = 0
    marker = "onAskAi({"
    while True:
        idx = text.find(marker, start)
        if idx < 0:
            break
        brace_start = text.find("{", idx)
        depth = 0
        for pos in range(brace_start, len(text)):
            char = text[pos]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    blocks.append((text[brace_start : pos + 1], text.count("\n", 0, idx) + 1))
                    start = pos + 1
                    break
        else:
            break
    return blocks


def _parse_frontend_ai_options(block: str) -> dict[str, Any] | None:
    context_type = _js_string_prop(block, "contextType")
    action = _js_string_prop(block, "action")
    draft_type = _js_string_prop(block, "draftType")
    if not context_type or not (action or draft_type):
        return None
    context = _context_from_js_block(block, context_type)
    return {
        "contextType": context_type,
        "action": action,
        "draftType": draft_type,
        "investigation": bool(re.search(r"\binvestigation\s*:\s*true\b", block)),
        "title": _js_template_or_string_prop(block, "title") or action or draft_type,
        "question": _js_string_prop(block, "question") or "",
        "instruction": _js_string_prop(block, "instruction") or "",
        "context": context,
        "toolPolicy": _tool_policy_from_js_block(block),
        "source": "frontend_onAskAi",
    }


def _js_string_prop(block: str, prop: str) -> str | None:
    match = re.search(rf"\b{re.escape(prop)}\s*:\s*['\"]([^'\"]+)['\"]", block)
    return match.group(1) if match else None


def _js_template_or_string_prop(block: str, prop: str) -> str | None:
    simple = _js_string_prop(block, prop)
    if simple:
        return simple
    match = re.search(rf"\b{re.escape(prop)}\s*:\s*`([^`]+)`", block)
    return match.group(1) if match else None


def _context_from_js_block(block: str, context_type: str) -> dict[str, Any]:
    if "alert_id" in block:
        return {"alert_id": 1001}
    if "incident_id" in block or "selectedIncident.id" in block:
        return {"incident_id": 2002}
    if "source_ip" in block or "sourceIp" in block:
        return {"source_ip": "203.0.113.77"}
    if "activity_id" in block or "recon_activity_id" in block:
        return {"activity_id": 3003}
    if "registry_id" in block or "record.id" in block:
        return {"registry_id": 4004}
    if "rule_id" in block:
        return {"rule_id": "pfsense_firewall_repeated_deny"}
    if context_type == "dashboard":
        return {"dashboard_id": "summary"}
    return {"id": 1001}


def _tool_policy_from_js_block(block: str) -> dict[str, Any] | None:
    if "toolPolicy" not in block:
        return None
    max_calls = re.search(r"max_tool_calls\s*:\s*(\d+)", block)
    hours = re.search(r"time_window_hours\s*:\s*(\d+)", block)
    return {
        "max_tool_calls": int(max_calls.group(1)) if max_calls else 5,
        "time_window_hours": int(hours.group(1)) if hours else 24,
    }


def _frontend_contract_key(options: dict[str, Any], filename: str) -> str:
    context_type = options.get("contextType")
    action = options.get("action") or options.get("draftType") or "ask"
    suffix = ".guided" if options.get("investigation") else ".draft" if options.get("draftType") else ""
    if filename == "DashboardMetrics.js":
        return f"frontend.dashboard.metrics.{action}"
    if filename == "DashboardVisuals.js":
        return f"frontend.dashboard.visuals.{action}"
    if filename == "AlertDetailsPanel.js":
        return f"frontend.alert.{action}{suffix}"
    if filename == "SourceIpContext.js":
        return f"frontend.source_ip.{action}{suffix}"
    if filename == "IncidentsPanel.js":
        return f"frontend.incident.{action}{suffix}"
    if filename == "SocCommandCenter.js":
        return f"frontend.recon.{action}{suffix}"
    if filename == "ResponseRegistryPanel.js":
        return f"frontend.response_registry.{action}{suffix}"
    return f"frontend.{context_type}.{action}{suffix}"


def _default_command_contracts() -> list[dict[str, Any]]:
    workspace = {
        "workspace": {"activeSection": "analyst_workspace"},
        "object": {"type": "workspace", "id": "analyst_workspace"},
        "data": _visible_context_fixture("analyst_workspace"),
    }
    return [
        {
            "contract_key": "frontend.command_palette.explain",
            "contextType": "analyst_workspace",
            "action": "explain",
            "question": "Provide a read-only explain for the current SIEM context.",
            "context": workspace,
            "source": "anakinCommandRegistry.commandToAiOptions",
        },
        {
            "contract_key": "frontend.command_palette.summarize",
            "contextType": "analyst_workspace",
            "action": "summarize",
            "question": "Provide a read-only summarize for the current SIEM context.",
            "context": workspace,
            "source": "anakinCommandRegistry.commandToAiOptions",
        },
        {
            "contract_key": "frontend.command_palette.suggested_actions",
            "contextType": "analyst_workspace",
            "action": "suggestedactions",
            "question": "Provide read-only suggested actions for the current SIEM context.",
            "context": workspace,
            "source": "anakinCommandRegistry.commandToAiOptions",
        },
        {
            "contract_key": "frontend.guided_investigation",
            "contextType": "analyst_workspace",
            "action": "investigate",
            "investigation": True,
            "question": "Run a bounded read-only investigation of the current context and identify source-cited next steps.",
            "context": workspace,
            "toolPolicy": {"max_tool_calls": 5, "time_window_hours": 24},
            "source": "anakinCommandRegistry.commandToAiOptions",
        },
        {
            "contract_key": "frontend.drafts",
            "contextType": "analyst_workspace",
            "draftType": "investigation_checklist",
            "instruction": "Draft a read-only analyst checklist from the current context. Do not save or execute anything.",
            "context": workspace,
            "source": "anakinCommandRegistry.commandToAiOptions",
        },
    ]


def _frontend_options_for_entry(
    entry: AiInvocationInventoryEntry,
    context_type: str,
    frontend_options: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if entry.key == "frontend.floating_chat.general":
        return {
            "route": "POST /ai/chat",
            "message": "What should I inspect first in this workspace?",
            "visible_context": _visible_context_fixture("dashboard"),
            "client_history": [],
            "source": "FloatingSiemChat",
        }
    if entry.key == "frontend.repo_architecture.chat":
        return {
            "route": "POST /ai/repo/chat",
            "message": "What is my most impressive feature?",
            "client_history": [],
            "refresh": False,
            "source": "RepoArchitectureAssistantPanel",
        }
    if entry.key == "worker.soc_briefing.manual_and_scheduled":
        return {"contextType": "soc_briefing", "action": "run_now", "source": "SocBriefingsPanel"}
    if entry.key in frontend_options:
        return _with_large_entity_fixture(frontend_options[entry.key], context_type)
    compatible = [
        options
        for options in frontend_options.values()
        if options.get("contextType") == context_type and (options.get("action") == entry.selector or options.get("draftType") == entry.selector)
    ]
    if compatible:
        return _with_large_entity_fixture(compatible[0], context_type)
    return {
        "contextType": context_type,
        "action": entry.selector if entry.selector_type == "explain_action" else "explain",
        "question": _question_for_entry(entry, context_type),
        "context": _entity_context_for_type(context_type),
        "source": "acceptance_fallback_from_inventory",
    }


def _with_large_entity_fixture(options: dict[str, Any], context_type: str) -> dict[str, Any]:
    copied = {**options}
    context = dict(copied.get("context") or {})
    context.update(_entity_context_for_type(context_type))
    copied["context"] = context
    return copied


def _entity_context_for_type(context_type: str) -> dict[str, Any]:
    if context_type == "alert":
        return {"alert_id": 1001}
    if context_type == "incident":
        return {"incident_id": 2002}
    if context_type == "source_ip":
        return {"source_ip": "203.0.113.77"}
    if context_type == "recon_activity":
        return {"activity_id": 3003}
    if context_type == "response_registry":
        return {"registry_id": 4004}
    if context_type == "detection":
        return {"alert_id": 1001, "rule_id": "pfsense_firewall_repeated_deny"}
    return {"id": 1001}


def _visible_context_fixture(active_section: str) -> dict[str, Any]:
    return {
        "active_section": active_section,
        "visible_filters": {"severity": "high", "status": "open", "timeline_range": "7d"},
        "dashboard_summary": {"total_alerts": 4200, "critical": 17, "high": 231},
        "timeline": [{"bucket": idx, "count": 100 + idx, "severity": "high"} for idx in range(30)],
        "top_source_ips": [{"source_ip": f"203.0.113.{idx}", "count": 50 + idx} for idx in range(10)],
        "map_markers": [{"source_ip": f"198.51.100.{idx}", "count": 20 + idx, "lat": 40.0, "lon": -73.0} for idx in range(10)],
        "recent_alerts": [
            {
                "id": idx,
                "alert_type": "pfsense_firewall_repeated_deny",
                "severity": "high",
                "status": "open",
                "source_ip": f"203.0.113.{idx % 30}",
                "message": "Repeated deny events against exposed service.",
                "created_at": "2026-08-01T00:00:00Z",
            }
            for idx in range(10)
        ],
    }


def _normalize_context_type(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_")


def _stable_ai_entity_id(context: Any) -> str | int | None:
    if not isinstance(context, dict):
        return None
    for key in ("alert_id", "incident_id", "source_ip", "activity_id", "recon_activity_id", "registry_id", "id", "rule_id"):
        if context.get(key) not in (None, ""):
            return context[key]
    return None


def _active_section_for_context(context_type: str) -> str:
    return {
        "alert": "alerts",
        "dashboard": "dashboard",
        "source_ip": "source-ip-context",
        "incident": "incidents",
        "recon_activity": "soc-command-center",
        "response_registry": "response-registry",
        "repository": "admin",
        "soc_briefing": "soc-briefings",
    }.get(context_type, "analyst_workspace")


def _context_type_for_entry(entry: AiInvocationInventoryEntry) -> str:
    key = entry.key
    selector = entry.selector
    if "dashboard" in key:
        return "dashboard"
    if ".alert" in key or selector in {"explain_alert", "why_important", "recommend_investigation", "explain_detection"}:
        return "alert"
    if "source_ip" in key:
        return "source_ip"
    if "incident" in key:
        return "incident"
    if "recon" in key:
        return "recon_activity"
    if "response_registry" in key:
        return "response_registry"
    if "repo_architecture" in key:
        return "repository"
    if "soc_briefing" in key:
        return "soc_briefing"
    if "draft" in key:
        return "alert"
    if "guided_investigation" in key:
        return "alert"
    return "general"


def _stale_policy_for_entry(entry: AiInvocationInventoryEntry) -> str:
    if entry.backend_path in {"POST /ai/drafts", "POST /ai/actions/preview"}:
        return "strict_for_confirmable_preview"
    if entry.backend_path == "soc_briefing_worker":
        return "durable_lifecycle_recoverable"
    return "read_only_advisory"


def _question_for_entry(entry: AiInvocationInventoryEntry, context_type: str) -> str:
    if entry.backend_path == "POST /ai/repo/chat":
        return "What is my most impressive feature?"
    if entry.backend_path == "soc_briefing_worker":
        return "Run Anakin Briefing Now using current bounded SIEM evidence."
    return f"Analyze this {context_type} context and identify evidence, uncertainty, gaps, and next read-only steps."


def _fixture_context(context_type: str) -> AiContextPayload:
    data = _large_fixture_data(context_type)
    return AiContextPayload(
        context_type=context_type,
        data=data,
        sources=[
            AiContextSource(
                context_type,
                f"/acceptance/{context_type}/1001",
                [1001],
                "2026-08-01T00:00:00+00:00",
                truncated=True,
                omitted_count=488,
                truncation_reason="acceptance_large_fixture_bounded",
            )
        ],
        truncated=True,
        omitted_count=488,
    )


def _large_fixture_data(context_type: str) -> dict[str, Any]:
    base = {
        "summary": f"Acceptance fixture for {context_type}",
        "_evidence": {
            "included": {"primary": 1, "bounded_rows": 12},
            "omitted": {"raw_events": 488},
            "truncated": True,
        },
    }
    if context_type == "recon_activity":
        return {
            **base,
            "recon_activity": {
                "id": 3003,
                "severity": "high",
                "confidence": "medium",
                "primary_source_ip": "203.0.113.77",
                "target_ports": [22, 80, 443, 3389, 8080, 8443],
                "distinct_targets": 43,
                "window": "24h",
                "signals": [
                    {"name": "fanout", "value": 43},
                    {"name": "repeated_denies", "value": 612},
                    {"name": "admin_surface_touches", "value": 7},
                ],
            },
            "related_events": [
                {"id": idx, "source_ip": "203.0.113.77", "target_port": 443 + (idx % 20), "action": "deny"}
                for idx in range(40)
            ],
            "related_alerts": [
                {"id": idx, "severity": "high", "alert_type": "recon_cluster", "status": "open"}
                for idx in range(20)
            ],
        }
    if context_type == "source_ip":
        return {
            **base,
            "source_ip": "203.0.113.77",
            "reputation": {"status": "suspicious", "confidence": "medium", "last_seen": "2026-08-01T00:00:00Z"},
            "recent_alerts": [
                {"id": idx, "type": "pfsense_firewall_repeated_deny", "severity": "high", "target_port": 443 + idx}
                for idx in range(60)
            ],
            "campaign_memberships": [{"id": idx, "label": f"campaign-{idx}", "confidence": "medium"} for idx in range(10)],
            "response_outcomes": [{"action": "monitor", "status": "tracking_only", "count": idx + 1} for idx in range(12)],
        }
    if context_type == "incident":
        return {
            **base,
            "incident": {"id": 2002, "title": "VPN recon and repeated deny cluster", "severity": "high", "status": "open"},
            "timeline": [
                {"id": idx, "event_type": "alert_linked", "detail": "Repeated deny event added to incident", "created_at": "2026-08-01T00:00:00Z"}
                for idx in range(75)
            ],
            "linked_alerts": [{"id": idx, "severity": "high", "source_ip": f"203.0.113.{idx % 30}"} for idx in range(35)],
        }
    if context_type == "alert":
        return {
            **base,
            "alert": {
                "id": 1001,
                "alert_type": "pfsense_firewall_repeated_deny",
                "severity": "high",
                "status": "open",
                "source_ip": "203.0.113.77",
                "message": "Repeated deny events during background refresh.",
                "refresh_generation": 2,
            },
            "why_fired": {"rule": "Repeated deny threshold exceeded", "threshold": 25, "observed": 612},
            "related_events": [
                {"id": idx, "source_ip": "203.0.113.77", "target_port": 443 + (idx % 40), "action": "deny"}
                for idx in range(80)
            ],
            "background_refresh": {"previous_selected_alert_id": 1001, "current_selected_alert_id": 1001, "dashboard_refreshing": True},
        }
    if context_type == "response_registry":
        return {
            **base,
            "registry_record": {
                "id": 4004,
                "indicator_value": "203.0.113.77",
                "action": "monitor",
                "status": "active",
                "latest_outcome": "tracking_only",
            },
            "related_alerts": [{"id": idx, "severity": "high", "status": "open"} for idx in range(30)],
            "outcome_history": [{"id": idx, "status": "tracking_only", "note": "No production action executed"} for idx in range(20)],
        }
    if context_type in {"general", "analyst_workspace"}:
        return {
            **base,
            "workspace": "analyst_workspace",
            "visible_context": _visible_context_fixture("analyst_workspace"),
            "open_investigations": [{"id": idx, "status": "open", "severity": "high"} for idx in range(12)],
        }
    return {
        **base,
        "primary": {
            "id": 1001,
            "severity": "high",
            "status": "open",
            "source_ip": "203.0.113.77",
            "description": "Repeated deny events against VPN and admin surfaces.",
        },
        "bounded_rows": [
            {"id": idx, "event": "deny", "port": 443 + idx, "count": 10 + idx}
            for idx in range(12)
        ],
    }


def _repo_chunks() -> list[RepoChunk]:
    return [
        RepoChunk(
            path="core/ai/context_builder.py",
            line_start=1,
            line_end=80,
            text="SUPPORTED_CONTEXT_TYPES and bounded context builders package SIEM evidence before AI prompts.",
            trust_tier=1,
            source_kind="source",
            label="current",
            mtime=0,
            size=200,
            content_hash="acceptance-context",
        ),
        RepoChunk(
            path="core/ai/profile_registry.py",
            line_start=1,
            line_end=120,
            text="AI_INVOCATION_INVENTORY maps frontend AI surfaces to backend routes and model profiles.",
            trust_tier=1,
            source_kind="source",
            label="current",
            mtime=0,
            size=200,
            content_hash="acceptance-profile",
        ),
    ]


def _sample_response_for_case(entry: AiInvocationInventoryEntry, case: AcceptanceCase) -> str:
    if entry.backend_path == "POST /ai/drafts":
        return json.dumps(_sample_draft_payload(str(case.request_payload.get("draft_type") or "investigation_checklist"), case.context_type))
    if entry.backend_path == "POST /ai/actions/preview":
        return (
            "Assessment: action preview is ready for analyst review only.\n"
            "Evidence: payload digest, target fingerprint, and confirmation token are required before confirmation.\n"
            "Contradictions and uncertainty: stale target state blocks confirmation.\n"
            "Evidence gaps: analyst must review the generated draft and current target state.\n"
            "Read-only next steps: inspect preview details and reject or explicitly confirm through the guarded workflow."
        )
    return (
        "Assessment: repeated activity is notable because it targets sensitive surfaces.\n"
        "Evidence: bounded fixture rows support the assessment while omitted raw rows are reported.\n"
        "Contradictions and uncertainty: no successful login or containment outcome is shown.\n"
        "Evidence gaps: confirm affected asset criticality and related incidents.\n"
        "Read-only next steps: inspect related alerts, event timeline, and source-IP history."
    )


def _sample_draft_payload(draft_type: str, context_type: str) -> dict[str, Any]:
    if draft_type == "detection_rule_change":
        return {
            "title": "Tune repeated-deny detection threshold",
            "rationale": "Bounded evidence supports analyst review of the detection condition.",
            "target_rule": "pfsense_firewall_repeated_deny",
            "suggested_condition": "Require repeated deny events from one source across multiple target ports in the observed window.",
            "severity": "high",
            "false_positive_notes": "Check approved scanners, NAT gateways, monitoring tools, and maintenance windows before treating the activity as malicious.",
            "test_ideas": ["Replay benign scanner events.", "Replay recent high-confidence deny bursts."],
            "rollback_notes": "Restore the previous threshold if false positives increase after review.",
            "source_references": [context_type],
        }
    if draft_type == "playbook_draft":
        return {
            "name": "Review suspicious scanner",
            "trigger_context": "High-severity repeated deny evidence",
            "steps": ["Collect alert detail", "Review source-IP history"],
            "approval_gates": ["Analyst approval before enforcement"],
            "simulation_real_caveats": "This is review-only and does not execute a playbook.",
            "required_integrations": ["firewall"],
            "risks": ["Benign scanner may be misclassified"],
            "source_references": [context_type],
        }
    if draft_type == "incident_note":
        return {
            "summary": "Repeated suspicious activity requires analyst review.",
            "evidence": ["Bounded SIEM evidence supports the assessment."],
            "uncertainty": "Source ownership and benign scanner status remain unknown.",
            "recommended_next_steps": ["Review related events"],
            "attribution": [context_type],
        }
    if draft_type == "escalation_summary":
        return {
            "audience": "SOC lead",
            "urgency": "High",
            "business_or_security_impact": "Potential recon against exposed services.",
            "evidence": ["Multiple related alerts"],
            "asks": ["Confirm response policy"],
            "next_update_criteria": "Update after related-event review.",
            "source_references": [context_type],
        }
    if draft_type == "response_recommendation":
        return {
            "recommended_action_class": "Monitor and investigate",
            "prerequisites": ["Confirm source history"],
            "expected_outcome": "Improved confidence before enforcement.",
            "approval_need": "Required before any production action.",
            "risk": "Premature blocking may affect benign traffic.",
            "alternatives": ["Escalate to network owner"],
            "source_references": [context_type],
        }
    return {
        "title": "Acceptance investigation checklist",
        "checks": ["Review cited evidence", "Compare benign indicators", "Document uncertainty"],
        "data_sources": ["alerts", "events"],
        "expected_findings": ["Repeated denies may indicate recon"],
        "stop_conditions": ["No matching current evidence"],
        "source_references": [context_type],
    }


def _usefulness_checks(response: str) -> dict[str, bool]:
    normalized = str(response or "").strip().lower()
    return {
        "non_empty": bool(normalized),
        "has_assessment_or_title": "assessment" in normalized or "title" in normalized,
        "has_evidence": "evidence" in normalized or "source_references" in normalized,
        "has_uncertainty_or_gaps": "uncertainty" in normalized or "gap" in normalized,
        "has_next_steps_or_checks": "next step" in normalized or "checks" in normalized,
        "not_generic_monitoring_only": normalized != "continue monitoring.",
    }


def _empty_usefulness(value: bool) -> dict[str, bool]:
    return {
        "non_empty": value,
        "has_assessment_or_title": value,
        "has_evidence": value,
        "has_uncertainty_or_gaps": value,
        "has_next_steps_or_checks": value,
        "not_generic_monitoring_only": value,
    }


def _stale_result(case: AcceptanceCase) -> str:
    if case.stale_policy == "read_only_advisory":
        return "read_only_response_remains_visible_with_advisory"
    if case.stale_policy == "strict_for_confirmable_preview":
        return "confirmable_preview_blocks_confirmation_when_stale"
    if case.stale_policy == "durable_lifecycle_recoverable":
        lifecycle = ["queued", "running", "completed"]
        terminal = lifecycle[-1]
        return f"manual_lifecycle_visible_terminal:{terminal}" if terminal in TERMINAL_MANUAL_BRIEFING_STATES else "manual_lifecycle_missing_terminal"
    return "unknown"


def _stale_ok(stale_result: str) -> bool:
    return stale_result in {
        "read_only_response_remains_visible_with_advisory",
        "confirmable_preview_blocks_confirmation_when_stale",
    } or stale_result.startswith("manual_lifecycle_visible_terminal:")


def _acceptance_config() -> AiGatewayConfig:
    return AiGatewayConfig(
        mode=AI_MODE_LOCAL_ONLY,
        configured_mode=AI_MODE_LOCAL_ONLY,
        local_provider="ollama",
        local_base_url="http://127.0.0.1:11434",
        local_model="llama3.1:8b",
        local_timeout_seconds=30,
        profiles=default_ai_profiles(local_model="llama3.1:8b", local_timeout_seconds=30),
    )


__all__ = [
    "AcceptanceReport",
    "AcceptanceResult",
    "LIVE_SMOKE_ENV",
    "LIVE_SWEEP_ENV",
    "build_acceptance_cases",
    "build_frontend_realistic_request",
    "discover_frontend_ai_options",
    "render_live_sweep_markdown",
    "render_markdown_report",
    "run_acceptance_harness",
    "run_live_backend_sweep",
    "run_offline_contract_tier",
    "run_optional_live_smoke_tier",
]
