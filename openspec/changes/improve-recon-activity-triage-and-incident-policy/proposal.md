## Why

Recon Activities already exist, but the current workspace does not help analysts distinguish them quickly. The left-hand list repeats generic titles, the detail pane exposes data before identity and next actions, and the wording still leans on implementation language instead of plain-English investigation meaning.

Incident creation is also still too severity-driven. High-severity honeypot alerts and source-specific pfSense alerts can still become incidents even when they represent routine reconnaissance that analysts should see but not case-manage. The current `HIGH -> P2` bias makes incident priority too coarse and keeps P2 overloaded.

This change is intentionally narrow. It improves how analysts triage and investigate Recon Activities, and it makes incident eligibility and priority reflect actionability rather than severity alone. It does not add new detectors, expand alert volume, redesign major navigation, or build a generic campaign platform.

## What Changes

- Replace generic Recon Activity list entries with compact triage cards that surface distinct, glanceable summaries.
- Add truthful `New` / `Updated` / previously reviewed activity state using the smallest safe persistence model justified by the existing architecture.
- Rework the Recon Activity detail pane so it immediately answers target, source, service, timing, investigation value, and next pivots.
- Add only the highest-value investigation pivots from Recon Activity detail: linked alerts, related incident, representative source, and primary destination when supported.
- Reword touched analyst-facing Recon and incident labels into plain English where current wording is too implementation-heavy or ambiguous.
- Separate incident eligibility from severity so routine honeypot scanner/admin probing and routine aggregate pfSense recon stay alert-only.
- Implement a simple, explainable P1/P2/P3 policy based on operational actionability, not direct severity mapping.
- Preserve safe P3 auto-close behavior and historical records without rewriting past incidents or alerts.

## Non-Goals

- No new detector families.
- No broad severity redesign.
- No broad SOAR redesign.
- No new workspace or major navigation shell.
- No alert multiplication.
- No generic campaign platform work outside what Recon Activity already supports.
- No VM access, deployment, commit, push, or archive work in this change.

## Impact

Analysts should be able to identify the meaningful Recon Activity in seconds instead of opening several near-identical cards. Incidents should become rarer, more defensible, and better distributed across P1/P2/P3 because routine recon and low-value honeypot probes no longer inherit case creation from severity alone.
