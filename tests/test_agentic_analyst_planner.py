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
from core.ai.gateway import AiGateway
from core.ai.models import AI_STATUS_SUCCESS, AiGatewayResponse, AiRequestMetadata
from core.ai.providers import OllamaProvider
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
    intent="fresh_evidence_lookup",
    sufficiency="insufficient",
    strategy="quick_evidence_lookup",
    tools=None,
    requirements=None,
    clarification=None,
):
    return {
        "current_turn_intent": intent,
        "evidence_sufficiency": sufficiency,
        "required_evidence": ["current high-severity alerts"] if sufficiency == "insufficient" else [],
        "proposed_strategy": strategy,
        "proposed_tool_categories": tools if tools is not None else (["alerts"] if strategy == "quick_evidence_lookup" else []),
        "evidence_requirements": requirements if requirements is not None else (
            {"severity": "high", "limit": 1}
            if strategy == "quick_evidence_lookup"
            else {}
        ),
        "clarification_question": clarification,
        "reasoning_summary": "The current question changes task and requires current alert evidence.",
        "confidence": "high",
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


def test_server_populates_deterministic_plan_fields_and_rejects_model_override():
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
    override["resolved_entities"] = [{"type": "alert", "id": "9999"}]
    invalid, errors = parse_and_validate_plan(json.dumps(override), packet.payload)
    assert invalid is None
    assert any("unknown plan fields: resolved_entities" in error for error in errors)


@pytest.mark.parametrize(
    "resolution_intent,expected",
    [
        ("why", "continuation"),
        ("compare", "comparison"),
        ("explicit_entity", "entity_switch"),
        ("go_back", "entity_switch"),
        ("new_question", "new_question"),
    ],
)
def test_server_derives_relationship_from_authoritative_resolution(resolution_intent, expected):
    packet = _packet()
    packet.payload["reference_resolution"]["intent"] = resolution_intent

    plan, errors = parse_and_validate_plan(json.dumps(_plan()), packet.payload)

    assert errors == []
    assert plan.relationship_to_prior_turn == expected


@pytest.mark.parametrize(
    "mutator,expected",
    [
        (lambda value: value.update(proposed_capability="generate_artifact"), "unknown plan fields"),
        (lambda value: value.update(relationship_to_prior_turn="continuation"), "unknown plan fields"),
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


def test_real_planner_request_reaches_ollama_generation_contract(monkeypatch):
    calls = []

    def fake_http(method, url, *, payload=None, timeout):
        calls.append({"method": method, "url": url, "payload": payload, "timeout": timeout})
        return {"response": json.dumps(_plan())}

    monkeypatch.setattr("core.ai.providers._http_json", fake_http)
    config = replace(_config(), local_provider="ollama")
    gateway = AiGateway(config=config, providers={"ollama": OllamaProvider()})

    outcome = plan_turn(_packet(), gateway=gateway, config=config)

    assert outcome.status == "planned"
    assert outcome.plan.proposed_strategy == "quick_evidence_lookup"
    assert outcome.provider_status == AI_STATUS_SUCCESS
    assert len(calls) == 1
    assert calls[0]["method"] == "POST"
    assert calls[0]["url"].endswith("/api/generate")
    assert calls[0]["payload"]["model"] == "llama3.1:8b"
    assert calls[0]["payload"]["options"]["num_predict"] == 1024


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


def test_plain_literal_ip_lookup_gets_explicit_provenance_without_spurious_filters():
    packet = _packet("Show me alerts from 18.232.121.80.")
    value = _plan(requirements={"limit": 10})

    plan, errors = parse_and_validate_plan(json.dumps(value), packet.payload)

    assert errors == []
    assert plan.evidence_requirements == {"source_ip": "18.232.121.80", "limit": 10}
    assert plan.evidence_filter_provenance == {
        "source_ip": "explicit_current_turn",
        "limit": "planner_proposed",
    }


def test_planner_cannot_invent_time_window_for_plain_source_ip_lookup():
    packet = _packet("Show me alerts from 18.232.121.80.")
    value = _plan(requirements={"source_ip": "18.232.121.80", "time_window_minutes": 30, "limit": 10})

    plan, errors = parse_and_validate_plan(json.dumps(value), packet.payload)

    assert plan is None
    assert any("time_window_minutes is unsupported" in error for error in errors)


def test_authoritative_resolved_ip_can_scope_pronoun_lookup():
    packet = build_planner_packet(
        question="Show me alerts from this IP.",
        resolved_context={
            "active_entity": {"type": "source_ip", "id": "18.232.121.80"},
            "comparison_entities": [],
            "resolution": {"status": "resolved", "intent": "entity_reference"},
            "context": {"source_ip": "18.232.121.80"},
        },
        conversation_packet={"conclusions": [{"summary": "Current source remains under review."}]},
        preferred_capability=None,
        latency_class={"mode": "sync"},
    )
    value = _plan(requirements={"source_ip": "18.232.121.80", "limit": 10})

    plan, errors = parse_and_validate_plan(json.dumps(value), packet.payload)

    assert errors == []
    assert plan.evidence_filter_provenance["source_ip"] == "inherited_authoritative_context"


def test_fresh_lookup_does_not_inherit_prior_time_or_severity_filters():
    packet = build_planner_packet(
        question="Show me alerts from this IP.",
        resolved_context={
            "active_entity": {"type": "source_ip", "id": "18.232.121.80"},
            "comparison_entities": [],
            "resolution": {"status": "resolved", "intent": "entity_reference"},
            "context": {
                "source_ip": "18.232.121.80",
                "time_window_minutes": 30,
                "severity": "high",
            },
        },
        conversation_packet={"thread_summary": "A prior lookup used a 30-minute HIGH filter."},
        preferred_capability=None,
        latency_class={"mode": "sync"},
    )
    value = _plan(
        requirements={
            "source_ip": "18.232.121.80",
            "time_window_minutes": 30,
            "severity": "high",
            "limit": 10,
        }
    )

    plan, errors = parse_and_validate_plan(json.dumps(value), packet.payload)

    assert plan is None
    assert any("time_window_minutes is unsupported" in error for error in errors)
    assert any("severity is unsupported" in error for error in errors)


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
        json.dumps(_plan(requirements=requirements)),
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
        json.dumps(_plan(requirements=requirements)),
        _packet(
            "Show the newest HIGH failed_login alert from source 203.0.113.81 to destination 10.0.0.8 in the last hour."
        ).payload,
    )

    assert errors == []
    assert plan.evidence_requirements == {**requirements, "severity": "high"}
    assert plan.evidence_filter_provenance["source_ip"] == "explicit_current_turn"
    assert plan.evidence_filter_provenance["time_window_minutes"] == "explicit_current_turn"


@pytest.mark.parametrize(
    "question,expected_minutes",
    [
        ("What happened in the last hour?", 60),
        ("Show alerts from the past 30 minutes.", 30),
        ("Review activity over the previous 2 days.", 2880),
    ],
)
def test_explicit_duration_is_deterministically_owned_by_server(question, expected_minutes):
    plan, errors = parse_and_validate_plan(
        json.dumps(_plan(requirements={"limit": 10})),
        _packet(question).payload,
    )

    assert errors == []
    assert plan.evidence_requirements["time_window_minutes"] == expected_minutes


def test_planner_prompt_defines_sort_semantics_without_accepting_aliases():
    gateway = SequenceGateway([json.dumps(_plan())])

    outcome = plan_turn(_packet(), gateway=gateway, config=_config())

    assert outcome.status == "planned"
    prompt = gateway.requests[0].prompt
    assert "sort MUST be exactly newest, oldest, or severity" in prompt
    assert "never output timestamp, asc, or desc" in prompt


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
    assert '"required_evidence":"array of strings"' in repair_prompt
    assert "Correct every reported schema and cross-field violation" in repair_prompt


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
    assert '"current_turn_intent":"must remain fresh_evidence_lookup"' in gateway.requests[1].prompt


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


def test_planner_prompt_prefers_authoritative_state_for_state_summary_intent():
    gateway = SequenceGateway([json.dumps(_plan(intent="state_summary", strategy="direct_answer", sufficiency="sufficient", tools=[], requirements={}))])
    packet = _packet("Summarize our current investigation.")

    outcome = plan_turn(packet, gateway=gateway, config=_config())

    assert outcome.status == "planned"
    assert "asks to summarize that state" in gateway.requests[0].prompt
    assert "use direct_answer with sufficient evidence" in gateway.requests[0].prompt


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
    value = _plan(strategy="direct_answer", sufficiency="sufficient", tools=[])
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
    value = _plan(
        intent=intent,
        strategy=strategy,
        sufficiency=sufficiency,
        tools=tools,
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


def test_repeated_controlled_plans_remain_contract_consistent():
    content = json.dumps(_plan())
    gateway = SequenceGateway([content] * 12)
    outcomes = [plan_turn(_packet(), gateway=gateway, config=_config()) for _ in range(12)]
    assert {outcome.plan.proposed_strategy for outcome in outcomes} == {"quick_evidence_lookup"}
    assert all(outcome.repaired is False for outcome in outcomes)
