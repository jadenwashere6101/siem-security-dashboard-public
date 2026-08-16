from __future__ import annotations

import json
import inspect
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import ANY, MagicMock, patch

import pytest

from core.ai.config import AiGatewayConfig
from core.ai.models import (
    AI_STATUS_PROVIDER_UNAVAILABLE,
    AI_STATUS_SUCCESS,
    AiGatewayResponse,
    AiRequestMetadata,
)
from core.nist_evidence_explanation import (
    EXPLANATION_LOOKAHEAD_LIMIT,
    EXPLANATION_REFERENCE_LIMIT,
    NistExplanationBindingError,
    NistExplanationValidationError,
    NistExplanationServiceResult,
    execute_explanation,
    enqueue_explanation,
    load_explanation_context,
    resolve_explanation_binding,
    validate_explanation_output,
    validate_explanation_request,
)
from core.ai.workflow_request_store import create_or_get_request, get_request
from core.ai.workflow_request_worker import AnakinWorkflowWorkerConfig, run_anakin_workflow_worker
from core.nist_evidence_store import create_boundary, create_run_record, list_boundary_runs
import core.nist_evidence_explanation as explanation_module


REQUEST = {
    "boundary_id": 7,
    "run_id": 11,
    "requirement_result_id": 20,
    "requirement_id": "03.03.01",
    "client_request_id": "55f5fa58-9dc3-4dda-b880-d950bcf56c62",
}


def test_postgres_run_history_is_descending_bounded_and_keyset_resumable(postgres_db):
    conn, cur = postgres_db
    boundary = create_boundary(
        conn,
        {
            "name": "Run history contract",
            "selected_sources": ["pfsense"],
            "environments": ["prod"],
            "default_window_hours": 24,
        },
        actor_username="admin",
    )
    base = datetime(2026, 8, 12, 10, 0, tzinfo=timezone.utc)
    run_ids = []
    for index in range(3):
        run_id = create_run_record(
            conn,
            boundary_id=boundary["id"],
            framework_id="nist_sp_800_171",
            framework_version="rev3",
            window_start=base - timedelta(hours=1),
            window_end=base,
            source_health_snapshot={},
            actor_username="admin",
        )
        created_at = base + timedelta(minutes=index)
        cur.execute(
            "UPDATE nist_assessment_runs SET created_at = %s WHERE id = %s",
            (created_at, run_id),
        )
        run_ids.append(run_id)
    conn.commit()

    first = list_boundary_runs(conn, boundary["id"], limit=2)
    second = list_boundary_runs(
        conn,
        boundary["id"],
        limit=2,
        before_created_at=datetime.fromisoformat(first["next_cursor"]["before_created_at"]),
        before_id=first["next_cursor"]["before_id"],
    )

    assert [item["id"] for item in first["items"]] == run_ids[::-1][:2]
    assert first["next_cursor"]["before_id"] == run_ids[1]
    assert [item["id"] for item in second["items"]] == [run_ids[0]]
    assert second["next_cursor"] is None


def test_postgres_explanation_reads_persisted_package_without_mutating_result(postgres_db):
    conn, cur = postgres_db
    boundary = create_boundary(
        conn,
        {"name": "Immutable explanation", "selected_sources": ["pfsense"]},
        actor_username="admin",
    )
    end = datetime(2026, 8, 12, 10, 0, tzinfo=timezone.utc)
    run_id = create_run_record(
        conn,
        boundary_id=boundary["id"],
        framework_id="nist_sp_800_171",
        framework_version="rev3",
        window_start=end - timedelta(hours=1),
        window_end=end,
        source_health_snapshot={},
        actor_username="admin",
    )
    cur.execute(
        """
        INSERT INTO nist_requirement_results (
            run_id, requirement_id, requirement_name, mapping_strength,
            evidence_status, collection_confidence, reason_code, limitation,
            evidence_count, omitted_count, evaluated_at, catalog_version,
            catalog_hash, collector_version
        ) VALUES (
            %s, '03.03.01', 'Event Logging', 'partial_siem_evidence',
            'partial_evidence', 'healthy', 'partial_collection',
            'Only mapped SIEM-visible evidence is represented.',
            1, 0, %s, 'v1', %s, 'v1'
        ) RETURNING id
        """,
        (run_id, end, "a" * 64),
    )
    result_id = cur.fetchone()[0]
    cur.execute(
        """
        INSERT INTO nist_evidence_references (
            run_id, requirement_result_id, requirement_id, evidence_category,
            evidence_type, canonical_source, source_type, source_health_state,
            entity_type, entity_id, occurrence_timestamp, ingestion_timestamp,
            collection_timestamp, query_window_start, query_window_end, query_hash,
            operational_classification, catalog_version, mapping_version,
            collector_version, evidence_summary
        ) VALUES (
            %s, %s, '03.03.01', 'alerts', 'threshold_alert', 'pfsense',
            'firewall', 'healthy', 'alert', '501', %s, %s, %s, %s, %s, %s,
            'real', 'v1', 'v1', 'v1', 'Bounded persisted alert reference.'
        ) RETURNING id
        """,
        (run_id, result_id, end, end, end, end - timedelta(hours=1), end, "b" * 64),
    )
    reference_id = cur.fetchone()[0]
    conn.commit()
    request = {
        "boundary_id": boundary["id"],
        "run_id": run_id,
        "requirement_result_id": result_id,
        "requirement_id": "03.03.01",
        "client_request_id": "99d177b0-f4f9-4dac-b052-5cb27a0d349d",
    }
    first_queue, first_created = enqueue_explanation(
        conn, request, actor_username="analyst", actor_role="analyst"
    )
    second_queue, second_created = enqueue_explanation(
        conn, request, actor_username="analyst", actor_role="analyst"
    )
    assert first_created is True
    assert second_created is False
    assert first_queue["request_id"] == second_queue["request_id"]
    cur.execute("SELECT to_jsonb(rr) FROM nist_requirement_results rr WHERE id = %s", (result_id,))
    before = cur.fetchone()[0]
    gateway = SimpleNamespace(generate=MagicMock(return_value=AiGatewayResponse(
        status=AI_STATUS_SUCCESS,
        content=_model_output(
            summary=(
                f"The persisted record shows SIEM-visible logging evidence "
                f"[{reference_id}]."
            ),
            why_it_matters=(
                f"Reference {reference_id} supports the deterministic evidence package."
            ),
            citation_ids=[reference_id],
        ),
        metadata=_metadata(AI_STATUS_SUCCESS),
    )))

    with patch("core.nist_evidence_explanation.log_audit_event"):
        response = execute_explanation(
            conn,
            request,
            actor_username="analyst",
            actor_role="analyst",
            request_id="aiwf_immutable",
            gateway=gateway,
            config=AiGatewayConfig(),
        )
    cur.execute("SELECT to_jsonb(rr) FROM nist_requirement_results rr WHERE id = %s", (result_id,))
    after = cur.fetchone()[0]

    assert response.payload["status"] == "success"
    assert before == after
    assert response.payload["result"]["deterministic_result"]["evidence_status"] == "partial_evidence"


def _result(**overrides):
    result = {
        "id": 20,
        "run_id": 11,
        "requirement_id": "03.03.01",
        "requirement_name": "Event Logging",
        "mapping_strength": "partial_siem_evidence",
        "evidence_status": "partial_evidence",
        "collection_confidence": "healthy",
        "reason_code": "partial_collection",
        "limitation": "Only mapped SIEM-visible evidence is represented.",
        "evidence_count": 30,
        "omitted_count": 0,
        "evaluated_at": "2026-08-12T10:00:00+00:00",
        "catalog_version": "v1",
        "catalog_hash": "a" * 64,
        "collector_version": "v1",
    }
    result.update(overrides)
    return result


def _binding(result=None):
    return {
        "boundary_id": 7,
        "run": {
            "id": 11,
            "boundary_id": 7,
            "framework_id": "nist_sp_800_171",
            "framework_version": "rev3",
            "catalog_version": "v1",
            "catalog_hash": "a" * 64,
            "collector_version": "v1",
        },
        "result": result or _result(),
    }


def _reference(reference_id, **overrides):
    reference = {
        "id": reference_id,
        "evidence_category": "event_types",
        "evidence_type": "normalized_event",
        "canonical_source": "pfsense",
        "source_type": "firewall",
        "source_health_state": "healthy",
        "entity_type": "alert",
        "entity_id": str(1000 + reference_id),
        "occurrence_timestamp": "2026-08-12T09:30:00+00:00",
        "ingestion_timestamp": "2026-08-12T09:30:01+00:00",
        "collection_timestamp": "2026-08-12T10:00:00+00:00",
        "operational_classification": "real",
        "is_truncated": False,
        "omitted_count": 0,
        "evidence_summary": f"Persisted reference {reference_id}",
    }
    reference.update(overrides)
    return reference


def _context(*, confidence="healthy", truncated=False, classification="real"):
    refs = [_reference(31, operational_classification=classification)]
    return {
        "binding": {
            "boundary_id": 7,
            "run_id": 11,
            "requirement_result_id": 20,
            "requirement_id": "03.03.01",
        },
        "framework": {
            "id": "nist_sp_800_171",
            "version": "rev3",
            "catalog_version": "v1",
            "catalog_hash": "a" * 64,
            "collector_version": "v1",
        },
        "deterministic_result": _result(collection_confidence=confidence),
        "evidence": {
            "total_count": 31 if truncated else 1,
            "supplied_count": 1,
            "context_omitted_count": 30 if truncated else 0,
            "collector_omitted_count": 0,
            "omitted_count": 30 if truncated else 0,
            "truncated": truncated,
            "references": refs,
        },
    }


def _model_output(**overrides):
    output = {
        "summary": "The persisted records show SIEM-visible logging evidence [31].",
        "why_it_matters": "Reference 31 supports the deterministic evidence package.",
        "limitations": "Only the bounded persisted records supplied by the server are described.",
        "additional_evidence_needed": ["Review non-SIEM evidence outside this workspace."],
        "citation_ids": [31],
    }
    output.update(overrides)
    return json.dumps(output)


def _metadata(status, *, error_code=None):
    return AiRequestMetadata(
        provider="ollama",
        model="llama3.2:3b",
        mode="local_only",
        status=status,
        profile="fast_triage",
        latency_ms=12,
        estimated_prompt_tokens=100,
        estimated_completion_tokens=40,
        error_code=error_code,
        local_request=True,
    )


def test_request_contract_accepts_exact_ids_only_and_rejects_frontend_facts():
    assert validate_explanation_request(REQUEST) == REQUEST
    with pytest.raises(NistExplanationValidationError, match="unsupported request fields"):
        validate_explanation_request({**REQUEST, "evidence_status": "evidence_available"})
    with pytest.raises(NistExplanationValidationError, match="missing request fields"):
        validate_explanation_request({key: value for key, value in REQUEST.items() if key != "run_id"})


def test_explanation_runtime_has_no_events_source_health_collector_or_planner_fallback():
    source = inspect.getsource(explanation_module).lower()
    for forbidden in (
        "from events",
        "join events",
        "aggregate_source_health",
        "execute_assessment_run",
        "run_workflow",
        "prepare_worker_conversation",
        "execute_soc_tool",
    ):
        assert forbidden not in source


def test_existing_fast_triage_profile_is_local_only_without_paid_fallback():
    profile = AiGatewayConfig().profile("fast_triage")
    assert profile.name == "fast_triage"
    assert profile.provider == "ollama"
    assert profile.model == "llama3.2:3b"
    assert profile.local_only is True
    assert profile.paid_fallback_enabled is False
    assert profile.local_fallback_profile is None


def test_four_id_binding_uses_one_authoritative_lookup_and_rejects_mismatch():
    conn = MagicMock()
    with patch(
        "core.nist_evidence_explanation.get_bound_requirement_result",
        return_value=_binding(),
    ) as lookup:
        assert resolve_explanation_binding(conn, REQUEST)["result"]["id"] == 20
    lookup.assert_called_once_with(
        conn,
        boundary_id=7,
        run_id=11,
        requirement_result_id=20,
        requirement_id="03.03.01",
    )
    with patch(
        "core.nist_evidence_explanation.get_bound_requirement_result", return_value=None
    ), pytest.raises(NistExplanationBindingError):
        resolve_explanation_binding(conn, {**REQUEST, "run_id": 99})


def test_context_uses_only_bound_persisted_references_and_caps_with_lookahead():
    references = [_reference(index) for index in range(1, EXPLANATION_LOOKAHEAD_LIMIT + 1)]
    with patch(
        "core.nist_evidence_explanation.get_bound_requirement_result",
        return_value=_binding(),
    ), patch(
        "core.nist_evidence_explanation.list_bound_evidence_references",
        return_value={"items": references, "total": 100},
    ) as reference_lookup:
        context = load_explanation_context(MagicMock(), REQUEST)
    assert len(context["evidence"]["references"]) == EXPLANATION_REFERENCE_LIMIT
    assert context["evidence"]["total_count"] == 100
    assert context["evidence"]["supplied_count"] == 25
    assert context["evidence"]["context_omitted_count"] == 75
    assert context["evidence"]["collector_omitted_count"] == 0
    assert context["evidence"]["omitted_count"] == 75
    assert context["evidence"]["truncated"] is True
    reference_lookup.assert_called_once_with(
        ANY,
        run_id=11,
        requirement_result_id=20,
        requirement_id="03.03.01",
        limit=EXPLANATION_LOOKAHEAD_LIMIT,
    )


@pytest.mark.parametrize(
    ("content", "context", "error_code"),
    [
        ("not json", _context(), "malformed_model_output"),
        (_model_output(citation_ids=[999]), _context(), "unbound_citation"),
        (_model_output(summary="This requirement is compliant."), _context(), "compliance_overclaim"),
        (_model_output(summary="This evidence satisfies the requirement."), _context(), "compliance_overclaim"),
        (_model_output(summary="Collection healthy."), _context(confidence="degraded"), "deterministic_state_contradiction"),
        (_model_output(limitations="Only the provided records are described."), _context(truncated=True), "truncation_not_preserved"),
        (_model_output(summary="All evidence is real operational execution."), _context(classification="synthetic"), "operational_classification_overclaim"),
        (_model_output(summary="Alert ID 999999 proves logging activity."), _context(), "introduced_identifier"),
        (_model_output(summary="Reference 999 proves logging activity."), _context(), "introduced_identifier"),
        (_model_output(summary="A different record [999] proves logging activity."), _context(), "introduced_identifier"),
    ],
)
def test_grounded_output_validation_fails_closed(content, context, error_code):
    explanation, actual_error = validate_explanation_output(content, context)
    assert explanation is None
    assert actual_error == error_code


def test_valid_grounded_output_preserves_bounded_citations():
    explanation, error = validate_explanation_output(_model_output(), _context())
    assert error is None
    assert explanation["citation_ids"] == [31]
    assert set(explanation) == {
        "summary", "why_it_matters", "limitations", "additional_evidence_needed", "citation_ids",
    }


def test_provider_unavailable_returns_only_server_owned_result_and_safe_metadata():
    gateway = SimpleNamespace(generate=MagicMock(return_value=AiGatewayResponse(
        status=AI_STATUS_PROVIDER_UNAVAILABLE,
        content=None,
        metadata=_metadata(AI_STATUS_PROVIDER_UNAVAILABLE, error_code="provider_unavailable"),
        error="offline",
    )))
    with patch(
        "core.nist_evidence_explanation.load_explanation_context", return_value=_context()
    ), patch("core.nist_evidence_explanation.log_audit_event") as audit_mock:
        response = execute_explanation(
            MagicMock(), REQUEST, actor_username="analyst", actor_role="analyst",
            request_id="aiwf_test", gateway=gateway, config=AiGatewayConfig(),
        )
    assert response.payload["status"] == "explanation_unavailable"
    assert response.payload["result"]["deterministic_result"] == _context()["deterministic_result"]
    assert response.payload["result"]["explanation"] is None
    gateway.generate.assert_called_once()
    request = gateway.generate.call_args.args[0]
    assert request.profile == "fast_triage"
    assert request.capability == "text_generation"
    assert request.metadata["read_only"] is True
    logged_details = audit_mock.call_args.kwargs["details"]
    assert "prompt" not in logged_details
    assert "raw_model_prose" not in logged_details
    assert "persisted reference" not in json.dumps(logged_details).lower()


def test_worker_side_binding_rejection_fails_without_provider_call():
    gateway = SimpleNamespace(generate=MagicMock())
    with patch(
        "core.nist_evidence_explanation.load_explanation_context",
        side_effect=NistExplanationBindingError("not found"),
    ), patch("core.nist_evidence_explanation.log_audit_event") as audit_mock:
        response = execute_explanation(
            MagicMock(), REQUEST, actor_username="analyst", actor_role="analyst",
            request_id="aiwf_bad_binding", gateway=gateway, config=AiGatewayConfig(),
        )
    assert response.status_code == 404
    assert response.payload["status"] == "failed"
    assert response.payload["error_code"] == "binding_invalid"
    gateway.generate.assert_not_called()
    assert audit_mock.call_args.args[0] == "NIST_EVIDENCE_EXPLANATION_BINDING_REJECTED"


def test_successful_execution_keeps_deterministic_block_separate_from_model_prose():
    gateway = SimpleNamespace(generate=MagicMock(return_value=AiGatewayResponse(
        status=AI_STATUS_SUCCESS,
        content=_model_output(),
        metadata=_metadata(AI_STATUS_SUCCESS),
    )))
    with patch(
        "core.nist_evidence_explanation.load_explanation_context", return_value=_context()
    ), patch("core.nist_evidence_explanation.log_audit_event"):
        response = execute_explanation(
            MagicMock(), REQUEST, actor_username="analyst", actor_role="analyst",
            request_id="aiwf_test", gateway=gateway, config=AiGatewayConfig(),
        )
    result = response.payload["result"]
    assert result["deterministic_result"]["evidence_status"] == "partial_evidence"
    assert "evidence_status" not in result["explanation"]
    assert result["explanation_status"] == "available"


def test_worker_dispatch_is_isolated_from_planner_session_memory_and_tools(
    client, postgres_db, monkeypatch
):
    conn, _cur = postgres_db
    row, _created = create_or_get_request(
        conn,
        workflow="nist_evidence_explanation",
        context_type="nist_evidence_result",
        payload=REQUEST,
        classification={"classified_workflow": "nist_evidence_explanation"},
        actor_username="analyst",
        actor_role="analyst",
    )
    conn.commit()

    class NoCloseConnection:
        def __init__(self, wrapped):
            self.wrapped = wrapped

        def __getattr__(self, name):
            return getattr(self.wrapped, name)

        def close(self):
            return None

    isolated = MagicMock(return_value=NistExplanationServiceResult({
        "status": "success",
        "workflow": "nist_evidence_explanation",
        "result": {
            "deterministic_result": _result(),
            "explanation_status": "available",
            "explanation": json.loads(_model_output()),
        },
        "metadata": {"provider": "ollama", "profile": "fast_triage"},
    }))
    monkeypatch.setattr("core.ai.workflow_request_worker.execute_explanation", isolated)
    monkeypatch.setattr(
        "core.ai.workflow_request_worker.prepare_worker_conversation",
        MagicMock(side_effect=AssertionError("session memory must not be used")),
    )
    monkeypatch.setattr(
        "core.ai.workflow_request_worker.complete_worker_conversation",
        MagicMock(side_effect=AssertionError("session memory must not be used")),
    )
    monkeypatch.setattr(
        "core.ai.workflow_request_worker.run_workflow",
        MagicMock(side_effect=AssertionError("planner/orchestrator must not be used")),
    )
    monkeypatch.setattr(
        "core.ai.workflow_request_worker.answer_repo_question",
        MagicMock(side_effect=AssertionError("SOC/repository tools must not be used")),
    )

    worker_conn = NoCloseConnection(conn)
    stats = run_anakin_workflow_worker(
        config=AnakinWorkflowWorkerConfig(batch_size=1, max_runtime_seconds=30),
        worker_id="nist-isolation-test",
        connect=lambda: worker_conn,
        flask_app=client.application,
    )
    persisted = get_request(conn, row["request_id"], actor_username="analyst")

    assert stats["success"] == 1
    assert persisted["status"] == "completed"
    isolated.assert_called_once()
    assert isolated.call_args.args[0] is worker_conn
    assert isolated.call_args.args[1] == REQUEST
