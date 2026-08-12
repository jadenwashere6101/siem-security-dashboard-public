from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal
import json

import pytest

from core.ai.agentic_analyst_planner import (
    PLAN_SEMANTIC_CONTRACTS,
    PLANNER_GATEWAY_FRAMING_CHARS,
    PLANNER_PACKET_MAX_CHARS,
    build_planner_packet,
    parse_and_validate_plan,
    planner_output_contract,
    planner_output_schema,
    planner_semantic_contract,
    plan_turn,
)
from core.ai.config import (
    AI_MODE_AUTOMATIC_FALLBACK,
    AI_MODE_LOCAL_ONLY,
    AiGatewayConfig,
    default_ai_profiles,
)
from core.ai.acceptance_harness import build_planner_reliability_fixtures
from core.ai.gateway import AiGateway
from core.ai.models import (
    AI_STATUS_BUDGET_EXHAUSTED,
    AI_STATUS_SUCCESS,
    PROVIDER_COMPLETION_COMPLETE,
    PROVIDER_COMPLETION_OUTPUT_EXHAUSTED,
    AiGatewayResponse,
    AiRequestMetadata,
)
from core.ai.providers import AnthropicProvider
from core.ai.paid_usage_store import (
    PaidBudgetExhausted,
    PaidUsageReservation,
    PaidUsageSettlement,
)
from core.ai.profile_registry import AI_PROFILE_AGENTIC_PLANNING


class SequenceGateway:
    def __init__(self, contents):
        self.contents = list(contents)
        self.requests = []

    def generate(self, request):
        self.requests.append(request)
        content = self.contents.pop(0)
        return AiGatewayResponse(
            status=AI_STATUS_SUCCESS,
            content=content,
            error=None,
            metadata=AiRequestMetadata(
                provider="controlled-local",
                model="planner-test",
                mode=AI_MODE_LOCAL_ONLY,
                status=AI_STATUS_SUCCESS,
                local_request=True,
                paid_request=False,
            ),
        )


class FailureGateway:
    def __init__(self, status="provider_timeout"):
        self.status = status
        self.requests = []

    def generate(self, request):
        self.requests.append(request)
        return AiGatewayResponse(
            status=self.status,
            content=None,
            error="Planner provider unavailable.",
            metadata=AiRequestMetadata(
                provider="controlled-local",
                model="planner-test",
                mode=AI_MODE_LOCAL_ONLY,
                status=self.status,
                error_code=self.status,
                local_request=True,
                paid_request=False,
            ),
        )


class CompletionGateway:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def generate(self, request):
        self.requests.append(request)
        value = self.responses.pop(0)
        return AiGatewayResponse(
            status=value.get("status", AI_STATUS_SUCCESS),
            content=value.get("content"),
            error=None,
            metadata=AiRequestMetadata(
                provider="anthropic",
                model="planner-test",
                mode=AI_MODE_LOCAL_ONLY,
                status=value.get("status", AI_STATUS_SUCCESS),
                provider_completion_state=value.get("completion_state"),
                provider_stop_reason=value.get("stop_reason"),
                provider_reported_prompt_tokens=value.get("input_tokens"),
                provider_reported_completion_tokens=value.get("output_tokens"),
                accounting_attempt_id=value.get("accounting_attempt_id"),
                paid_request=True,
            ),
        )


class AllowingAccountingStore:
    def __init__(self):
        self.attempts = 0
        self.kinds = []
        self.correlations = []

    def reserve(self, *, request, **_kwargs):
        self.attempts += 1
        kind = "repair" if request.metadata.get("repair_attempt") == 1 else "initial"
        self.kinds.append(kind)
        self.correlations.append(request.metadata.get("paid_correlation_id"))
        return PaidUsageReservation(
            attempt_id=f"test-attempt-{self.attempts}",
            usage_day=date(2026, 8, 4),
            reserved_cost_usd=Decimal("0.10"),
            remaining_usd=Decimal("4.90"),
            estimated_input_tokens=10,
            estimated_output_tokens=20,
            correlation_id=request.metadata.get("paid_correlation_id"),
            attempt_kind=kind,
        )

    def settle(self, reservation, _response, **_kwargs):
        return PaidUsageSettlement(
            attempt_id=reservation.attempt_id,
            usage_day=reservation.usage_day,
            charged_cost_usd=Decimal("0.10"),
            remaining_usd=Decimal("4.90"),
            input_tokens=10,
            output_tokens=20,
            total_tokens=30,
            token_usage_source="estimated",
            cost_source="estimated",
        )


class RepairBudgetExhaustedAccountingStore(AllowingAccountingStore):
    def reserve(self, *, request, **kwargs):
        if self.attempts == 1:
            self.attempts += 1
            self.kinds.append("repair")
            self.correlations.append(request.metadata.get("paid_correlation_id"))
            raise PaidBudgetExhausted(
                attempt_id="blocked-repair",
                usage_day=date(2026, 8, 4),
                requested_usd=Decimal("0.10"),
                remaining_usd=Decimal("0.01"),
            )
        return super().reserve(request=request, **kwargs)


def _config():
    base = AiGatewayConfig(
        mode=AI_MODE_LOCAL_ONLY,
        configured_mode=AI_MODE_LOCAL_ONLY,
        local_provider="controlled-local",
        local_base_url="http://127.0.0.1:11434",
        local_model="planner-test",
    )
    profiles = base.profiles or None
    return replace(base, profiles=profiles)


def _anthropic_config():
    model = "claude-test-model"
    return AiGatewayConfig(
        mode=AI_MODE_AUTOMATIC_FALLBACK,
        configured_mode=AI_MODE_AUTOMATIC_FALLBACK,
        local_provider="ollama",
        local_base_url="http://127.0.0.1:11434",
        local_model="llama3.2:3b",
        anthropic_enabled=True,
        anthropic_routing_enabled=True,
        anthropic_api_key="test-key-never-send",
        anthropic_model=model,
        anthropic_daily_budget_usd=5.0,
        anthropic_input_cost_per_million_tokens=3.0,
        anthropic_output_cost_per_million_tokens=15.0,
        profiles=default_ai_profiles(local_model="llama3.2:3b", anthropic_model=model),
    )


def _packet(question="What's the newest HIGH alert?", *, evidence=None, corrections=None):
    return build_planner_packet(
        question=question,
        request_context={"context_type": "alert"},
        conversation_packet={
            "thread": {"thread_id": "ath_planner"},
            "entities": [
                {"type": "alert", "id": "9078", "display_alias": "Alert 9078", "source_type": "request_context"},
                {"type": "alert", "id": "9078", "display_alias": "Alert 9078", "source_type": "thread_record"},
                {"type": "alert", "id": "9011", "source_type": "thread_state"},
            ],
            "analyst_corrections": corrections or [],
            "unresolved_questions": [],
            "recent_conclusions": [{"summary": "Earlier scan explanation", "confidence": "medium"}],
            "recent_tool_results": evidence or [],
            "prior_recommendations": [],
            "recent_turns": [{"role": "assistant", "content": "Earlier explanation", "sequence": 2}],
            "analyst_statements": [],
        },
        preferred_capability="quick_explain",
        latency_class={"mode": "sync", "p95_seconds": 8},
    )


def _plan(
    *,
    intent="fresh_evidence_lookup",
    sufficiency="insufficient",
    strategy="quick_evidence_lookup",
    tools=None,
    requirements=None,
    clarification=None,
    relationship="new_question",
    entities=None,
    artifact_type=None,
    referenced_turn_sequence=None,
):
    capability = {
        "direct_answer": "quick_explain",
        "quick_evidence_lookup": "quick_explain",
        "bounded_investigation": "deep_investigate",
        "decision_support": "decision_support",
        "artifact_draft": "generate_artifact",
        "compare_entities": "deep_investigate",
        "clarification_required": None,
        "unsupported_or_boundary": None,
    }[strategy]
    if entities is None:
        entities = (
            [{"type": "alert", "id": "9078"}, {"type": "alert", "id": "9011"}]
            if strategy == "compare_entities"
            else []
            if strategy in {"clarification_required", "unsupported_or_boundary"}
            else [{"type": "alert", "id": "9078", "display_alias": "Alert 9078"}]
        )
    if strategy == "artifact_draft" and artifact_type is None:
        artifact_type = "investigation_checklist"
    if requirements is None and strategy == "quick_evidence_lookup":
        requirements = {"severity": "high", "limit": 1}
        if len(entities) == 1 and entities[0].get("type") in {"alert", "detection"}:
            requirements["alert_id"] = int(entities[0]["id"])
    return {
        "current_turn_intent": intent,
        "relationship_to_prior_turn": relationship,
        "resolved_entities": entities,
        "evidence_sufficiency": sufficiency,
        "required_evidence": ["current high-severity alerts"] if sufficiency == "insufficient" else [],
        "proposed_strategy": strategy,
        "proposed_capability": capability,
        "proposed_tool_categories": tools if tools is not None else (["alerts"] if strategy == "quick_evidence_lookup" else []),
        "evidence_requirements": requirements if requirements is not None else {},
        "clarification_question": clarification,
        "artifact_type": artifact_type,
        "referenced_turn_sequence": referenced_turn_sequence,
        "reasoning_summary": "The current question changes task and requires current alert evidence.",
        "confidence": "high",
    }


def _prompt_contract(prompt: str) -> dict:
    rendered = prompt.split("PLANNER_CONTRACT=", 1)[1].splitlines()[0]
    return json.loads(rendered)


def test_packet_is_fit_by_construction_with_production_sized_state():
    long = "blocked firewall observation " * 80
    packet = build_planner_packet(
        question="Compare the current alert with the earlier scan and explain what changed.",
        request_context={"context_type": "alert"},
        conversation_packet={
            "thread": {"thread_id": "ath_planner"},
            "entities": [
                {"type": "alert", "id": "9078", "source_type": "request_context"},
                {"type": "alert", "id": "9078", "source_type": "thread_record"},
                {"type": "alert", "id": "9011", "source_type": "thread_state"},
            ],
            **{
                category: [{"content": long, "summary": long, "confidence": "medium"} for _ in range(12)]
                for category in (
                    "analyst_corrections", "unresolved_questions", "recent_conclusions", "recent_tool_results",
                    "prior_recommendations", "recent_turns", "analyst_statements",
                )
            },
        },
        preferred_capability="deep_investigate",
        latency_class={"mode": "polling", "completion_seconds": [45, 90]},
    )
    assert packet.serialized_chars <= PLANNER_PACKET_MAX_CHARS
    assert packet.payload["current_user_message"].startswith("Compare")
    assert {item["id"] for item in packet.payload["facts"]["entities"]} >= {"9078", "9011"}
    assert packet.omitted


def test_complete_prompt_builder_preserves_full_question_and_fits_twenty_turns():
    question = "Compare the two validated alert records and explain whether the newer evidence changes our current conclusion. " * 8
    turns = [
        {
            "sequence": sequence,
            "role": "assistant" if sequence % 2 == 0 else "user",
            "content": f"Recorded turn {sequence} " + ("bounded context " * 30),
            "entity": {"type": "alert", "id": str(9000 + sequence % 2)},
        }
        for sequence in range(1, 21)
    ]
    packet = build_planner_packet(
        question=question,
        request_context={"context_type": "alert"},
        conversation_packet={
            "entities": [
                {"type": "alert", "id": "9000", "source_type": "turn_snapshot", "sequence": 18},
                {"type": "alert", "id": "9001", "source_type": "turn_snapshot", "sequence": 20},
            ],
            "recent_tool_results": [
                {"source_type": "alerts", "snapshot": {"alert_id": 9001}, "observed_at": "2026-08-03T12:00:00Z"}
            ],
            "recent_conclusions": [{"content": "The newer alert remains under review."}],
            "unresolved_questions": [{"question": "Was follow-up activity observed?"}],
            "conversation_summary": "Two related alerts are being compared.",
            "recent_turns": turns,
        },
        preferred_capability=None,
        latency_class={"mode": "sync"},
        max_prompt_chars=8000,
    )

    assert packet.payload["current_user_message"] == question.strip()
    assert packet.prompt_chars + packet.gateway_framing_chars <= 8000
    assert packet.gateway_framing_chars == PLANNER_GATEWAY_FRAMING_CHARS == 0
    assert {item["id"] for item in packet.payload["facts"]["entities"]} == {"9000", "9001"}
    assert packet.omitted


def test_many_entities_remain_typed_and_unranked_within_complete_prompt_budget():
    entities = [
        {"type": "alert", "id": str(9100 + index), "source_type": "entity_index", "sequence": index}
        for index in range(20)
    ]
    packet = build_planner_packet(
        question="Which two records should be compared?",
        request_context={"context_type": "general"},
        conversation_packet={"entities": entities},
        preferred_capability=None,
        latency_class={"mode": "sync"},
        max_prompt_chars=8000,
    )

    assert [(item["type"], item["id"]) for item in packet.payload["facts"]["entities"]] == [
        ("alert", str(9100 + index)) for index in range(20)
    ]
    assert all("rank" not in item and "priority" not in item for item in packet.payload["facts"]["entities"])
    assert packet.prompt_chars <= 8000


def test_duplicate_tool_facts_are_embedded_once():
    evidence = {
        "source_type": "alerts",
        "source_ref": "bounded-alert-search",
        "snapshot": {"alert_id": 9078, "severity": "high"},
        "observed_at": "2026-08-03T12:00:00Z",
    }
    packet = build_planner_packet(
        question="Show me the evidence.",
        request_context={"context_type": "alert"},
        conversation_packet={
            "entities": [{"type": "alert", "id": "9078", "source_type": "verified_evidence"}],
            "recent_tool_results": [evidence, dict(evidence), dict(evidence)],
        },
        preferred_capability=None,
        latency_class={"mode": "sync"},
        max_prompt_chars=8000,
    )

    assert len(packet.payload["facts"]["recent_tool_results"]) == 1
    assert packet.prompt_chars <= 8000


def test_server_authored_planner_context_is_a_model_agnostic_fact_packet():
    packet = _packet().payload
    banned = {
        "active_focus",
        "primary_entity",
        "focus_history",
        "preferred_reference",
        "correction_target",
        "entity_context",
        "current_request_entity",
        "preferred_capability_hint",
        "intent",
        "relationship",
        "priority",
    }

    def keys(value):
        if isinstance(value, dict):
            return set(value).union(*(keys(child) for child in value.values()))
        if isinstance(value, list):
            return set().union(*(keys(child) for child in value)) if value else set()
        return set()

    assert not (keys(packet["facts"]) & banned)
    assert packet["facts"]["entities"]
    assert all(item.get("source_type") for item in packet["facts"]["entities"])


def test_planner_owns_reference_fields_while_server_owns_safety():
    packet = _packet()
    valid, errors = parse_and_validate_plan(json.dumps(_plan()), packet.payload)
    assert errors == []
    assert valid.proposed_strategy == "quick_evidence_lookup"
    assert valid.relationship_to_prior_turn == "new_question"
    assert valid.resolved_entities == ({"type": "alert", "id": "9078", "display_alias": "Alert 9078"},)
    assert valid.proposed_capability == "quick_explain"
    assert valid.read_only is True
    assert valid.mutation_allowed is False

    override = _plan()
    override["safety"] = {"read_only": False}
    invalid, errors = parse_and_validate_plan(json.dumps(override), packet.payload)
    assert invalid is None
    assert any("unknown plan fields: safety" in error for error in errors)


def test_open_lookup_with_zero_entities_is_valid():
    value = _plan(entities=[])

    plan, errors = parse_and_validate_plan(json.dumps(value), _packet().payload)

    assert errors == []
    assert plan.resolved_entities == ()
    assert plan.evidence_requirements == {"severity": "high", "limit": 1}


def test_specific_alert_evidence_plan_binds_alert_9663():
    value = _plan(
        intent="evidence_explanation",
        entities=[{"type": "alert", "id": "9663"}],
        requirements={"alert_id": "9663", "limit": 1},
    )

    plan, errors = parse_and_validate_plan(json.dumps(value), _packet("Explain the selected record.").payload)

    assert errors == []
    assert plan.resolved_entities == ({"type": "alert", "id": "9663"},)
    assert plan.evidence_requirements == {"alert_id": 9663, "limit": 1}
    assert planner_output_schema()["entity_binding_keys"]["alert"] == "alert_id"


def test_resolved_alert_rejects_unfiltered_newest_lookup():
    value = _plan(
        intent="evidence_explanation",
        entities=[{"type": "alert", "id": "9663"}],
        requirements={"limit": 1, "sort": "newest"},
    )

    plan, errors = parse_and_validate_plan(json.dumps(value), _packet().payload)

    assert plan is None
    assert any("must bind resolved alert 9663 with alert_id=9663" in error for error in errors)


def test_resolved_alert_rejects_wrong_alert_id_lookup():
    value = _plan(
        intent="evidence_explanation",
        entities=[{"type": "alert", "id": "9663"}],
        requirements={"alert_id": 9682, "limit": 1},
    )

    plan, errors = parse_and_validate_plan(json.dumps(value), _packet().payload)

    assert plan is None
    assert "evidence_requirements alert_id must equal resolved alert id 9663" in errors


def test_entity_binding_validation_does_not_interpret_question_language():
    value = _plan(
        intent="evidence_explanation",
        entities=[{"type": "alert", "id": "9663"}],
        requirements={"limit": 1, "sort": "newest"},
    )
    error_sets = []
    for question in ("explain alert ID 9663", "unseen wording with no identifier syntax"):
        plan, errors = parse_and_validate_plan(json.dumps(value), _packet(question).payload)
        assert plan is None
        error_sets.append(errors)

    assert error_sets[0] == error_sets[1]


@pytest.mark.parametrize(
    "category,entity,requirements",
    [
        ("incidents", {"type": "incident", "id": "41"}, {"incident_id": 41}),
        ("source_ip_activity", {"type": "source_ip", "id": "203.0.113.81"}, {"source_ip": "203.0.113.81"}),
        ("recon_activity", {"type": "recon_activity", "id": "17"}, {"activity_id": 17}),
        ("response_registry", {"type": "response_registry", "id": "29"}, {"registry_id": 29}),
    ],
)
def test_other_supported_entity_bindings_use_existing_identity_keys(category, entity, requirements):
    value = _plan(entities=[entity], tools=[category], requirements=requirements)

    plan, errors = parse_and_validate_plan(json.dumps(value), _packet().payload)

    assert errors == []
    assert plan.evidence_requirements == requirements


@pytest.mark.parametrize(
    "intent,strategy,entities,expected",
    [
        ("state_summary", "direct_answer", [], None),
        ("state_summary", "direct_answer", [{"type": "alert", "id": "9078"}], None),
        ("evidence_explanation", "direct_answer", [], "exactly 1"),
        ("decision_support", "decision_support", [], "exactly 1"),
        ("artifact_draft", "artifact_draft", [], "exactly 1"),
        ("bounded_investigation", "bounded_investigation", [], "exactly 1"),
        ("comparison", "compare_entities", [], "exactly 2"),
        ("comparison", "compare_entities", [{"type": "alert", "id": "9078"}], "exactly 2"),
    ],
)
def test_action_strategy_contract_controls_entity_cardinality(intent, strategy, entities, expected):
    value = _plan(
        intent=intent,
        strategy=strategy,
        sufficiency="sufficient" if strategy in {"direct_answer", "decision_support", "artifact_draft"} else "insufficient",
        tools=[],
        requirements={},
        entities=entities,
    )

    plan, errors = parse_and_validate_plan(json.dumps(value), _packet().payload)

    if expected is None:
        assert errors == []
        assert plan is not None
    else:
        assert plan is None
        assert any(expected in error for error in errors)


def test_comparison_rejects_three_entities_without_substitution():
    value = _plan(
        intent="comparison",
        strategy="compare_entities",
        sufficiency="insufficient",
        tools=[],
        requirements={},
        entities=[
            {"type": "alert", "id": "9078"},
            {"type": "alert", "id": "9011"},
            {"type": "alert", "id": "9001"},
        ],
    )

    plan, errors = parse_and_validate_plan(json.dumps(value), _packet().payload)

    assert plan is None
    assert any("at most two" in error for error in errors)


def test_clarification_contract_allows_bounded_candidates_and_requires_ambiguous_state():
    value = _plan(
        intent="clarification",
        strategy="clarification_required",
        sufficiency="ambiguous",
        tools=[],
        requirements={},
        entities=[{"type": "alert", "id": "9078"}, {"type": "alert", "id": "9011"}],
        clarification="Did you mean Alert 9078 or Alert 9011?",
    )
    plan, errors = parse_and_validate_plan(json.dumps(value), _packet().payload)
    assert errors == []
    assert len(plan.resolved_entities) == 2

    value["evidence_sufficiency"] = "sufficient"
    invalid, errors = parse_and_validate_plan(json.dumps(value), _packet().payload)
    assert invalid is None
    assert any("requires ambiguous" in error for error in errors)


def test_prompt_and_repair_use_the_authoritative_semantic_contract():
    malformed = _plan(entities=[])
    malformed["resolved_entities"] = [{"type": "alert", "id": "9078"}, {"type": "alert", "id": "9011"}]
    gateway = SequenceGateway([json.dumps(malformed), json.dumps(_plan(entities=[]))])

    outcome = plan_turn(_packet(), gateway=gateway, config=_config())

    assert outcome.status == "planned"
    for request in gateway.requests:
        rows = _prompt_contract(request.prompt)["action_strategy"]["rows"]
        assert {(row[0], row[1]) for row in rows} == set(PLAN_SEMANTIC_CONTRACTS)
    assert "fresh_evidence_lookup/quick_evidence_lookup requires between 0 and 1 resolved entities" in gateway.requests[1].prompt


def test_compact_semantic_contract_is_equivalent_to_validator_authority():
    compact = planner_semantic_contract()
    fields = compact["fields"]

    assert set(compact["rules"]) == {
        f"{action}/{strategy}" for action, strategy in PLAN_SEMANTIC_CONTRACTS
    }
    for (action, strategy), expected in PLAN_SEMANTIC_CONTRACTS.items():
        reconstructed = dict(zip(fields, compact["rules"][f"{action}/{strategy}"]))
        assert reconstructed == {
            "min_entities": expected.minimum_entities,
            "max_entities": expected.maximum_entities,
            "filters": expected.evidence_filters_allowed,
            "clarification": expected.clarification_required,
            "tools": expected.tool_execution_allowed,
            "capability": expected.capability,
        }
    assert "current_turn_intent" in planner_output_schema()["required"]
    assert "resolved_entities" in planner_output_schema()["required"]


def test_authoritative_output_contract_covers_filters_bounds_bindings_and_conditions():
    contract = planner_output_contract()
    schema = contract["schema"]

    assert schema["bounds"]["time_window_minutes"] == [1, 7 * 24 * 60]
    assert schema["bounds"]["limit"] == [1, 10]
    assert schema["bounds"]["resolved_entities"] == 2
    assert schema["bounds"]["proposed_tool_categories"] == 1
    assert schema["evidence_filters"]["mutual_exclusion"] == [["hostname", "username"]]
    assert schema["evidence_filters"]["allowed_by_tool"]["alerts"] == sorted(
        {"alert_id", "severity", "alert_type", "source_ip", "destination_ip", "hostname", "username", "time_window_minutes", "sort", "limit"}
    )
    assert schema["entity_bindings"]["alert"]["alerts"] == "alert_id"
    assert schema["conditionals"]["artifact_draft"].startswith("artifact_type required")
    assert contract["action_strategy"]["rows"]


def test_planner_prompt_explicitly_serializes_all_validator_owned_enums():
    gateway = SequenceGateway([json.dumps(_plan())])

    outcome = plan_turn(_packet(), gateway=gateway, config=_config())

    assert outcome.status == "planned"
    schema = planner_output_schema()
    prompt = gateway.requests[0].prompt
    assert schema["enums"]["current_turn_intent"] == sorted({action for action, _strategy in PLAN_SEMANTIC_CONTRACTS})
    assert schema["enums"]["proposed_strategy"] == sorted({strategy for _action, strategy in PLAN_SEMANTIC_CONTRACTS})
    assert schema["enums"]["proposed_capability"] == [
        "decision_support", "deep_investigate", "generate_artifact", "quick_explain"
    ]
    prompt_contract = _prompt_contract(prompt)
    prompt_rows = prompt_contract["action_strategy"]["rows"]
    assert {row[0] for row in prompt_rows} == set(schema["enums"]["current_turn_intent"])
    assert {row[1] for row in prompt_rows} == set(schema["enums"]["proposed_strategy"])
    assert {row[7] for row in prompt_rows if row[7] is not None} == set(schema["enums"]["proposed_capability"])
    assert prompt_contract["filter_formats"] == schema["evidence_filters"]["formats"]
    alert_binding = next(
        value
        for key, value in prompt_contract["entity_binding(entity@tools)"].items()
        if key.startswith("alert@") and "events" in key
    )
    assert alert_binding == ["alert_id", ["alert_id", "limit"]]
    assert "Obey PLANNER_CONTRACT" in prompt
    assert "never invent tokens" in prompt
    assert all(row[1] in schema["enums"]["proposed_strategy"] for row in prompt_rows)


def test_every_canonical_action_strategy_pair_accepts_its_exact_tokens():
    candidates = [{"type": "alert", "id": "9078"}, {"type": "alert", "id": "9011"}]
    for (intent, strategy), contract in PLAN_SEMANTIC_CONTRACTS.items():
        is_lookup = contract.tool_execution_allowed
        is_clarification = contract.clarification_required
        value = _plan(
            intent=intent,
            strategy=strategy,
            sufficiency="ambiguous" if is_clarification else "insufficient" if is_lookup else "sufficient",
            entities=candidates[: contract.minimum_entities],
            tools=["alerts"] if is_lookup else [],
            requirements=(
                {"alert_id": 9078, "severity": "high"}
                if is_lookup and contract.minimum_entities
                else {"severity": "high"}
                if is_lookup
                else {}
            ),
            clarification="Which record did you mean?" if is_clarification else None,
            referenced_turn_sequence=2 if intent == "analyst_correction" else None,
        )

        plan, errors = parse_and_validate_plan(json.dumps(value), _packet().payload)

        assert errors == [], (intent, strategy, errors)
        assert plan.current_turn_intent == intent
        assert plan.proposed_strategy == strategy


def test_strategy_and_capability_vocabularies_are_not_interchangeable():
    strategy_as_capability = _plan()
    strategy_as_capability["proposed_strategy"] = "quick_explain"
    capability_as_strategy = _plan()
    capability_as_strategy["proposed_capability"] = "quick_evidence_lookup"

    first, first_errors = parse_and_validate_plan(json.dumps(strategy_as_capability), _packet().payload)
    second, second_errors = parse_and_validate_plan(json.dumps(capability_as_strategy), _packet().payload)

    assert first is None
    assert "proposed_strategy is invalid" in first_errors
    assert second is None
    assert "proposed_capability is incompatible with proposed_strategy" in second_errors


@pytest.mark.parametrize("invalid_action", ["lookup", "request_for_summary"])
def test_noncanonical_action_synonyms_fail_and_repair_receives_exact_enum_vocabulary(invalid_action):
    malformed = _plan()
    malformed["current_turn_intent"] = invalid_action
    gateway = SequenceGateway([json.dumps(malformed), json.dumps(_plan())])

    outcome = plan_turn(_packet(), gateway=gateway, config=_config())

    assert outcome.status == "planned"
    assert outcome.repaired is True
    repair_prompt = gateway.requests[1].prompt
    for canonical in planner_output_schema()["enums"]["current_turn_intent"]:
        assert f'"{canonical}"' in repair_prompt
    assert "current_turn_intent is invalid" in repair_prompt


@pytest.mark.parametrize(
    "rendered,accepted",
    [
        (lambda value: value, True),
        (lambda value: f"Here is the plan: {value}", False),
        (lambda value: f"{value}\nThis is the plan.", False),
        (lambda value: f"Explanation first.\n```json\n{value}\n```", False),
        (lambda value: f"```json\n{value}\n```", False),
    ],
)
def test_initial_parser_accepts_only_one_json_object_without_surrounding_prose(rendered, accepted):
    content = rendered(json.dumps(_plan()))

    plan, errors = parse_and_validate_plan(content, _packet().payload)

    assert (plan is not None) is accepted
    assert (errors == []) is accepted


def test_repair_with_surrounding_prose_remains_fail_closed():
    malformed = _plan()
    malformed["required_evidence"] = {"alerts": "current high-severity alerts"}
    prose_wrapped_repair = f"Here is the corrected plan:\n{json.dumps(_plan())}\nNo other changes were made."
    gateway = SequenceGateway([json.dumps(malformed), prose_wrapped_repair])

    outcome = plan_turn(_packet(), gateway=gateway, config=_config())

    assert outcome.status == "invalid"
    assert outcome.plan is None
    assert outcome.repaired is True
    assert len(gateway.requests) == 2


def test_repair_prompt_has_hard_output_boundaries_and_preserves_unreported_valid_fields():
    malformed = _plan()
    malformed["required_evidence"] = {"alerts": "current high-severity alerts"}
    gateway = SequenceGateway([json.dumps(malformed), json.dumps(_plan())])

    outcome = plan_turn(_packet(), gateway=gateway, config=_config())

    assert outcome.status == "planned"
    prompt = gateway.requests[1].prompt
    assert prompt.startswith("Return ONLY the repaired JSON object. Your entire response must begin with { and end with }.")
    assert prompt.endswith("Return ONLY one JSON object beginning with { and ending with }; no text before or after it.")
    assert '"preserved_fields"' in prompt
    assert '"resolved_entities"' in prompt
    assert '"evidence_requirements"' in prompt
    assert '"proposed_strategy"' in prompt
    assert "Change only invalid or dependent fields" in prompt


@pytest.mark.parametrize(
    "intent,strategy,sufficiency,entities,tools,requirements,clarification",
    [
        ("state_summary", "direct_answer", "sufficient", [], [], {}, None),
        ("fresh_evidence_lookup", "quick_evidence_lookup", "insufficient", [], ["alerts"], {"severity": "high"}, None),
        ("decision_support", "decision_support", "sufficient", [{"type": "alert", "id": "9078"}], [], {}, None),
        ("artifact_draft", "artifact_draft", "sufficient", [{"type": "alert", "id": "9078"}], [], {}, None),
        ("bounded_investigation", "bounded_investigation", "insufficient", [{"type": "alert", "id": "9078"}], [], {}, None),
        ("comparison", "compare_entities", "insufficient", [{"type": "alert", "id": "9078"}, {"type": "alert", "id": "9011"}], [], {}, None),
        ("clarification", "clarification_required", "ambiguous", [], [], {}, "Which alert did you mean?"),
    ],
)
def test_controlled_valid_outputs_reach_every_planner_capability_contract(
    intent, strategy, sufficiency, entities, tools, requirements, clarification
):
    value = _plan(
        intent=intent,
        strategy=strategy,
        sufficiency=sufficiency,
        entities=entities,
        tools=tools,
        requirements=requirements,
        clarification=clarification,
    )

    plan, errors = parse_and_validate_plan(json.dumps(value), _packet().payload)

    assert errors == []
    assert plan is not None
    assert plan.current_turn_intent == intent
    assert plan.proposed_strategy == strategy


@pytest.mark.parametrize(
    "question",
    [
        "What's the newest HIGH alert?",
        "Show the latest high-severity alert.",
        "Did any high priority alert just arrive?",
    ],
)
def test_varied_open_lookup_turns_use_canonical_zero_entity_plan(question):
    gateway = SequenceGateway([json.dumps(_plan(entities=[]))])

    outcome = plan_turn(_packet(question), gateway=gateway, config=_config())

    assert outcome.status == "planned"
    assert outcome.plan.current_turn_intent == "fresh_evidence_lookup"
    assert outcome.plan.proposed_strategy == "quick_evidence_lookup"
    assert outcome.plan.resolved_entities == ()
    assert len(gateway.requests) == 1


@pytest.mark.parametrize("question", ["Which IP?", "Compare which alerts?", "Is which one worse?"])
def test_varied_ambiguity_turns_accept_canonical_clarification_plan(question):
    value = _plan(
        intent="clarification",
        strategy="clarification_required",
        sufficiency="ambiguous",
        entities=[],
        tools=[],
        requirements={},
        clarification="Which alert or source IP did you mean?",
    )
    gateway = SequenceGateway([json.dumps(value)])

    outcome = plan_turn(_packet(question), gateway=gateway, config=_config())

    assert outcome.status == "planned"
    assert outcome.plan.current_turn_intent == "clarification"
    assert outcome.plan.proposed_strategy == "clarification_required"
    assert outcome.plan.clarification_question
    assert outcome.plan.proposed_tool_categories == ()


def test_repair_prompt_is_independently_bounded_and_does_not_embed_initial_prompt():
    malformed = _plan()
    malformed["required_evidence"] = {"alerts": "current high-severity alerts"}
    gateway = SequenceGateway([json.dumps(malformed), json.dumps(_plan())])

    outcome = plan_turn(_packet(), gateway=gateway, config=_config())

    assert outcome.status == "planned"
    assert outcome.repaired is True
    assert outcome.repair_prompt_chars == len(gateway.requests[1].prompt)
    assert len(gateway.requests[0].prompt) <= 8000
    assert len(gateway.requests[1].prompt) <= 8000
    assert "REPAIR_PACKET=" in gateway.requests[1].prompt
    assert "SERVER_PACKET=" not in gateway.requests[1].prompt
    assert gateway.requests[0].prompt not in gateway.requests[1].prompt


def test_gateway_receives_exact_prompt_approved_by_complete_builder():
    packet = _packet()
    gateway = SequenceGateway([json.dumps(_plan())])

    outcome = plan_turn(packet, gateway=gateway, config=_config())

    assert outcome.status == "planned"
    assert gateway.requests[0].prompt == outcome.packet.prompt
    assert len(gateway.requests[0].prompt) + outcome.packet.gateway_framing_chars <= 8000


def test_repair_mandatory_overflow_fails_without_second_gateway_call():
    packet = build_planner_packet(
        question="Q" * 1800,
        request_context={"context_type": "general"},
        conversation_packet={"entities": []},
        preferred_capability=None,
        latency_class={"mode": "sync"},
        max_prompt_chars=8000,
    )
    oversized_invalid_proposal = json.dumps(
        {"current_turn_intent": "fresh_evidence_lookup", "padding": "x" * 3300}
    )
    gateway = SequenceGateway([oversized_invalid_proposal, json.dumps(_plan())])

    outcome = plan_turn(packet, gateway=gateway, config=_config())

    assert outcome.status == "invalid"
    assert outcome.error_code == "agentic_plan_repair_too_large"
    assert outcome.plan is None
    assert len(gateway.requests) == 1


@pytest.mark.parametrize(
    "relationship",
    [
        "continuation",
        "comparison",
        "entity_switch",
        "clarification_response",
        "new_question",
    ],
)
def test_planner_relationship_is_model_owned_and_validated(relationship):
    packet = _packet()

    plan, errors = parse_and_validate_plan(json.dumps(_plan(relationship=relationship)), packet.payload)

    assert errors == []
    assert plan.relationship_to_prior_turn == relationship


@pytest.mark.parametrize(
    "mutator,expected",
    [
        (lambda value: value.update(proposed_capability="generate_artifact"), "incompatible"),
        (lambda value: value.update(relationship_to_prior_turn="not_a_relationship"), "relationship_to_prior_turn is invalid"),
        (lambda value: value.update(proposed_tool_categories=["delete_alert"]), "unapproved"),
        (lambda value: value.update(proposed_tool_categories=["alerts", "events"]), "at most one"),
        (lambda value: value.update(safety={"read_only": False, "mutation_allowed": True}), "unknown plan fields"),
        (lambda value: value.update(execution_metadata={"workflow_request_id": "invented"}), "unknown plan fields"),
        (lambda value: value.update(evidence_sufficiency="sufficient", proposed_strategy="quick_evidence_lookup"), "insufficient"),
    ],
)
def test_semantically_invalid_plans_fail_closed(mutator, expected):
    value = _plan()
    mutator(value)
    plan, errors = parse_and_validate_plan(json.dumps(value), _packet().payload)
    assert plan is None
    assert any(expected in error for error in errors)


def test_planner_uses_exactly_one_repair():
    gateway = SequenceGateway(["not-json", json.dumps(_plan())])
    outcome = plan_turn(_packet(), gateway=gateway, config=_config())
    assert outcome.status == "planned"
    assert outcome.repaired is True
    assert len(gateway.requests) == 2
    assert gateway.requests[0].profile == AI_PROFILE_AGENTIC_PLANNING
    assert gateway.requests[1].profile == AI_PROFILE_AGENTIC_PLANNING
    assert gateway.requests[0].metadata["read_only"] is True


def test_planner_repairs_one_cross_field_contradiction_without_server_rewriting():
    contradictory = _plan(
        sufficiency="sufficient",
        strategy="direct_answer",
        tools=["alerts"],
    )
    gateway = SequenceGateway([json.dumps(contradictory), json.dumps(_plan())])

    outcome = plan_turn(_packet(), gateway=gateway, config=_config())

    assert outcome.status == "planned"
    assert outcome.repaired is True
    assert outcome.plan.proposed_strategy == "quick_evidence_lookup"
    assert len(gateway.requests) == 2


def test_planner_repairs_entity_lookup_binding_without_server_rewriting():
    inconsistent = _plan(
        intent="evidence_explanation",
        entities=[{"type": "alert", "id": "9663"}],
        requirements={"limit": 1, "sort": "newest"},
    )
    repaired = _plan(
        intent="evidence_explanation",
        entities=[{"type": "alert", "id": "9663"}],
        requirements={"alert_id": 9663, "limit": 1},
    )
    gateway = SequenceGateway([json.dumps(inconsistent), json.dumps(repaired)])

    outcome = plan_turn(_packet("Explain the selected alert."), gateway=gateway, config=_config())

    assert outcome.status == "planned"
    assert outcome.repaired is True
    assert outcome.plan.resolved_entities == ({"type": "alert", "id": "9663"},)
    assert outcome.plan.evidence_requirements == {"alert_id": 9663, "limit": 1}
    assert "must bind resolved alert 9663" in gateway.requests[1].prompt
    assert len(gateway.requests) == 2


def test_real_planner_request_reaches_anthropic_generation_contract(monkeypatch):
    calls = []

    def fake_http(*, payload, headers, timeout):
        calls.append({"payload": payload, "headers": headers, "timeout": timeout})
        return {"content": [{"type": "text", "text": json.dumps(_plan())}], "usage": {}}

    monkeypatch.setattr("core.ai.providers._anthropic_http_json", fake_http)
    config = _anthropic_config()
    gateway = AiGateway(
        config=config,
        providers={"anthropic": AnthropicProvider()},
        accounting_store=AllowingAccountingStore(),
    )

    outcome = plan_turn(_packet(), gateway=gateway, config=config)

    assert outcome.status == "planned"
    assert outcome.plan.proposed_strategy == "quick_evidence_lookup"
    assert outcome.provider_status == AI_STATUS_SUCCESS
    assert len(calls) == 1
    assert calls[0]["payload"]["model"] == "claude-test-model"
    assert calls[0]["payload"]["max_tokens"] == 4096
    assert calls[0]["timeout"] == 90.0


def test_initial_and_repair_planner_generations_each_receive_full_profile_timeout(monkeypatch):
    malformed = _plan()
    malformed["required_evidence"] = {"alerts": "current high-severity alerts"}
    responses = [json.dumps(malformed), json.dumps(_plan())]
    calls = []

    def fake_http(*, payload, headers, timeout):
        calls.append({"payload": payload, "headers": headers, "timeout": timeout})
        return {"content": [{"type": "text", "text": responses.pop(0)}], "usage": {}}

    monkeypatch.setattr("core.ai.providers._anthropic_http_json", fake_http)
    config = _anthropic_config()
    accounting = AllowingAccountingStore()

    outcome = plan_turn(
        _packet(),
        gateway=AiGateway(
            config=config,
            providers={"anthropic": AnthropicProvider()},
            accounting_store=accounting,
        ),
        config=config,
    )

    assert outcome.status == "planned"
    assert outcome.repaired is True
    assert len(calls) == 2
    assert all(call["payload"]["model"] == "claude-test-model" for call in calls)
    assert all(call["timeout"] == 90.0 for call in calls)
    assert accounting.kinds == ["initial", "repair"]
    assert accounting.correlations[0]
    assert accounting.correlations[0] == accounting.correlations[1]


def test_repair_budget_exhaustion_blocks_second_anthropic_call_and_degrades_gracefully(monkeypatch):
    malformed = _plan()
    malformed["required_evidence"] = {"alerts": "current high-severity alerts"}
    calls = []

    def fake_http(*, payload, headers, timeout):
        calls.append({"payload": payload, "headers": headers, "timeout": timeout})
        return {"content": [{"type": "text", "text": json.dumps(malformed)}], "usage": {}}

    monkeypatch.setattr("core.ai.providers._anthropic_http_json", fake_http)
    config = _anthropic_config()
    accounting = RepairBudgetExhaustedAccountingStore()
    outcome = plan_turn(
        _packet(),
        gateway=AiGateway(
            config=config,
            providers={"anthropic": AnthropicProvider()},
            accounting_store=accounting,
        ),
        config=config,
    )

    assert len(calls) == 1
    assert accounting.kinds == ["initial", "repair"]
    assert accounting.correlations[0] == accounting.correlations[1]
    assert outcome.status == "unavailable"
    assert outcome.repaired is True
    assert outcome.provider_status == AI_STATUS_BUDGET_EXHAUSTED
    assert outcome.error_code == AI_STATUS_BUDGET_EXHAUSTED
    assert outcome.plan is None


def test_planner_rejects_empty_required_reasoning_summary():
    value = _plan()
    value["reasoning_summary"] = ""

    plan, errors = parse_and_validate_plan(json.dumps(value), _packet().payload)

    assert plan is None
    assert any("reasoning_summary is required" in error for error in errors)


def test_planner_derives_nonessential_metadata_when_omitted():
    value = _plan()
    value.pop("confidence")
    value.pop("clarification_question")

    plan, errors = parse_and_validate_plan(json.dumps(value), _packet().payload)

    assert errors == []
    assert plan.confidence == "unknown"
    assert plan.clarification_question is None
    assert plan.stopping_condition.startswith("Stop after one bounded read")


def test_clarification_question_is_required_only_for_clarification_strategy():
    value = _plan(
        intent="clarification",
        strategy="clarification_required",
        sufficiency="ambiguous",
        tools=[],
        requirements={},
    )
    value.pop("clarification_question")

    plan, errors = parse_and_validate_plan(json.dumps(value), _packet("Which IP?").payload)

    assert plan is None
    assert any("needs clarification_question" in error for error in errors)


@pytest.mark.parametrize(
    "action,strategy",
    [
        ("fresh_evidence_lookup", "direct_answer"),
        ("decision_support", "direct_answer"),
        ("artifact_draft", "direct_answer"),
        ("state_summary", "quick_evidence_lookup"),
    ],
)
def test_current_turn_action_rejects_incompatible_strategy(action, strategy):
    value = _plan(
        intent=action,
        strategy=strategy,
        sufficiency="sufficient" if strategy == "direct_answer" else "insufficient",
        tools=[] if strategy == "direct_answer" else ["alerts"],
        requirements={} if strategy == "direct_answer" else {"limit": 1},
    )

    plan, errors = parse_and_validate_plan(json.dumps(value), _packet().payload)

    assert plan is None
    assert any("incompatible" in error for error in errors)


def test_literal_ip_lookup_is_interpreted_by_planner_without_server_injection():
    packet = _packet("Show me alerts from 18.232.121.80.")
    value = _plan(
        requirements={"source_ip": "18.232.121.80", "limit": 10},
        entities=[{"type": "source_ip", "id": "18.232.121.80"}],
    )

    plan, errors = parse_and_validate_plan(json.dumps(value), packet.payload)

    assert errors == []
    assert plan.evidence_requirements == {"source_ip": "18.232.121.80", "limit": 10}
    assert plan.evidence_filter_provenance == {
        "source_ip": "planner_interpreted",
        "limit": "planner_interpreted",
    }


def test_server_does_not_parse_sentence_to_add_or_remove_filters():
    packet = _packet("Look into the source again.")
    value = _plan(requirements={"source_ip": "18.232.121.80", "limit": 10}, entities=[{"type": "source_ip", "id": "18.232.121.80"}])

    plan, errors = parse_and_validate_plan(json.dumps(value), packet.payload)

    assert errors == []
    assert plan.evidence_requirements == {"source_ip": "18.232.121.80", "limit": 10}


def test_authoritative_context_is_available_without_preplanner_resolution():
    packet = build_planner_packet(
        question="Show me alerts from this IP.",
        request_context={"context_type": "source_ip"},
        conversation_packet={
            "entities": [
                {"type": "source_ip", "id": "18.232.121.80", "source_type": "thread_state"},
                {"type": "alert", "id": "9078", "source_type": "thread_record"},
            ],
            "recent_conclusions": [{"summary": "Current source remains under review."}],
        },
        preferred_capability=None,
        latency_class={"mode": "sync"},
    )
    value = _plan(requirements={"source_ip": "18.232.121.80", "limit": 10}, entities=[{"type": "source_ip", "id": "18.232.121.80"}], relationship="continuation")

    plan, errors = parse_and_validate_plan(json.dumps(value), packet.payload)

    assert errors == []
    assert any(item["id"] == "18.232.121.80" for item in packet.payload["facts"]["entities"])
    assert plan.resolved_entities[0]["id"] == "18.232.121.80"


def test_fresh_lookup_does_not_inherit_prior_time_or_severity_filters():
    packet = build_planner_packet(
        question="Show me alerts from this IP.",
        request_context={"context_type": "source_ip"},
        conversation_packet={
            "entities": [{"type": "source_ip", "id": "18.232.121.80", "source_type": "thread_record"}],
            "conversation_summary": "A prior lookup used a 30-minute HIGH filter.",
        },
        preferred_capability=None,
        latency_class={"mode": "sync"},
    )
    value = _plan(requirements={"source_ip": "18.232.121.80", "limit": 10}, entities=[{"type": "source_ip", "id": "18.232.121.80"}])

    plan, errors = parse_and_validate_plan(json.dumps(value), packet.payload)

    assert errors == []
    assert "time_window_minutes" not in plan.evidence_requirements
    assert "severity" not in plan.evidence_requirements


def test_quick_evidence_lookup_requires_named_evidence():
    value = _plan()
    value["required_evidence"] = []

    plan, errors = parse_and_validate_plan(json.dumps(value), _packet().payload)

    assert plan is None
    assert any("requires at least one required_evidence item" in error for error in errors)


@pytest.mark.parametrize(
    "requirements,expected",
    [
        ({"unknown_filter": "value"}, "unknown filters"),
        ({"severity": "urgent"}, "severity is invalid"),
        ({"source_ip": "not-an-ip"}, "source_ip is invalid"),
        ({"destination_ip": "999.1.1.1"}, "destination_ip is invalid"),
        ({"username": "jsmith' OR 1=1"}, "username is invalid"),
        ({"time_window_minutes": 0}, "time_window_minutes is invalid"),
        ({"time_window_minutes": 10081}, "time_window_minutes is invalid"),
        ({"sort": "random"}, "sort is invalid"),
        ({"limit": 11}, "limit is invalid"),
    ],
)
def test_evidence_requirements_reject_unknown_or_unbounded_filters(requirements, expected):
    plan, errors = parse_and_validate_plan(
        json.dumps(_plan(requirements=requirements, entities=[])),
        _packet().payload,
    )

    assert plan is None
    assert any(expected in error for error in errors)


def test_alert_evidence_requirements_are_normalized_without_query_generation():
    requirements = {
        "severity": "HIGH",
        "alert_type": "failed_login",
        "source_ip": "203.0.113.81",
        "destination_ip": "10.0.0.8",
        "time_window_minutes": 60,
        "sort": "newest",
        "limit": 1,
    }

    plan, errors = parse_and_validate_plan(
        json.dumps(_plan(requirements=requirements, entities=[])),
        _packet(
            "Show the newest HIGH failed_login alert from source 203.0.113.81 to destination 10.0.0.8 in the last hour."
        ).payload,
    )

    assert errors == []
    assert plan.evidence_requirements == {**requirements, "severity": "high"}
    assert set(plan.evidence_filter_provenance.values()) == {"planner_interpreted"}


@pytest.mark.parametrize(
    "question,expected_minutes",
    [
        ("What happened in the last hour?", 60),
        ("Show alerts from the past 30 minutes.", 30),
        ("Review activity over the previous 2 days.", 2880),
    ],
)
def test_duration_is_interpreted_by_planner_and_bounded_by_server(question, expected_minutes):
    plan, errors = parse_and_validate_plan(
        json.dumps(_plan(requirements={"time_window_minutes": expected_minutes, "limit": 10}, entities=[])),
        _packet(question).payload,
    )

    assert errors == []
    assert plan.evidence_requirements["time_window_minutes"] == expected_minutes


def test_planner_prompt_defines_sort_semantics_without_accepting_aliases():
    gateway = SequenceGateway([json.dumps(_plan())])

    outcome = plan_turn(_packet(), gateway=gateway, config=_config())

    assert outcome.status == "planned"
    prompt = gateway.requests[0].prompt
    assert _prompt_contract(prompt)["filter_formats"]["sort"] == ["newest", "oldest", "severity"]
    assert all(alias not in _prompt_contract(prompt)["filter_formats"]["sort"] for alias in ("timestamp", "asc", "desc"))


def test_planner_repair_reports_required_evidence_type_contract_precisely():
    malformed = _plan()
    malformed["required_evidence"] = {"alerts": "current high-severity alerts"}
    gateway = SequenceGateway([json.dumps(malformed), json.dumps(_plan())])

    outcome = plan_turn(_packet(), gateway=gateway, config=_config())

    assert outcome.status == "planned"
    assert outcome.repaired is True
    assert len(gateway.requests) == 2
    repair_prompt = gateway.requests[1].prompt
    assert "required_evidence must be a list" in repair_prompt
    assert _prompt_contract(repair_prompt)["shape"]["required_evidence"] == "array<=6[nonempty_string]"
    assert "Correct every typed violation" in repair_prompt


def test_repair_cannot_change_the_initial_valid_action_classification():
    malformed = _plan()
    malformed["required_evidence"] = {"alerts": "current high-severity alerts"}
    changed = _plan(
        intent="state_summary",
        strategy="direct_answer",
        sufficiency="sufficient",
        tools=[],
        requirements={},
    )
    gateway = SequenceGateway([json.dumps(malformed), json.dumps(changed)])

    outcome = plan_turn(_packet(), gateway=gateway, config=_config())

    assert outcome.status == "invalid"
    assert outcome.plan is None
    assert '"current_turn_intent":"fresh_evidence_lookup"' in gateway.requests[1].prompt
    assert '"preserved_fields"' in gateway.requests[1].prompt


def test_contradictory_repaired_direct_answer_still_fails_closed():
    malformed = _plan()
    malformed["required_evidence"] = {"alerts": "current high-severity alerts"}
    contradictory = _plan(
        intent="state_summary",
        strategy="direct_answer",
        sufficiency="insufficient",
        tools=[],
        requirements={},
    )
    gateway = SequenceGateway([json.dumps(malformed), json.dumps(contradictory)])

    outcome = plan_turn(_packet(), gateway=gateway, config=_config())

    assert outcome.status == "invalid"
    assert outcome.plan is None
    assert outcome.repaired is True
    assert len(gateway.requests) == 2


def test_planner_prompt_describes_state_summary_contract_without_server_routing():
    gateway = SequenceGateway([json.dumps(_plan(intent="state_summary", strategy="direct_answer", sufficiency="sufficient", tools=[], requirements={}))])
    packet = _packet("Summarize our current investigation.")

    outcome = plan_turn(packet, gateway=gateway, config=_config())

    assert outcome.status == "planned"
    rows = _prompt_contract(gateway.requests[0].prompt)["action_strategy"]["rows"]
    state_summary = next(row for row in rows if row[:2] == ["state_summary", "direct_answer"])
    assert state_summary[2:8] == [0, 1, False, False, False, "quick_explain"]


def test_second_invalid_plan_does_not_fall_back_to_prior_workflow():
    gateway = SequenceGateway(["not-json", "still-not-json"])
    outcome = plan_turn(_packet(), gateway=gateway, config=_config())
    assert outcome.status == "invalid"
    assert outcome.plan is None
    assert outcome.error_code == "invalid_agentic_plan"
    assert len(gateway.requests) == 2


def test_validation_errors_are_typed_by_parse_schema_semantic_and_binding_stage():
    parse_plan, parse_errors = parse_and_validate_plan('{"current_turn_intent":', _packet().payload)
    schema_value = _plan()
    schema_value.pop("required_evidence")
    schema_plan, schema_errors = parse_and_validate_plan(json.dumps(schema_value), _packet().payload)
    semantic_value = _plan()
    semantic_value["proposed_capability"] = "deep_investigate"
    semantic_plan, semantic_errors = parse_and_validate_plan(json.dumps(semantic_value), _packet().payload)
    binding_value = _plan(entities=[{"type": "alert", "id": "9663"}], requirements={"alert_id": 9682})
    binding_plan, binding_errors = parse_and_validate_plan(json.dumps(binding_value), _packet().payload)

    assert parse_plan is schema_plan is semantic_plan is binding_plan is None
    assert parse_errors[0].as_dict() == {
        "stage": "parse",
        "code": "invalid_json_object",
        "path": "$",
        "message": "response must be one JSON object",
    }
    assert any(error.stage == "schema" and error.code == "missing_required_fields" for error in schema_errors)
    assert any(error.stage == "semantic" and error.path == "proposed_capability" for error in semantic_errors)
    assert any(error.stage == "entity_binding" and error.code == "mismatched_entity_identity" for error in binding_errors)


@pytest.mark.parametrize("content", ['{"current_turn_intent":', None])
def test_initial_output_exhaustion_is_classified_before_validation_or_repair(content):
    gateway = CompletionGateway(
        [{
            "content": content,
            "completion_state": PROVIDER_COMPLETION_OUTPUT_EXHAUSTED,
            "stop_reason": "max_tokens",
            "input_tokens": 42,
            "output_tokens": 4096,
            "accounting_attempt_id": "attempt-initial",
        }]
    )

    outcome = plan_turn(_packet(), gateway=gateway, config=_config())

    assert outcome.status == "truncated"
    assert outcome.error_code == "agentic_plan_output_exhausted"
    assert outcome.repaired is False
    assert len(gateway.requests) == 1
    assert outcome.attempts[0].validation_errors[0].stage == "provider_completion"
    assert outcome.attempts[0].validation_errors[0].code == "output_exhausted"
    assert outcome.attempts[0].plan_chars == len(content or "")
    assert outcome.attempts[0].accounting_attempt_id == "attempt-initial"


def test_repair_output_exhaustion_retains_both_attempt_classifications():
    malformed = _plan()
    malformed["required_evidence"] = "current alerts"
    gateway = CompletionGateway(
        [
            {"content": json.dumps(malformed), "completion_state": PROVIDER_COMPLETION_COMPLETE, "stop_reason": "end_turn"},
            {"content": '{"current_turn_intent":', "completion_state": PROVIDER_COMPLETION_OUTPUT_EXHAUSTED, "stop_reason": "max_tokens"},
        ]
    )

    outcome = plan_turn(_packet(), gateway=gateway, config=_config())

    assert outcome.status == "truncated"
    assert outcome.error_code == "agentic_plan_repair_output_exhausted"
    assert outcome.repaired is True
    assert len(gateway.requests) == 2
    assert [attempt.stage for attempt in outcome.attempts] == ["initial", "repair"]
    assert outcome.attempts[0].validation_errors[0].stage == "schema"
    assert outcome.attempts[1].validation_errors[0].stage == "provider_completion"


def test_failed_repair_metadata_retains_bounded_attempt_errors_without_raw_plans():
    gateway = CompletionGateway(
        [
            {"content": "not-json", "completion_state": PROVIDER_COMPLETION_COMPLETE, "stop_reason": "end_turn"},
            {"content": "still-not-json", "completion_state": PROVIDER_COMPLETION_COMPLETE, "stop_reason": "end_turn"},
        ]
    )

    outcome = plan_turn(_packet(), gateway=gateway, config=_config())
    metadata = outcome.metadata()

    assert outcome.status == "invalid"
    assert [attempt["validation_errors"][0]["stage"] for attempt in metadata["attempts"]] == ["parse", "parse"]
    assert "not-json" not in json.dumps(metadata)
    assert "still-not-json" not in json.dumps(metadata)


@pytest.mark.parametrize("fixture", build_planner_reliability_fixtures(), ids=lambda fixture: fixture["name"])
def test_offline_acceptance_planner_reliability_fixtures(fixture):
    gateway = CompletionGateway(fixture["responses"])

    outcome = plan_turn(_packet(), gateway=gateway, config=_config())

    expected = fixture["expected"]
    assert outcome.status == expected["status"]
    assert outcome.repaired is expected["repaired"]
    assert outcome.error_code == expected["error_code"]
    assert len(gateway.requests) == expected["requests"]
    assert all(request.capability == "agentic_analyst_planning" for request in gateway.requests)


def test_provider_timeout_returns_unavailable_without_repair_or_sticky_plan():
    gateway = FailureGateway()
    outcome = plan_turn(_packet(), gateway=gateway, config=_config())
    assert outcome.status == "unavailable"
    assert outcome.plan is None
    assert outcome.provider_status == "provider_timeout"
    assert len(gateway.requests) == 1


def test_stale_or_missing_evidence_cannot_validate_as_sufficient():
    packet = build_planner_packet(
        question="What is the newest HIGH alert?",
        request_context={"context_type": "alert"},
        conversation_packet={
            "entities": [{"type": "alert", "id": "9078", "source_type": "request_context"}],
            "bounds": {"stale_evidence_excluded": 4},
            "recent_tool_results": [],
        },
        preferred_capability=None,
        latency_class={"mode": "sync"},
    )
    value = _plan(strategy="direct_answer", sufficiency="sufficient", tools=[])
    plan, errors = parse_and_validate_plan(json.dumps(value), packet.payload)
    assert plan is None
    assert any("verified evidence or relevant thread state" in error for error in errors)
    assert packet.payload["evidence_freshness"]["stale_evidence_excluded"] == 4


@pytest.mark.parametrize("capability", ["quick_explain", "deep_investigate", "decision_support", "generate_artifact"])
def test_planner_packet_and_prompt_fit_each_participating_capability(capability):
    packet = build_planner_packet(
        question="Assess the current alert and tell me what matters now.",
        request_context={"context_type": "alert"},
        conversation_packet={
            "entities": [{"type": "alert", "id": "9078", "source_type": "request_context"}],
            "conversation_summary": "Blocked scan activity remains under review.",
            "recent_tool_results": [{"summary": "Three blocked attempts", "fresh": True}],
        },
        preferred_capability=capability,
        latency_class={"mode": "sync" if capability == "quick_explain" else "polling"},
    )
    assert packet.serialized_chars <= PLANNER_PACKET_MAX_CHARS
    assert packet.prompt_chars < 8000


@pytest.mark.parametrize("question", ["Which one?", "Check that IP.", "Is it bad?"])
def test_ambiguity_paraphrases_require_clarification(question):
    packet = _packet(question)
    value = _plan(
        intent="clarification",
        strategy="clarification_required",
        sufficiency="ambiguous",
        tools=[],
        clarification="Which alert or IP do you mean?",
    )
    plan, errors = parse_and_validate_plan(json.dumps(value), packet.payload)
    assert errors == []
    assert plan.proposed_strategy == "clarification_required"


@pytest.mark.parametrize(
    "question",
    ["Inspect the repository code.", "Continue the SOC Briefing.", "Apply the block action now."],
)
def test_boundary_paraphrases_remain_outside_siem_capabilities(question):
    packet = _packet(question)
    value = _plan(
        intent="unsupported",
        strategy="unsupported_or_boundary",
        sufficiency="sufficient",
        tools=[],
    )
    plan, errors = parse_and_validate_plan(json.dumps(value), packet.payload)
    assert errors == []
    assert plan.proposed_capability is None


@pytest.mark.parametrize(
    "question,intent,strategy,capability,sufficiency,tools",
    [
        *[(question, "fresh_evidence_lookup", "quick_evidence_lookup", "quick_explain", "insufficient", ["alerts"]) for question in (
            "What's the newest HIGH alert?", "Show me the latest high-severity alert.", "Anything high priority just come in?"
        )],
        *[(question, "decision_support", "decision_support", "decision_support", "insufficient", []) for question in (
            "Which alert matters most right now?", "What should I actually care about?", "Which one needs attention first?"
        )],
        *[(question, "evidence_explanation", "direct_answer", "quick_explain", "sufficient", []) for question in (
            "Why?", "What makes you say that?", "Walk me through your reasoning."
        )],
        *[(question, "evidence_explanation", "direct_answer", "quick_explain", "sufficient", []) for question in (
            "Show me the evidence.", "What supports that?", "What did you base that on?"
        )],
        *[(question, "fresh_evidence_lookup", "quick_evidence_lookup", "quick_explain", "insufficient", ["alerts"]) for question in (
            "Now show me the most recent brute-force alert.", "Forget that—what happened with authentication alerts?", "Switch gears. Anything unusual on the firewall?"
        )],
        *[(question, "comparison", "compare_entities", "deep_investigate", "insufficient", []) for question in (
            "Compare those two.", "Which is worse?", "Is this more serious than the scan from earlier?"
        )],
        *[(question, "analyst_correction", "direct_answer", "quick_explain", "sufficient", []) for question in (
            "That IP is our approved scanner.", "We own that address.", "That account is a service account."
        )],
        *[(question, "state_summary", "direct_answer", "quick_explain", "sufficient", []) for question in (
            "What did we already rule out?", "Summarize our current conclusion.", "What are we still uncertain about?"
        )],
    ],
)
def test_behavioral_paraphrases_validate_consistently(question, intent, strategy, capability, sufficiency, tools):
    packet = build_planner_packet(
        question=question,
        request_context={"context_type": "alert"},
        conversation_packet={
            "entities": [
                {"type": "alert", "id": "9078", "source_type": "request_context"},
                {"type": "alert", "id": "9078", "source_type": "thread_record"},
                {"type": "alert", "id": "9011", "source_type": "thread_state"},
            ],
            "recent_conclusions": [{"summary": "Current conclusion"}],
            "recent_tool_results": [],
        },
        preferred_capability="quick_explain",
        latency_class={"mode": "sync"},
    )
    value = _plan(
        intent=intent,
        strategy=strategy,
        sufficiency=sufficiency,
        tools=tools,
        entities=[] if strategy == "quick_evidence_lookup" else None,
        referenced_turn_sequence=2 if intent == "analyst_correction" else None,
        requirements=(
            {"severity": "high", "limit": 1}
            if strategy == "quick_evidence_lookup" and "high" in question.lower()
            else ({"limit": 1} if strategy == "quick_evidence_lookup" else {})
        ),
    )
    plan, errors = parse_and_validate_plan(json.dumps(value), packet.payload)
    assert errors == []
    assert plan.proposed_strategy == strategy
    assert plan.proposed_capability == capability


@pytest.mark.parametrize(
    "question,action,strategy,capability,sufficiency",
    [
        ("Draft an investigation checklist for this alert.", "artifact_draft", "artifact_draft", "generate_artifact", "sufficient"),
        ("Create an escalation-summary preview.", "artifact_draft", "artifact_draft", "generate_artifact", "sufficient"),
        ("Write an incident-note draft.", "artifact_draft", "artifact_draft", "generate_artifact", "sufficient"),
        ("Investigate this alert further.", "bounded_investigation", "bounded_investigation", "deep_investigate", "insufficient"),
        ("Correlate the related activity.", "bounded_investigation", "bounded_investigation", "deep_investigate", "insufficient"),
        ("Do a deeper investigation of this incident.", "bounded_investigation", "bounded_investigation", "deep_investigate", "insufficient"),
    ],
)
def test_artifact_and_investigation_paraphrases_reach_dedicated_capabilities(
    question,
    action,
    strategy,
    capability,
    sufficiency,
):
    plan, errors = parse_and_validate_plan(
        json.dumps(
            _plan(
                intent=action,
                strategy=strategy,
                sufficiency=sufficiency,
                tools=[],
                requirements={},
            )
        ),
        _packet(question).payload,
    )

    assert errors == []
    assert plan.proposed_capability == capability


PLANNER_BOUNDARY_SCENARIOS = {
    "state_summary": (
        ("What are we investigating?", "Where are we right now?", "Summarize the current investigation."),
        _plan(intent="state_summary", strategy="direct_answer", sufficiency="sufficient", tools=[]),
    ),
    "fresh_lookup_previous_entity": (
        ("Show me alerts from this IP.", "Check that source again.", "Find newer activity from it."),
        _plan(intent="fresh_evidence_lookup", strategy="quick_evidence_lookup", sufficiency="insufficient", tools=["alerts"], requirements={"source_ip": "203.0.113.81", "limit": 10}, entities=[{"type": "source_ip", "id": "203.0.113.81"}]),
    ),
    "literal_entity_lookup": (
        ("Show alerts from 203.0.113.81.", "Search 203.0.113.81 for alerts.", "Any activity tied to 203.0.113.81?"),
        _plan(intent="fresh_evidence_lookup", strategy="quick_evidence_lookup", sufficiency="insufficient", tools=["alerts"], requirements={"source_ip": "203.0.113.81", "limit": 10}, entities=[{"type": "source_ip", "id": "203.0.113.81"}]),
    ),
    "decision_support": (
        ("Should I block or monitor this IP?", "What response would you recommend?", "Is escalation justified?"),
        _plan(intent="decision_support", strategy="decision_support", sufficiency="insufficient", tools=[]),
    ),
    "artifact_draft": (
        ("Draft a checklist for this alert.", "Create an escalation summary preview.", "Write an incident-note draft."),
        _plan(intent="artifact_draft", strategy="artifact_draft", sufficiency="insufficient", tools=[]),
    ),
    "investigation_continuation": (
        ("Continue the investigation.", "Keep digging into this alert.", "Take the analysis one step further."),
        _plan(intent="bounded_investigation", strategy="bounded_investigation", sufficiency="insufficient", tools=[]),
    ),
    "comparison": (
        ("Compare those alerts.", "Which of the two is worse?", "Is this more serious than the earlier scan?"),
        _plan(intent="comparison", strategy="compare_entities", sufficiency="insufficient", tools=[], relationship="comparison"),
    ),
    "clarification": (
        ("Which one?", "Check that.", "Is it worse?"),
        _plan(intent="clarification", strategy="clarification_required", sufficiency="ambiguous", tools=[], clarification="Which alert or IP do you mean?"),
    ),
    "topic_switch": (
        ("Switch to the earlier alert.", "Forget this and inspect Alert 9011.", "Now look at the prior scan."),
        _plan(intent="evidence_explanation", strategy="direct_answer", sufficiency="sufficient", tools=[], relationship="entity_switch", entities=[{"type": "alert", "id": "9011"}]),
    ),
    "return_previous": (
        ("Go back to the first alert.", "Return to the earlier investigation.", "Pick up where we left off on Alert 9011."),
        _plan(intent="evidence_explanation", strategy="direct_answer", sufficiency="sufficient", tools=[], relationship="entity_switch", entities=[{"type": "alert", "id": "9011"}]),
    ),
}


@pytest.mark.parametrize(
    "scenario,question",
    [
        (scenario, question)
        for scenario, (questions, _plan_value) in PLANNER_BOUNDARY_SCENARIOS.items()
        for question in questions
    ],
)
def test_three_phrasings_per_required_scenario_cross_the_same_planner_boundary(scenario, question):
    expected = PLANNER_BOUNDARY_SCENARIOS[scenario][1]
    gateway = SequenceGateway([json.dumps(expected)])

    outcome = plan_turn(_packet(question), gateway=gateway, config=_config())

    assert outcome.plan is not None
    assert outcome.plan.current_turn_intent == expected["current_turn_intent"]
    assert outcome.plan.proposed_strategy == expected["proposed_strategy"]
    assert outcome.plan.proposed_capability == expected["proposed_capability"]
    assert outcome.plan.resolved_entities == tuple(expected["resolved_entities"])
    assert json.loads(gateway.requests[0].prompt.split("SERVER_PACKET=", 1)[1])["current_user_message"] == question


def test_repeated_controlled_plans_remain_contract_consistent():
    content = json.dumps(_plan())
    gateway = SequenceGateway([content] * 12)
    outcomes = [plan_turn(_packet(), gateway=gateway, config=_config()) for _ in range(12)]
    assert {outcome.plan.proposed_strategy for outcome in outcomes} == {"quick_evidence_lookup"}
    assert all(outcome.repaired is False for outcome in outcomes)
