from __future__ import annotations

from dataclasses import replace
import json

import pytest

from core.ai.agentic_analyst_planner import (
    PLANNER_PACKET_MAX_CHARS,
    build_planner_packet,
    parse_and_validate_plan,
    plan_turn,
)
from core.ai.config import AI_MODE_LOCAL_ONLY, AiGatewayConfig
from core.ai.models import AI_STATUS_SUCCESS, AiGatewayResponse, AiRequestMetadata


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


def _packet(question="What's the newest HIGH alert?", *, evidence=None, corrections=None):
    return build_planner_packet(
        question=question,
        resolved_context={
            "active_entity": {"type": "alert", "id": "9078", "display_alias": "Alert 9078"},
            "comparison_entities": [],
            "resolution": {"status": "not_needed", "intent": "new_question"},
        },
        conversation_packet={
            "corrections": corrections or [],
            "unresolved_questions": [],
            "conclusions": [{"summary": "Earlier scan explanation", "confidence": "medium"}],
            "verified_evidence": evidence or [],
            "recommendations": [],
            "recent_turns": [{"role": "assistant", "content": "Earlier explanation", "sequence": 2}],
            "analyst_statements": [],
        },
        preferred_capability="quick_explain",
        latency_class={"mode": "sync", "p95_seconds": 8},
    )


def _plan(
    *,
    intent="Find the newest high-severity alert.",
    relationship="new_question",
    sufficiency="insufficient",
    strategy="quick_evidence_lookup",
    capability="quick_explain",
    tools=None,
    entities=None,
    clarification=None,
):
    return {
        "current_turn_intent": intent,
        "relationship_to_prior_turn": relationship,
        "resolved_entities": entities if entities is not None else [{"type": "alert", "id": "9078"}],
        "evidence_sufficiency": sufficiency,
        "required_evidence": ["current high-severity alerts"] if sufficiency == "insufficient" else [],
        "proposed_strategy": strategy,
        "proposed_capability": capability,
        "proposed_tool_categories": tools if tools is not None else (["alerts"] if strategy == "quick_evidence_lookup" else []),
        "clarification_question": clarification,
        "reasoning_summary": "The current question changes task and requires current alert evidence.",
        "stopping_condition": "Stop after identifying the newest accessible high-severity alert.",
        "confidence": "high",
        "safety": {"read_only": True, "mutation_allowed": False},
    }


def test_packet_is_fit_by_construction_with_production_sized_state():
    long = "blocked firewall observation " * 80
    packet = build_planner_packet(
        question="Compare the current alert with the earlier scan and explain what changed.",
        resolved_context={
            "active_entity": {"type": "alert", "id": "9078"},
            "comparison_entities": [{"type": "alert", "id": "9011"}, {"type": "alert", "id": "9078"}],
            "resolution": {"status": "resolved", "intent": "compare"},
        },
        conversation_packet={
            category: [{"content": long, "summary": long, "confidence": "medium"} for _ in range(12)]
            for category in (
                "corrections", "unresolved_questions", "conclusions", "verified_evidence",
                "recommendations", "recent_turns", "analyst_statements", "entities",
            )
        },
        preferred_capability="deep_investigate",
        latency_class={"mode": "polling", "completion_seconds": [45, 90]},
    )
    assert packet.serialized_chars <= PLANNER_PACKET_MAX_CHARS
    assert packet.payload["current_user_message"].startswith("Compare")
    assert packet.payload["resolved_focus"] == {"type": "alert", "id": "9078"}
    assert packet.omitted


def test_valid_plan_is_accepted_and_wrong_entity_is_rejected():
    packet = _packet()
    valid, errors = parse_and_validate_plan(json.dumps(_plan()), packet.payload)
    assert errors == []
    assert valid.proposed_strategy == "quick_evidence_lookup"
    invalid, errors = parse_and_validate_plan(
        json.dumps(_plan(entities=[{"type": "alert", "id": "9999"}])),
        packet.payload,
    )
    assert invalid is None
    assert any("authoritative" in error for error in errors)


@pytest.mark.parametrize(
    "mutator,expected",
    [
        (lambda value: value.update(proposed_capability="generate_artifact"), "does not match"),
        (lambda value: value.update(proposed_tool_categories=["delete_alert"]), "unapproved"),
        (lambda value: value.update(proposed_tool_categories=["alerts", "events"]), "at most one"),
        (lambda value: value.update(safety={"read_only": False, "mutation_allowed": True}), "read_only"),
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
    assert gateway.requests[0].profile == "fast_triage"
    assert gateway.requests[0].metadata["read_only"] is True


def test_second_invalid_plan_does_not_fall_back_to_prior_workflow():
    gateway = SequenceGateway(["not-json", "still-not-json"])
    outcome = plan_turn(_packet(), gateway=gateway, config=_config())
    assert outcome.status == "invalid"
    assert outcome.plan is None
    assert outcome.error_code == "invalid_agentic_plan"
    assert len(gateway.requests) == 2


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
        resolved_context={
            "active_entity": {"type": "alert", "id": "9078"},
            "comparison_entities": [],
            "resolution": {"status": "not_needed", "intent": "new_question"},
        },
        conversation_packet={"bounds": {"stale_evidence_excluded": 4}, "verified_evidence": []},
        preferred_capability=None,
        latency_class={"mode": "sync"},
    )
    value = _plan(strategy="direct_answer", capability="quick_explain", sufficiency="sufficient", tools=[])
    plan, errors = parse_and_validate_plan(json.dumps(value), packet.payload)
    assert plan is None
    assert any("verified evidence or relevant thread state" in error for error in errors)
    assert packet.payload["evidence_freshness"]["stale_evidence_excluded"] == 4


@pytest.mark.parametrize("capability", ["quick_explain", "deep_investigate", "decision_support", "generate_artifact"])
def test_planner_packet_and_prompt_fit_each_participating_capability(capability):
    packet = build_planner_packet(
        question="Assess the current alert and tell me what matters now.",
        resolved_context={
            "active_entity": {"type": "alert", "id": "9078"},
            "comparison_entities": [],
            "resolution": {"status": "not_needed", "intent": "new_question"},
        },
        conversation_packet={
            "thread_summary": "Blocked scan activity remains under review.",
            "verified_evidence": [{"summary": "Three blocked attempts", "fresh": True}],
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
        intent="Resolve an ambiguous referent.",
        strategy="clarification_required",
        capability=None,
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
        intent="Identify a request outside the SIEM conversation planner boundary.",
        strategy="unsupported_or_boundary",
        capability=None,
        sufficiency="sufficient",
        tools=[],
    )
    plan, errors = parse_and_validate_plan(json.dumps(value), packet.payload)
    assert errors == []
    assert plan.proposed_capability is None


@pytest.mark.parametrize(
    "question,intent,strategy,capability,sufficiency,tools",
    [
        *[(question, "Find the newest high-severity alert.", "quick_evidence_lookup", "quick_explain", "insufficient", ["alerts"]) for question in (
            "What's the newest HIGH alert?", "Show me the latest high-severity alert.", "Anything high priority just come in?"
        )],
        *[(question, "Prioritize current alerts.", "decision_support", "decision_support", "insufficient", []) for question in (
            "Which alert matters most right now?", "What should I actually care about?", "Which one needs attention first?"
        )],
        *[(question, "Explain the latest conclusion.", "direct_answer", "quick_explain", "sufficient", []) for question in (
            "Why?", "What makes you say that?", "Walk me through your reasoning."
        )],
        *[(question, "Show supporting evidence.", "direct_answer", "quick_explain", "sufficient", []) for question in (
            "Show me the evidence.", "What supports that?", "What did you base that on?"
        )],
        *[(question, "Switch to a new security topic.", "quick_evidence_lookup", "quick_explain", "insufficient", ["alerts"]) for question in (
            "Now show me the most recent brute-force alert.", "Forget that—what happened with authentication alerts?", "Switch gears. Anything unusual on the firewall?"
        )],
        *[(question, "Compare two resolved alerts.", "compare_entities", "deep_investigate", "insufficient", []) for question in (
            "Compare those two.", "Which is worse?", "Is this more serious than the scan from earlier?"
        )],
        *[(question, "Apply an analyst correction.", "direct_answer", "quick_explain", "sufficient", []) for question in (
            "That IP is our approved scanner.", "We own that address.", "That account is a service account."
        )],
        *[(question, "Summarize thread state.", "direct_answer", "quick_explain", "sufficient", []) for question in (
            "What did we already rule out?", "Summarize our current conclusion.", "What are we still uncertain about?"
        )],
    ],
)
def test_behavioral_paraphrases_validate_consistently(question, intent, strategy, capability, sufficiency, tools):
    entities = [{"type": "alert", "id": "9078"}]
    resolved = {
        "active_entity": entities[0],
        "comparison_entities": ([{"type": "alert", "id": "9011"}, entities[0]] if strategy == "compare_entities" else []),
        "resolution": {"status": "resolved", "intent": "compare" if strategy == "compare_entities" else "new_question"},
    }
    packet = build_planner_packet(
        question=question,
        resolved_context=resolved,
        conversation_packet={"conclusions": [{"summary": "Current conclusion"}], "verified_evidence": []},
        preferred_capability="quick_explain",
        latency_class={"mode": "sync"},
    )
    plan_entities = packet.payload["comparison_entities"] or [packet.payload["resolved_focus"]]
    value = _plan(
        intent=intent,
        strategy=strategy,
        capability=capability,
        sufficiency=sufficiency,
        tools=tools,
        entities=plan_entities,
    )
    plan, errors = parse_and_validate_plan(json.dumps(value), packet.payload)
    assert errors == []
    assert plan.proposed_strategy == strategy


def test_repeated_controlled_plans_remain_contract_consistent():
    content = json.dumps(_plan())
    gateway = SequenceGateway([content] * 12)
    outcomes = [plan_turn(_packet(), gateway=gateway, config=_config()) for _ in range(12)]
    assert {outcome.plan.proposed_strategy for outcome in outcomes} == {"quick_evidence_lookup"}
    assert all(outcome.repaired is False for outcome in outcomes)
