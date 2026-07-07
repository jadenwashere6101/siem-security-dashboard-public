## Why

Opening an incident today (`core/incident_store.create_incident`) writes only `title`, `severity`, `priority`, `status`, `source_ip`. Everything an analyst would want to know about the state of the investigation at the moment it opened — the triggering alert's reputation data, MITRE mapping, correlation context — either isn't captured at all, or is only available by re-reading the alert row live, which can have since changed (`status`, `response_action`, `response_status` all mutate after the fact). Meanwhile, the codebase already has a correct, working live-recompute path (`build_readonly_incident_timeline`, SOC Command Center) for anything that legitimately changes after creation. There is no durable record of "what did we know when we opened this case" — only a live view of "what do we know right now." This spec closes that gap with the smallest possible addition, reusing enrichment that already exists rather than building new enrichment.

## What Changes

- Define a durable, immutable **evidence snapshot**, captured exactly once, synchronously, in the same transaction as incident creation — not a live-updating record.
- Specify exactly which investigation-context fields are required, optional, derived, snapshotted, or left as live references, based on a fresh audit of what the platform already computes (AbuseIPDB reputation already on the alert row, MITRE mapping as an existing pure function, correlation context already whitelisted) versus what genuinely doesn't exist yet at incident-creation time (execution history, response outcomes, analyst notes — which correctly stay live).
- Specify the data model (three new columns on the existing `incidents` table: `evidence_snapshot`, `evidence_captured_at`, `evidence_schema_version`), the redaction approach (reuse of the existing `redact_soar_outcome_metadata` convention), and immutability/audit requirements.
- No implementation, no schema changes, and no code changes in this proposal step.

## Capabilities

### New Capabilities
- `incident-evidence-collection-and-case-enrichment`: records the requirements for a one-time, immutable evidence snapshot captured at incident creation, and the automatic case-enrichment flow that populates it by reusing existing enrichment functions. No existing spec under `openspec/specs/` covers this domain.

### Modified Capabilities
(none — this proposal does not change the behavior of any shipped capability; evidence capture is additive to `create_incident` and does not alter existing incident creation, linking, status-transition, or timeline behavior)

## Impact

- **Affected code (future implementation phase, not this proposal step):** `core/incident_store.py` (evidence assembly wired into `create_incident`), a new migration adding three columns to `incidents`, `routes/incident_routes.py` (expose the new fields on `GET /incidents/:id`), possibly small visibility changes to `helpers/enrichment_helpers.py` (exporting the correlation-subset helper) and a shared extraction of `core/soar_response_outcomes.py`'s redaction logic.
- **Affected artifacts (this step):** adds `openspec/changes/incident-evidence-collection-and-case-enrichment/` as a new, unimplemented child change under the `soar-playbook-modernization-roadmap` parent.
- **Downstream effect:** gives analysts and any future case-management UI a trustworthy, point-in-time record of what was known when an incident opened, independent of later changes to the alert or ongoing automation; unblocks any future investigation-quality work that depends on stable, citable evidence rather than live-recomputed state.
- **Dependencies:** soft dependency on `Ad Hoc Trigger & Enrichment Step` per the parent roadmap ("reuse enrichment-snapshot shape") — not yet created at the time of this spec. This spec proceeds independently and defines its own snapshot shape now, reusing only enrichment that already exists in the codebase today; reconciling shapes with that future spec, if it introduces an overlapping snapshot concept, is deferred to whichever spec lands second.
