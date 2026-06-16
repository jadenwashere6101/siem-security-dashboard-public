## Why

Operators currently have to move across Alerts, Incidents, SOAR Queue, Blocklist, Playbook Executions, SOC Command Center, and Map views to answer what is known about a single `source_ip`. The underlying data is mostly correct, but each surface assembles only part of the picture, which increases investigation time and creates opportunities for unclear status interpretation.

## What Changes

- Add a read-only backend source-IP context contract for answering: "What do we know about this source IP?"
- Aggregate existing source-IP-related context from alerts, incidents, queue activity, blocklist state, behavioral reputation, external reputation snapshots, and linked playbook executions.
- Define explicit status semantics so alert status, incident status, queue status, blocklist status, external reputation, and behavioral reputation remain separate concepts.
- Define bounded response limits for recent alerts, incidents, queue rows, and playbook executions.
- Define input validation, permission behavior, error handling, and safe frontend consumption expectations.
- Avoid any mutation endpoint, lifecycle change, SOAR orchestration change, or schema change as part of this contract.

## Capabilities

### New Capabilities
- `source-ip-context`: Read-only normalized backend API contract for source-IP investigation context across existing SIEM and SOAR records.

### Modified Capabilities

None.

## Impact

- Backend API: introduces a new read-only source-IP context endpoint backed by existing data.
- Backend tests: requires API contract coverage for validation, permissions, response shape, bounded collections, and status semantics.
- Frontend: future integration should consume the normalized contract in Alert Details and Map popup through shared display components rather than duplicating joins in the browser.
- Data model: no schema changes expected; any schema addition must be separately justified before implementation.
- SOAR and incident behavior: no lifecycle, queue, playbook, approval, or orchestration behavior changes.
