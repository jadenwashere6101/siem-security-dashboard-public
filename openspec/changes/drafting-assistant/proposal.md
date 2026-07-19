## Why

Phase 3 lets analysts gather read-only AI investigation evidence, but the AI still cannot safely produce structured proposed follow-up content. Phase 4 adds AI-generated drafts so analysts can review suggested detection, playbook, note, escalation, response, and checklist content without any draft being applied, persisted as production state, or executed.

## What Changes

- Add a Drafting Assistant capability that generates validated, clearly labeled AI drafts from existing SIEM context and optional Phase 3 read-tool evidence.
- Define canonical draft types and schemas for detection rule changes, playbook drafts, incident notes, escalation summaries, response recommendations, and investigation checklists.
- Add a backend draft service that reuses the Phase 1A gateway, Phase 1B context builder/response contract, and Phase 3 read-tool evidence where appropriate.
- Add authenticated read-only draft API behavior that returns draft payloads for review only and never calls existing mutation, approval, SOAR, registry command, or execution paths.
- Extend the existing analyst AI UI only as needed to display drafts as reviewable AI-generated proposals with validation state, source attribution, copy/export affordances where safe, and clear “not applied” labeling.
- Add focused verification proving drafts are validated, non-persistent, RBAC-protected, source-grounded, secret-safe, and separated from execution/approval paths.
- Exclude approval-gated execution, autonomous actions, draft persistence, schema migrations, new provider work, and broad UI redesign.

## Capabilities

### New Capabilities

- `drafting-assistant`: AI-generated, schema-validated SOC drafts that are reviewable but never applied, persisted, or executed by Phase 4.

### Modified Capabilities

- None.

## Impact

- Backend: add draft schemas/service code under `core/ai`, extend `routes/ai_routes.py` with a thin authenticated draft endpoint, and add focused backend tests around validation and non-mutation boundaries.
- Frontend: extend existing AI service and response components with a draft review presentation that clearly distinguishes proposed content from production state.
- API: introduce a bounded draft-generation request/response contract that preserves Phase 1A metadata, Phase 1B grounding, and Phase 3 source/tool evidence metadata.
- Database/runtime: no migrations, no draft persistence, no background jobs, no production writes, no provider credential changes, and no VM work during spec creation.
