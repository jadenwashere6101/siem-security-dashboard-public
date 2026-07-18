## Why

Phase 1B can answer from a single bounded context snapshot, but deeper SOC questions often require several read-only lookups across alerts, incidents, events, source-IP history, playbook executions, audit records, and response registry context. Analysts need the assistant to investigate through existing SIEM read APIs without becoming an autonomous actor or bypassing established source-of-truth paths.

## What Changes

- Add a read-only SOC tool layer that lets the AI request bounded investigation lookups through approved backend services only.
- Define one canonical read-tool contract covering tool names, schemas, authorization, limits, result attribution, error states, and mutation prohibitions.
- Extend the Phase 1B SIEM chat/explainer backend path so eligible requests can perform a bounded tool-assisted investigation before producing a grounded answer.
- Return tool evidence, source attribution, truncation, gateway metadata, and safe failure states to the frontend.
- Update the existing analyst AI response experience only as needed to show tool evidence and tool-run status; do not create a broad new UI workflow.
- Add focused backend and frontend tests proving read-only behavior, canonical source reuse, bounded execution, RBAC, secret safety, and drift protection.

## Capabilities

### New Capabilities

- `soc-assistant-read-tools`: Read-only AI investigation tools, canonical tool contracts, bounded tool execution, evidence attribution, and analyst-visible tool metadata.

### Modified Capabilities

- None.

## Impact

- Backend AI modules under `core/ai` gain a tool contract, registry/executor, and tool-assisted service flow that reuses existing SIEM read helpers.
- `routes/ai_routes.py` remains thin and continues using existing analyst/super-admin RBAC.
- Existing alert, incident, source-IP, recon, playbook, audit, and response-registry read paths may need small helper extraction only where current route logic is not reusable without duplication.
- Frontend AI service/response components may be extended to display tool evidence and bounded investigation metadata.
- No schema migration, production write path, shell access, direct provider database access, background inference, VM work, deployment, commit, or push is part of this spec creation.
