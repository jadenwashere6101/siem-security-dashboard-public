from __future__ import annotations

import json
from pathlib import Path
import subprocess
from unittest.mock import patch

from werkzeug.security import generate_password_hash

from core.ai.session_memory_store import MAX_JSON_DEPTH, create_thread, get_thread, list_turns
from core.ai.workflow_orchestrator import WorkflowResult
from core.ai.models import AI_STATUS_SUCCESS, AiGatewayResponse, AiRequestMetadata


REPO_ROOT = Path(__file__).resolve().parent.parent


class NoCloseConnection:
    def __init__(self, conn):
        self._conn = conn

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def close(self):
        return None


class ProductionShapePlannerGateway:
    def __init__(self, **_kwargs):
        pass

    def generate(self, request):
        packet = json.loads(request.prompt.split("SERVER_PACKET=", 1)[1])
        hint = packet.get("preferred_capability_hint")
        capability = hint or "quick_explain"
        strategy = {
            "quick_explain": "quick_evidence_lookup",
            "deep_investigate": "bounded_investigation",
            "decision_support": "decision_support",
            "generate_artifact": "artifact_draft",
        }[capability]
        plan = {
            "current_turn_intent": "Handle the current production-shaped SIEM request.",
            "evidence_sufficiency": "insufficient",
            "required_evidence": ["current bounded SIEM evidence"],
            "proposed_strategy": strategy,
            "proposed_tool_categories": ["alerts"] if strategy == "quick_evidence_lookup" else [],
            "evidence_requirements": (
                {"severity": "high", "sort": "newest", "limit": 1}
                if strategy == "quick_evidence_lookup"
                else {}
            ),
            "clarification_question": None,
            "reasoning_summary": "The current request requires the selected bounded SIEM capability.",
            "stopping_condition": "Stop after the selected read-only capability returns a bounded result.",
            "confidence": "high",
        }
        return AiGatewayResponse(
            status=AI_STATUS_SUCCESS,
            content=json.dumps(plan),
            error=None,
            metadata=AiRequestMetadata(
                provider="controlled-local",
                model="planner-test",
                mode="local_only",
                status=AI_STATUS_SUCCESS,
                local_request=True,
                paid_request=False,
            ),
        )


def _depth(value):
    if isinstance(value, dict):
        return 1 + max((_depth(item) for item in value.values()), default=0)
    if isinstance(value, list):
        return 1 + max((_depth(item) for item in value), default=0)
    return 0


def _frontend_production_payloads(ids: dict[str, int]) -> list[dict]:
    script = r"""
const babel = require('@babel/core');
const Module = require('module');
const path = require('path');
function load(relative) {
  const filename = path.resolve(relative);
  const code = babel.transformFileSync(filename, { presets: ['@babel/preset-env'] }).code;
  const loaded = new Module(filename, module);
  loaded.filename = filename;
  loaded.paths = module.paths;
  loaded._compile(code, filename);
  return loaded.exports;
}
const command = load('src/utils/anakinCommandRegistry.js');
const conversation = load('src/utils/anakinConversationRequest.js');
const ids = JSON.parse(process.argv[1]);
const rich = {
  threatBrief: {
    sections: [{
      title: 'Network activity',
      items: [{
        alert: {
          id: ids.alert,
          source: { ip: '203.0.113.81', metadata: { provider: 'pfsense', labels: ['scan'] } },
        },
      }],
    }],
  },
};
const visible = {
  active_section: 'dashboard',
  dashboard_summary: { totalAlerts: 37, highCount: 4, uniqueIPs: 8 },
  timeline: [{ bucket: '2026-08-02T12:00:00Z', count: 7 }],
  recent_alerts: [{ alert_id: ids.alert, source_ip: '203.0.113.81' }],
  ...rich,
};
const commandContext = command.buildCommandContext({
  activeSection: 'dashboard',
  alertView: { operationalScope: 'since_tuning' },
  selectedAlertId: ids.alert,
  alerts: [{ id: ids.alert, alert_type: 'port_scan', source_ip: '203.0.113.81' }],
  metrics: { totalAlerts: 37 },
  currentUsername: 'production_payload_analyst',
  userRole: 'analyst',
  canTakeAlertActions: true,
  threatBrief: rich.threatBrief,
});
const explain = command.createDefaultAnakinCommands().find((item) => item.workflow === 'quick_explain');
const cases = [
  ['Dashboard Ask Anakin', { workflow: 'auto', contextType: 'dashboard', context: { command_context: commandContext }, question: 'Explain the current dashboard activity.' }],
  ['Dashboard Explain this alert', command.commandToAiOptions(explain, commandContext, 'Explain the selected alert.')],
  ['Alert Details', { workflow: 'quick_explain', contextType: 'alert', context: { alert_id: ids.alert, alert: rich }, question: 'Explain this alert.' }],
  ['Source IP', { workflow: 'quick_explain', contextType: 'source_ip', context: { source_ip: '203.0.113.81', events: rich }, question: 'Explain this source IP.' }],
  ['Incident', { workflow: 'decision_support', contextType: 'incident', context: { incident_id: ids.incident, incident: rich }, question: 'Recommend the next action.' }],
  ['SOC Command Center / Recon', { workflow: 'deep_investigate', contextType: 'recon_activity', context: { activity_id: ids.recon, activity: rich }, question: 'Investigate this recon activity.' }],
  ['Response Registry', { workflow: 'decision_support', contextType: 'response_registry', context: { registry_id: ids.registry, response: rich }, question: 'Recommend the next action.' }],
  ['Analyst Workspace', { workflow: 'auto', contextType: 'general', context: { investigation_id: ids.investigation, workspace: rich }, question: 'Explain the current investigation.' }],
  ['Generate Artifact preview', { workflow: 'generate_artifact', contextType: 'alert', context: { alert_id: ids.alert, alert: rich }, question: 'Draft an investigation checklist.', artifactType: 'investigation_checklist' }],
];
const output = cases.map(([label, options], index) => {
  const contextualCommand = command.normalizeContextualAiOptions(options);
  const built = conversation.buildAnakinWorkflowSubmission({
    options,
    activeSection: options.contextType || 'dashboard',
    visibleContext: visible,
    contextualCommand,
    conversation: { thread_id: 'replace', expected_version: 1, client_request_id: `production-${index}` },
    clientRequestId: `production-${index}`,
  });
  return { label, ...built };
});
process.stdout.write(JSON.stringify(output));
"""
    result = subprocess.run(
        ["node", "-e", script, json.dumps(ids)],
        cwd=REPO_ROOT / "frontend",
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def _seed_targets(conn):
    owner = "production_payload_analyst"
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO users (username, password_hash, role, is_active)
            VALUES (%s, 'hash', 'analyst', TRUE)
            ON CONFLICT (username) DO UPDATE SET role = 'analyst', is_active = TRUE
            """,
            (owner,),
        )
        cur.execute(
            """
            INSERT INTO alerts (alert_type, severity, source_ip, source, message, status)
            VALUES ('port_scan', 'HIGH', '203.0.113.81'::inet, 'pfsense', 'production-shaped alert', 'open')
            RETURNING id
            """
        )
        alert = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO incidents (title, severity, priority, status, source_ip)
            VALUES ('Production payload incident', 'high', 'P2', 'open', '203.0.113.81'::inet)
            RETURNING id
            """
        )
        incident = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO recon_activities (
                activity_type, source, source_type, status, severity, coordination_status,
                protected_range_key, service_signature, first_seen, last_seen,
                assessment_text, membership_evidence, summary
            ) VALUES (
                'distributed_internet_reconnaissance', 'pfsense', 'firewall', 'open', 'medium',
                'not_established', 'test-range', '[]'::jsonb, NOW(), NOW(),
                'Production payload recon', '{}'::jsonb, '{}'::jsonb
            ) RETURNING id
            """
        )
        recon = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO indicator_registry (indicator_type, indicator_value, current_disposition)
            VALUES ('ip', '203.0.113.81', 'observed')
            RETURNING id
            """
        )
        registry = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO investigations (owner_username, title, linked_alert_id)
            VALUES (%s, 'Production payload workspace', %s)
            RETURNING id
            """,
            (owner, alert),
        )
        investigation = cur.fetchone()[0]
    conn.commit()
    return owner, {
        "alert": alert,
        "incident": incident,
        "recon": recon,
        "registry": registry,
        "investigation": investigation,
    }


def _fake_user(username):
    return {
        "username": username,
        "password_hash": generate_password_hash("pass", method="pbkdf2:sha256"),
        "role": "analyst",
        "is_active": True,
    }


def _quick_result(payload, **_kwargs):
    entity = payload["entity"]
    return WorkflowResult(
        {
            "status": "success",
            "workflow": "quick_explain",
            "classification": {"classified_workflow": "quick_explain"},
            "result": {"status": "success", "answer": f"Reviewed {entity['type']} {entity['id']}."},
            "metadata": {"profile": "fast_triage"},
            "error": None,
        }
    )


def test_production_frontend_payloads_cross_real_conversation_routes(client, postgres_db):
    conn, _cur = postgres_db
    owner, ids = _seed_targets(conn)
    generated = _frontend_production_payloads(ids)
    wrapper = NoCloseConnection(conn)
    user = _fake_user(owner)
    captured_execution = []

    def fake_run(payload, **kwargs):
        captured_execution.append(payload)
        return _quick_result(payload, **kwargs)

    with patch("routes.auth_routes.get_user_by_username", return_value=user), patch(
        "core.auth.get_user_by_username", return_value=user
    ), patch("core.ai.conversation_orchestration_service.get_db_connection", return_value=wrapper), patch(
        "core.ai.session_memory_service.get_db_connection", return_value=wrapper
        ), patch("core.ai.conversation_orchestration_service.run_workflow", side_effect=fake_run), patch(
            "core.audit_helpers.get_db_connection", return_value=wrapper
        ), patch("core.ai.agentic_analyst_planner.AiGateway", ProductionShapePlannerGateway
        ), patch("routes.ai_routes.log_audit_event", return_value=None
    ):
        assert client.post("/login", json={"username": owner, "password": "pass"}).status_code == 200
        for item in generated:
            payload = item["payload"]
            entity = payload["entity"]
            thread, _created = create_thread(
                conn,
                owner_username=owner,
                primary_entity_type=entity["type"],
                primary_entity_id=entity["id"],
                scope_key=f"entity:{entity['type']}:{entity['id']}",
                is_default=True,
            )
            conn.commit()
            payload["conversation"] = {
                "thread_id": thread["thread_id"],
                "expected_version": thread["version"],
                "client_request_id": payload["client_request_id"],
            }
            endpoint = "/ai/workflows" if payload["workflow"] == "quick_explain" else "/ai/workflows/requests"
            response = client.post(endpoint, json=payload)
            assert response.status_code in {200, 202}, (item["label"], response.get_json())

            turns = list_turns(conn, thread_id=thread["thread_id"], owner_username=owner)["turns"]
            assert turns, item["label"]
            submitted = next(
                turn for turn in turns if turn["client_request_id"] == payload["client_request_id"]
            )
            stored = submitted["structured_payload"]
            assert _depth(stored) <= MAX_JSON_DEPTH
            assert stored["resolved_execution_context"]["active_entity"] == entity
            rendered = json.dumps(stored, sort_keys=True)
            assert "threatBrief" not in rendered
            assert "workspace" not in rendered
            if item["label"] == "Generate Artifact preview":
                assert stored["artifact_safety"] == {
                    "artifact_type": "investigation_checklist",
                    "preview_only": True,
                    "persisted": False,
                    "applied": False,
                    "approval_required": True,
                }

        dashboard_candidates = [
            payload
            for payload in captured_execution
            if payload["entity"].get("type") == "dashboard" and payload["entity"].get("id") == "dashboard"
        ]
        assert dashboard_candidates, [payload.get("entity") for payload in captured_execution]
        dashboard_execution = dashboard_candidates[0]
        assert dashboard_execution["context"]["command_context"]["data"]["threatBrief"]["sections"]
        assert dashboard_execution["conversation_context"]["thread"]["resolved_entity"]["type"] == "dashboard"

        alert_item = next(item for item in generated if item["label"] == "Alert Details")
        alert_thread_id = alert_item["payload"]["conversation"]["thread_id"]
        alert_turns = list_turns(conn, thread_id=alert_thread_id, owner_username=owner)["turns"]
        alert_assistant = next(turn for turn in alert_turns if turn["role"] == "assistant")
        assert alert_assistant["entity_snapshot"]["active_entity"]["id"] == str(ids["alert"])

        source_item = next(item for item in generated if item["label"] == "Source IP")
        completed_thread_id = source_item["payload"]["conversation"]["thread_id"]
        current = get_thread(conn, thread_id=completed_thread_id, owner_username=owner)
        too_deep = {"level": {"level": {"level": {"level": {"level": {"level": {"level": "reject"}}}}}}}
        rejected = client.post(
            f"/ai/threads/{completed_thread_id}/turns",
            json={
                "expected_version": current["version"],
                "client_request_id": "genuinely-deep-public-payload",
                "role": "user",
                "content": "Store this malformed payload.",
                "assertion_type": "analyst_statement",
                "structured_payload": too_deep,
            },
        )
        assert rejected.status_code == 400
        assert rejected.get_json()["error_code"] == "invalid_session_memory_request"
        assert "nested too deeply" in rejected.get_json()["error"]
