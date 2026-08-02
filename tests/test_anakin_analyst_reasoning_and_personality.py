from __future__ import annotations

from core.ai.anakin_persona import (
    artifact_policy,
    banned_filler_phrases,
    base_persona_policy,
    classify_tone,
    deep_investigate_policy,
    decision_support_policy,
    filler_pattern_phrases,
    quick_explain_policy,
    repo_assistant_policy,
)
from core.ai.acceptance_harness import build_golden_reasoning_cases, evaluate_golden_reasoning_answer
from core.ai.config import AiGatewayConfig
from core.ai.context_builder import AiContextPayload, AiContextSource
from core.ai.draft_schemas import DraftRequest
from core.ai.drafting_service import _build_draft_prompt
from core.ai.explainer_service import _build_prompt as build_explainer_prompt
from core.ai.investigation_models import AiRoutingProfile
from core.ai.investigation_planner import InvestigationPlan
from core.ai.investigation_service import _build_correlation_prompt
from core.ai.repo_assistant_service import QUESTION_TYPE_EVALUATIVE, _build_prompt as build_repo_prompt
from core.ai.soc_briefing_investigation_engine import InvestigationBudget, _build_synthesis_prompt_payload
from core.ai.soc_tools import SocToolExecutionSummary
from core.ai.workflow_orchestrator import (
    WORKFLOW_DEEP_INVESTIGATE,
    WORKFLOW_DECISION_SUPPORT,
    WORKFLOW_QUICK_EXPLAIN,
    _is_recommendation_line,
    _normalize_recommendation_label,
    run_workflow,
    WorkflowValidationError,
)
from core.ai.profile_registry import AI_PROFILE_DEVELOPER_ASSISTANT, AI_PROFILE_FAST_TRIAGE, AI_PROFILE_GUIDED_ANALYSIS


def _context(context_type: str = "alert") -> AiContextPayload:
    return AiContextPayload(
        context_type=context_type,
        data={
            "alert": {"id": 7, "severity": "HIGH", "description": "Repeated failed logins"},
            "evidence": {"failed_logins": 84, "successful_logins": 0, "source_ip": "203.0.113.77"},
        },
        sources=[AiContextSource(source_type=context_type, source_path=f"{context_type}:7", record_ids=[7])],
    )


def _config() -> AiGatewayConfig:
    return AiGatewayConfig(mode="disabled", max_prompt_chars=14000)


def test_quick_explain_prompt_uses_persona_and_stays_concise_tool_free():
    prompt = build_explainer_prompt(
        _context(),
        action="explain",
        question="What matters?",
        tools=None,
        config=_config(),
    ).lower()

    assert "experienced detection engineer" in prompt
    assert "quick explain style" in prompt
    assert "2-6 concise sentences" in prompt
    assert "use only already-loaded bounded context" in prompt
    assert "at most one concrete next check" in prompt
    assert "do not repeat the alert description" in prompt
    assert "generic monitoring advice" in prompt
    assert "tiny style example" in prompt
    assert "bad: this alert indicates suspicious activity" in prompt
    assert "good: this looks more like noisy recon" in prompt
    assert "style examples for interactive answers" not in prompt
    assert "you are a read-only siem analyst assistant" not in prompt


def test_shared_persona_has_tone_adaptation_without_false_personality():
    policy = base_persona_policy().lower()

    assert "match the user's communication style" in policy
    assert "formal user -> professional" in policy
    assert "casual user -> natural" in policy
    assert "technical user -> technical" in policy
    assert "do not roleplay" in policy
    assert "not theater" in policy
    assert "never initiate profanity" in policy
    assert "almost never repeat profanity" in policy
    assert "do not make operational recommendations stronger than the evidence supports" in policy
    assert "do not use filler phrases like" in policy
    assert "do not answer by merely restating visible ui fields" in policy


def test_interactive_policies_include_natural_conversation_rules_and_examples():
    for policy in (deep_investigate_policy("professional"), decision_support_policy("technical"), repo_assistant_policy("technical")):
        lower = policy.lower()
        assert "answer immediately" in lower
        assert "every paragraph must add reasoning, evidence, uncertainty, or a concrete next step" in lower
        assert "never a generic disclaimer" in lower
        assert "style examples for interactive answers" in lower
        assert "do not copy conclusions" in lower

    quick = quick_explain_policy("casual").lower()
    assert "answer immediately" in quick
    assert "tiny style example" in quick
    assert "style examples for interactive answers" not in quick
    assert len(quick_explain_policy("casual")) <= 3400

    artifact = artifact_policy("casual").lower()
    assert "style examples for interactive answers" not in artifact
    assert "tone classification: professional" in artifact


def test_tone_classifier_is_deterministic_and_conservative():
    assert classify_tone("what's actually going on with this thing?") == "casual"
    assert classify_tone("Explain the Sigma correlation and auth failure pattern") == "technical"
    assert classify_tone("Please provide a concise assessment.") == "professional"
    assert classify_tone("draft this damn response", workflow="generate_artifact") == "professional"


def test_tone_instructions_are_specific_without_forcing_slang():
    casual = quick_explain_policy("casual").lower()
    technical = repo_assistant_policy("technical").lower()
    professional = decision_support_policy("professional").lower()

    assert "use contractions naturally" in casual
    assert "do not force slang" in casual
    assert "implementation-focused language" in technical
    assert "avoid unnecessary definitions" in technical
    assert "avoid corporate filler" in professional


def test_filler_phrases_are_canonical_and_rejected_by_acceptance():
    assert "based on the information provided" in banned_filler_phrases()
    case = build_golden_reasoning_cases()[0]

    checks = evaluate_golden_reasoning_answer(
        case,
        "Based on the information provided, severity is high, source IP is 203.0.113.77, timestamp is now, status is open.",
    )

    assert checks["no_filler_phrases"] is False
    assert checks["not_visible_field_only"] is False

    paraphrase_checks = evaluate_golden_reasoning_answer(
        case,
        "The alert is indicating suspicious behavior. Next step: inspect auth logs. Uncertainty: target outcome is missing.",
    )
    assert "the alert is indicating" in filler_pattern_phrases()
    assert "the alert indicates" in filler_pattern_phrases()
    assert paraphrase_checks["no_filler_phrases"] is False
    assert paraphrase_checks["no_robotic_preamble"] is False

    disclaimer_checks = evaluate_golden_reasoning_answer(
        case,
        "Most important: auth failures matter. Missing evidence: success outcome. Next step: inspect auth logs. Conclusions may change.",
    )
    assert disclaimer_checks["no_generic_disclaimer_ending"] is False

    low_value_checks = evaluate_golden_reasoning_answer(
        case,
        "Severity high. Alert title repeated failed logins. Source IP 203.0.113.77. Timestamp now. Status open.",
    )
    assert low_value_checks["paragraphs_add_value"] is False


def test_persona_keeps_professional_artifacts_and_conservative_profanity():
    base_policy = base_persona_policy().lower()
    artifact = artifact_policy().lower()

    assert "never initiate profanity" in base_policy
    assert "almost never repeat profanity" in base_policy
    assert "never use profanity, slang, or casual mirroring" in base_policy
    assert "reduce personality" in artifact
    assert "free of slang or profanity" in artifact


def test_decision_support_recommendation_strength_is_evidence_bounded():
    policy = decision_support_policy().lower()

    assert "put the recommendation first" in policy
    assert "what evidence would change the recommendation" in policy
    assert "more confidence than the evidence supports" in policy
    assert "never draft an artifact" in policy


def test_quick_explain_and_repo_assistant_are_short_by_default():
    quick = quick_explain_policy().lower()
    repo = repo_assistant_policy().lower()

    assert "quick explain style" in quick
    assert "2-6 concise sentences" in quick
    assert "concise by default" in repo
    assert "do not answer live siem-data questions from repository context" in repo


def test_recommendation_label_normalization_handles_markdown_without_false_match():
    assert _normalize_recommendation_label("**Recommendation:** monitor") == "recommendation: monitor"
    assert _normalize_recommendation_label("## Recommendation") == "recommendation"
    assert _normalize_recommendation_label("1. **Recommendation:** escalate") == "recommendation: escalate"

    for line in (
        "Recommendation: monitor",
        "**Recommendation:** monitor",
        "## Recommendation",
        "- **Recommendation:** escalate",
        "1. Recommendation: gather more evidence",
        "I wouldn't block this yet.",
    ):
        assert _is_recommendation_line(line)

    for line in (
        "Evidence recommendation source: model output",
        "Recommended evidence: auth logs",
        "Risk: recommendation depends on missing evidence",
    ):
        assert not _is_recommendation_line(line)


def test_deep_investigate_prompt_requires_skeptical_reasoning_contract():
    plan = InvestigationPlan(
        workflow_type="alert_investigation",
        context_type="alert",
        steps=("build_context", "correlate_evidence"),
        tool_calls=({"tool_name": "search_alerts", "args": {"source_ip": "203.0.113.77"}},),
        draft_policy={"allow_automatic_draft": False},
        bounds={"max_tool_calls": 5},
    )
    prompt = _build_correlation_prompt(
        plan=plan,
        question="Investigate this alert.",
        ai_context=_context(),
        tools=SocToolExecutionSummary(used=False),
        routing=AiRoutingProfile(profile="standard", inputs={}),
        config=_config(),
    ).lower()

    assert "deep investigate mode" in prompt
    assert "competing hypotheses" in prompt
    assert "supporting evidence" in prompt
    assert "contradictory or benign evidence" in prompt
    assert "evidence gaps" in prompt
    assert "confidence" in prompt
    assert "prioritized read-only next steps" in prompt
    assert "do not merely create a longer summary" in prompt
    assert "you are a read-only advanced siem soc assistant" not in prompt


def test_decision_support_prompt_is_recommendation_only_and_not_artifact_path(monkeypatch):
    captured = {}

    def fake_explain(payload, *, gateway=None, config=None):
        captured["payload"] = payload
        from core.ai.explainer_service import AiServiceResult

        return AiServiceResult(
            {
                "status": "success",
                "answer": "Assessment: weak evidence.\nRecommendation: I would monitor with a specific auth-log check.",
                "metadata": {"tone": "professional"},
                "context": {},
            },
            200,
        )

    monkeypatch.setattr("core.ai.workflow_orchestrator.explain_context", fake_explain)

    result = run_workflow(
        {
            "workflow": WORKFLOW_DECISION_SUPPORT,
            "prompt": "Should I block this?",
            "context_type": "alert",
            "context": {"alert_id": 7},
        },
        config=_config(),
    )

    assert result.payload["workflow"] == WORKFLOW_DECISION_SUPPORT
    assert "do not draft artifacts" in captured["payload"]["question"].lower()
    assert "first rendered content must be recommendation" in captured["payload"]["question"].lower()
    assert captured["payload"]["use_tools"] is False
    assert result.payload["result"]["answer"].startswith("Recommendation:")
    assert result.payload["metadata"]["decision_support_contract"] == "recommendation_first"
    assert result.payload["metadata"]["recommendation_first_enforced"] is True
    assert result.payload["result"]["decision_support"]["artifacts_generated"] is False

    try:
        run_workflow(
            {
                "workflow": WORKFLOW_DECISION_SUPPORT,
                "prompt": "Should I block this?",
                "context_type": "alert",
                "artifact": {"type": "incident_note"},
            },
            config=_config(),
        )
    except WorkflowValidationError as error:
        assert error.error_code == "decision_support_read_only"
    else:
        raise AssertionError("Decision Support accepted artifact generation")


def test_decision_support_reorders_markdown_recommendation_and_reports_metadata(monkeypatch):
    def fake_explain(payload, *, gateway=None, config=None):
        from core.ai.explainer_service import AiServiceResult

        return AiServiceResult(
            {
                "status": "success",
                "answer": (
                    "## Assessment\n"
                    "The evidence is weak.\n"
                    "- **Recommendation:** I wouldn't block this yet.\n"
                    "Risk: unnecessary disruption."
                ),
                "metadata": {"tone": "professional"},
                "context": {},
            },
            200,
        )

    monkeypatch.setattr("core.ai.workflow_orchestrator.explain_context", fake_explain)

    result = run_workflow(
        {
            "workflow": WORKFLOW_DECISION_SUPPORT,
            "prompt": "This is obviously a real attack. We should block it now, right?",
            "context_type": "alert",
            "context": {"alert_id": 7},
        },
        config=_config(),
    )

    answer = result.payload["result"]["answer"]
    assert answer.startswith("- **Recommendation:**")
    assert result.payload["metadata"]["recommendation_first_enforced"] is True


def test_decision_support_markdown_recommendation_first_reports_no_reorder(monkeypatch):
    def fake_explain(payload, *, gateway=None, config=None):
        from core.ai.explainer_service import AiServiceResult

        return AiServiceResult(
            {
                "status": "success",
                "answer": "**Recommendation:** monitor with a specific auth-log check.\nWhy: no successful auth is visible.",
                "metadata": {"tone": "professional"},
                "context": {},
            },
            200,
        )

    monkeypatch.setattr("core.ai.workflow_orchestrator.explain_context", fake_explain)

    result = run_workflow(
        {
            "workflow": WORKFLOW_DECISION_SUPPORT,
            "prompt": "Should I block this?",
            "context_type": "alert",
            "context": {"alert_id": 7},
        },
        config=_config(),
    )

    assert result.payload["result"]["answer"].startswith("**Recommendation:**")
    assert result.payload["metadata"]["recommendation_first_enforced"] is False


def test_generate_artifact_prompt_preserves_schema_and_demands_specific_evidence():
    prompt = _build_draft_prompt(
        DraftRequest(
            draft_type="investigation_checklist",
            instruction="Draft a checklist.",
            context_type="alert",
            context={"alert_id": 7},
            client_request_id="test-draft",
        ),
        _context(),
        SocToolExecutionSummary(used=False),
        config=_config(),
    ).lower()

    assert "generate artifact mode" in prompt
    assert "tone classification: professional" in prompt
    assert "free of slang or profanity" in prompt
    assert "evidence-specific review content" in prompt
    assert "return exactly one json object" in prompt
    assert "required json schema shape" in prompt
    assert "bounded repair" not in prompt
    assert "do not restate every visible field" in prompt
    assert "you are a read-only siem drafting assistant" not in prompt


def test_soc_briefing_prompt_prioritizes_handoff_over_inventory():
    payload = _build_synthesis_prompt_payload(
        selected=[],
        skipped=[{"reason": "commodity scanner noise"}],
        evidence_summary=SocToolExecutionSummary(used=False),
        evidence_refs=[],
        budget=InvestigationBudget(max_prompt_chars=8000, max_prompt_tokens=3000),
    )
    policy = payload["anakin_persona_policy"].lower()

    assert "soc briefing mode" in policy
    assert "tone classification: professional" in policy
    assert "concise analyst handoff" in policy
    assert "what can probably be ignored" in policy
    assert payload["policy"]["avoid_raw_alert_inventory"] is True
    assert payload["policy"]["call_out_low_value_noise"] is True


def test_repo_assistant_prompt_distinguishes_fact_from_judgment():
    prompt = build_repo_prompt(
        "What is my most impressive feature?",
        history=[],
        chunks=[],
        max_prompt_chars=12000,
        question_type=QUESTION_TYPE_EVALUATIVE,
    ).lower()

    assert "read-only repository architecture assistant" in prompt
    assert "tone classification:" in prompt
    assert "distinguish repository facts from architectural judgment" in prompt
    assert "repository fact" in prompt
    assert "judgment" in prompt
    assert "do not claim to edit files" in prompt


def test_interactive_prompt_sizes_remain_inside_profile_limits():
    config = AiGatewayConfig(mode="disabled")
    quick_prompt = build_explainer_prompt(
        _context(),
        action="explain",
        question="hey, what's up with this alert, anything I should actually worry about or is it just noise?",
        tools=None,
        config=config,
        tone="casual",
    )
    decision_prompt = build_explainer_prompt(
        _context(),
        action="recommend_next_steps",
        question="This is obviously a real attack. We should block it now, right?",
        tools=None,
        config=config,
        tone="professional",
    )
    deep_prompt = _build_correlation_prompt(
        plan=InvestigationPlan(
            workflow_type="alert_investigation",
            context_type="alert",
            steps=("build_context", "correlate_evidence"),
            tool_calls=({"tool_name": "search_alerts", "args": {"source_ip": "203.0.113.77"}},),
            draft_policy={"allow_automatic_draft": False},
            bounds={"max_tool_calls": 5},
        ),
        question="Please assess whether this alert should be escalated.",
        ai_context=_context(),
        tools=SocToolExecutionSummary(used=False),
        routing=AiRoutingProfile(profile="standard", inputs={}),
        config=config,
        tone="professional",
    )
    repo_prompt = build_repo_prompt(
        "Where does the async Repo Assistant worker dispatch happen?",
        history=[],
        chunks=[],
        max_prompt_chars=config.profile(AI_PROFILE_DEVELOPER_ASSISTANT).max_prompt_chars,
        question_type=QUESTION_TYPE_EVALUATIVE,
        tone="technical",
    )

    assert len(quick_prompt) < config.profile(AI_PROFILE_FAST_TRIAGE).max_prompt_chars
    assert len(decision_prompt) < config.profile(AI_PROFILE_GUIDED_ANALYSIS).max_prompt_chars
    assert len(deep_prompt) < config.profile(AI_PROFILE_GUIDED_ANALYSIS).max_prompt_chars
    assert len(repo_prompt) < config.profile(AI_PROFILE_DEVELOPER_ASSISTANT).max_prompt_chars


def test_golden_reasoning_acceptance_cases_check_properties_not_exact_words():
    cases = build_golden_reasoning_cases()

    assert {case.scenario for case in cases} == {
        "casual user asks what is going on",
        "professional user requests assessment",
        "casual frustrated analyst used profanity",
        "shareable artifact stays professional",
        "analyst assumes block is required but evidence is weak",
        "likely password spray with no successful login",
        "noisy commodity recon that may not deserve escalation",
        "high-severity alert with weak follow-up evidence",
        "casual alert noise question from production",
        "casual profanity IP reputation question from production",
        "production unsupported block assumption",
        "incident with supporting and contradicting evidence",
        "graph spike dominated by one source",
        "decision between monitor, escalate, or block",
        "SOC briefing with low-value noise and one important trend",
        "What is my most impressive feature?",
        "technical Repo Assistant question",
        "professional SOC analyst question",
    }
    for case in cases:
        checks = evaluate_golden_reasoning_answer(case, case.expected_answer)
        assert all(checks.values()), (case.key, checks)
