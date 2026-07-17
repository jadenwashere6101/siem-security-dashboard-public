## Context

This audit stayed inside the analyst workflow surfaces that already exist: Dashboard / Recent Alerts, SOC Command Center Recon Activity, and Response Registry. The implementation evidence points to a connected class of problems rather than separate feature gaps:

- `Recent Alerts` uses one broad `search` parameter that matches `source_ip` or `message`, so analyst pivots for a specific source can broaden into unrelated alerts.
- In `App.js`, filter changes trigger the data-fetch effect before the later pagination-reset effect, so a deep link or filter change on page 2+ can issue one stale-offset request before returning to page 1.
- `ResponseRegistryPanel` applies incoming deep-link context for `view`, `q`, and related IDs, but it does not reset local disposition/origin/outcome/enforcement filters that can still hide the intended record.
- Recon Activity detail already has `display.primary_target` data in the backend projection and the earlier design approved `Open Primary Target`, but the current UI never exposes that pivot.
- Recon Activity list cards are bounded but not scrollable because the list column lacks its own overflow behavior.
- Expanded alert details preserve evidence, but the ordering is noisy: identity, message, source, reputation, correlation, response, and raw timestamps read as one long stack with repeated labels instead of grouped investigation sections.
- Shared loading state references `workspace-spin`, but no keyframes define it, so the spinner does not animate.

The design therefore has to tighten navigation state and improve readability without changing detection content, incident policy logic, or workspace information density in a destructive way.

## Goals / Non-Goals

**Goals:**
- Make analyst pivots into `Recent Alerts` exact when the intent is “show me this source or this target,” while preserving broad manual search for hunting.
- Make dashboard deep links request-safe by resetting pagination and incompatible state before list fetches occur.
- Make Response Registry deep links authoritative enough that stale local filters cannot hide the intended indicator.
- Reorder and group analyst evidence in alert and recon investigation views without removing forensic content.
- Restore missing approved recon pivots and fix bounded list scrolling.
- Capture directly related low-risk polish items that affect analyst trust in UI state.

**Non-Goals:**
- No detection-rule tuning, severity-matrix rewrite, or backend architecture rewrite.
- No new dashboard family, no generalized Detection Health expansion, and no production-data cleanup workflow inside this source change.
- No change to incident-creation policy semantics unless implementation work later proves an audited UI dependency requires a wording-only clarification.
- No destructive reduction of alert evidence, response history, or raw identifiers.

## Decisions

### 1. Add exact analyst pivot filters alongside broad search

`Recent Alerts` needs an exact investigation contract separate from free-text search. The narrow change is to add additive exact query fields for analyst pivots, such as `source_ip` and `target_ip`, to `/alerts` and `/alerts/summary`, while retaining `search` for manual broad hunting.

Why this over reinterpreting `search`:
- The current backend intentionally searches both `host(source_ip)` and `message`.
- Recon and related-alert pivots are not “search”; they are “open the exact investigation slice.”
- Overloading `search` further would keep the current ambiguity and make regressions harder to test.

### 2. Reset deep-link state synchronously, not via a follow-up effect

Dashboard deep links should construct the next alert-list state atomically: exact filter/search intent, cleared incompatible local filters when required, selected row, and offset `0`. The list request should be driven from that already-reset state rather than from a stale page offset followed by a later correction.

Why this over keeping the current effect ordering:
- The current effect order in `App.js` allows one request with stale pagination.
- This explains the observed “briefly right, then wrong” behavior for related-alert/recon pivots on non-zero pages.
- A single state transition is easier to cover with regression tests than two intentionally racing effects.

### 3. Treat deep-link context as authoritative in Response Registry

Opening Response Registry from alerts, incidents, approvals, playbooks, or queue history should temporarily override stale registry-local filters that can hide the intended record. The incoming navigation request should reset pagination, selection, and incompatible local filter controls while preserving the analyst’s ability to adjust filters afterward.

Why this over preserving every local filter:
- Preserving stale local state is useful for manual browsing but incorrect for an explicit investigation handoff.
- The current implementation already treats `view`, `q`, and related IDs as navigation context; this extends that principle consistently.

### 4. Re-group investigation evidence instead of removing it

Expanded alert detail and Recon Activity detail should move to evidence-first groupings:
- summary / why it matters
- target and network evidence
- threat or campaign evidence
- response and workflow context
- raw metadata / exports / timestamps

Collapsible subsections are acceptable for lower-signal material, but no evidence block is deleted.

Why this over cutting fields:
- The complaint is signal-to-noise, not data absence.
- Existing forensic value depends on keeping raw identifiers, reasons, response history, and timestamps accessible.

### 5. Finish the approved recon pivots using existing data only

Recon Activity should expose `Open Primary Target` only when `display.primary_target` exists and a supported destination can be reached through current navigation patterns. The list column should gain its own scroll containment so the bounded panel stays usable.

Why this over a larger recon redesign:
- The earlier approved design already scoped the pivot.
- Backend projections already provide the required identifier.
- The current issue is omission and state clarity, not absence of a larger workspace.

### 6. Fix loading polish through the shared async-state primitive

The shared initial-loading spinner should define its animation once in the existing shared shell/styles path so every consumer benefits without bespoke per-panel changes.

## Risks / Trade-offs

- [Exact alert pivot filters add backend/frontend contract surface] → Mitigation: keep the contract additive, optional, and limited to exact analyst pivots already used by current navigation paths.
- [Clearing incompatible deep-link filters may surprise analysts who expected sticky state] → Mitigation: only clear state for explicit cross-workspace investigation handoffs; preserve manual filtering once the destination opens.
- [Regrouping detail content can create perceived data loss if sections are collapsed poorly] → Mitigation: default high-value sections open, keep labels explicit, and preserve all existing evidence fields.
- [Recon primary-target navigation could point to an unsupported destination] → Mitigation: render the pivot only when a supported destination and identifier are both present.
- [Touching shared loading state can affect multiple workspaces] → Mitigation: keep the change to animation/style definition only, without changing loading semantics.
