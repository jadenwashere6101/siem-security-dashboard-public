## Why

The SIEM now preserves more investigation context than it used to, but analysts still have to infer too much from raw severity, generic rule names, and fragmented workflow surfaces. The remaining problem is not a lack of alerts. It is that too many alerts still answer only "something happened" instead of "what deserves attention first, and why?"

This change is needed to improve investigation quality without reintroducing alert storms. The project must make existing alerts, incidents, recon activities, and analyst context smarter while staying operationally modest. It is not a detection-rule expansion project, not a UI redesign, and not a threat-intelligence platform replacement.

## What Changes

- Add a separate Investigation Value model that ranks analyst attention without replacing Severity.
- Define whether analyst confidence should exist separately from Severity and Investigation Value, with an explainable model if retained.
- Add campaign intelligence centered on the protected target, repeated services, recurrence, progression, and returning-attacker context without creating standalone repeat-IP alerts.
- Redesign incident philosophy so incidents represent actionable investigations instead of automatically inflating into mostly P2 cases.
- Promote Recon Activities into first-class analyst workflow objects with clearer navigation, history, and campaign relationships.
- Redesign analyst-facing wording for Port Scan, Allow After Deny, campaign indicators, badges, and related workflow labels so an analyst can understand them at a glance without reading documentation.

## Capabilities

### New Capabilities

- `investigation-value-and-confidence`: Explainable analyst-priority modeling that is separate from Severity and exposes the reasons behind urgency.
- `campaign-intelligence-and-returning-attackers`: Target-centered campaign tracking and returning-attacker context without alert multiplication.
- `incident-intelligence-and-recon-workflow`: Smarter incident ownership, merging, closure, and Recon Activity workflow behavior.
- `port-scan-and-allow-after-deny-experience`: Analyst-facing explanation, enrichment, and wording improvements for Port Scan and Allow After Deny workflows.

### Modified Capabilities

- None in this authoring step. Future implementation will update existing alert, incident, recon, and workspace behavior under these new contracts.

## Impact

- Backend scoring, enrichment, and read-model logic in `core/`, `engines/`, and `routes/` will need additive investigation-priority, campaign, and incident-intelligence behavior.
- Existing analyst-facing surfaces in `frontend/src/components/` and `frontend/src/services/` will need scoped wording, ranking, and navigation changes, not a broad layout redesign.
- Existing pfSense, source-IP context, incident, and recon-activity behavior will be refined around workflow clarity and prioritization rather than new detector volume.
- No production mutation, deployment, commit, or VM action is part of this spec-authoring step.
