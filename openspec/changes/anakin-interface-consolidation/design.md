## Context

The backend now exposes canonical workflow orchestration at `POST /ai/workflows` while preserving legacy adapters. This phase consolidates frontend controls without redesigning non-AI workflows. It uses the prior audit decisions instead of re-auditing every UI.

## Target Surfaces

- Dashboard: `Ask Anakin`, `Quick Explain`, `Deep Investigate`.
- Alert Details: `Quick Explain`, `Deep Investigate`, `Decision Support`, `Generate Artifact`.
- Source IP: `Quick Explain`, `Deep Investigate`, `Decision Support`, `Generate Artifact`.
- Incident: `Deep Investigate`, `Decision Support`, `Generate Artifact`.
- SOC Command Center / Recon: `Deep Investigate`, `Decision Support`, `Generate Artifact`.
- Response Registry: `Decision Support`, `Deep Investigate`, `Generate Artifact` when response recommendation is supported.
- Analyst Workspace: `Investigate with Anakin`, `Decision Support`, `Generate Artifact`.
- Global Anakin surface: one freeform input with compact shortcuts for `Quick Explain`, `Deep Investigate`, `Decision Support`, and `Generate Artifact`; no large permanent button grid.
- Command Palette: one canonical entry per workflow; Repo Assistant hidden unless authorized.
- SOC Briefings: Generate/Run Briefing only.
- Repo Assistant: dedicated assistant only.

## Frontend Routing

Add `requestAiWorkflow(payload)` in `aiService`. Consolidated controls call `/ai/workflows` with:

```json
{
  "workflow": "auto",
  "prompt": "What should I do?",
  "context_type": "alert",
  "entity": {"alert_id": 1001},
  "artifact": {"type": "incident_note"},
  "tool_policy": {"max_tool_calls": 5, "time_window_hours": 24}
}
```

Shortcut buttons specify explicit workflow. The freeform Ask Anakin input uses `workflow=auto`.

## Artifact Menu

Artifact generation is one menu per surface. Menu items send `workflow=generate_artifact` plus `artifact.type`. Supported types:

- `incident_note`
- `alert_note` only where supported by backend schema; otherwise use `investigation_checklist` for alert/checklist needs.
- `investigation_checklist`
- `escalation_summary`
- `playbook_draft`
- `detection_rule_change`
- `response_recommendation`

If a requested artifact type is not backend-supported in this phase, the menu must not display it.

## Progress And Chooser UX

While a workflow request is running, the response panel may show the planned workflow and generic active state. After response, it shows backend lifecycle stages exactly as returned. For Deep Investigate, stage labels are taken from backend lifecycle metadata. The UI must not invent model reasoning or durable job state.

If `/ai/workflows` returns `status=chooser_required`, the response panel renders a compact workflow chooser using `result.allowed_workflows`; choosing an option replays the original prompt with that explicit workflow.

## Safety

Decision Support cannot render draft/confirm UI. Generate Artifact can render existing draft review, and any action preview/confirm remains inside the existing gated `AiResponsePanel` flow. Repo Assistant and SOC Briefing remain explicit navigation/route capabilities and are not added to auto-routing shortcuts for unauthorized users.

## Non-Goals

- No backend compatibility adapter removal.
- No SSE/WebSocket or durable Deep Investigate job UI.
- No model, runtime config, DB, VM, deployment, commit, or push changes.
