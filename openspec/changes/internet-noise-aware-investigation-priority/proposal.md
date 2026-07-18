## Why

Production evidence has exposed an analyst-prioritization gap rather than a detector-quality gap. Medium alerts and some incidents are being driven by IPs that external internet-noise intelligence classifies as benign scanners, crawlers, or routine background activity, but the current workflow has little ability to model "commodity internet noise" separately from meaningful local escalation.

This change is needed now to keep alerts visible while preventing routine internet noise from accumulating investigation value, campaign wording, returning-attacker labels, and incident pressure without enough local evidence. The goal is additive context, not suppression, and local evidence must remain authoritative.

## What Changes

- Define a dedicated internet-noise assessment that remains separate from detector severity, AbuseIPDB reputation, and internal behavioral reputation.
- Use internet-noise intelligence as a negative weighting input for investigation value, campaign wording, and incident eligibility, never as a hard ignore or auto-close signal.
- Define explicit local-evidence override rules so successful authentication, progression, protected-target repetition, cross-source correlation, or other strong local evidence continue to drive urgency even when a source is classified as commodity noise.
- Add an analyst-facing explanation contract so deprioritization and override behavior are visible in alerts, source-IP context, and incident reasoning.
- Require a VM-side production audit against recent real alerts and incidents before implementation is allowed to change prioritization or incident policy.

## Capabilities

### New Capabilities
- `internet-noise-investigation-prioritization`: additive internet-noise-aware prioritization for alert enrichment, investigation value, analyst explanation, and incident policy with explicit local-evidence overrides.

### Modified Capabilities
- None.

## Impact

- Backend intelligence and read-model logic in `core/investigation_intelligence.py`, `core/ip_helpers.py`, `core/incident_store.py`, `routes/alerts_events_routes.py`, and `routes/source_ip_context_routes.py` will need additive internet-noise context and explanation behavior in a later implementation phase.
- Existing external reputation behavior from `lookup_ip_reputation()` and stored `alerts.reputation_*` fields remains in scope only as a neighboring concept; this change does not replace AbuseIPDB or detector-authored severity.
- Analyst-facing surfaces that already expose investigation value, campaign context, returning-attacker context, and source-IP context will need scoped explanation changes in a later implementation phase so analysts can understand why urgency was lowered or preserved.
- No detector suppression, threshold tuning, SOAR redesign, incident lifecycle redesign, production mutation, deployment, commit, or VM execution is part of this spec-authoring step.
