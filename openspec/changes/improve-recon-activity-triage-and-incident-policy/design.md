## Context

The current recon workflow is partly in place but still incomplete from an analyst perspective:

- `frontend/src/components/SocCommandCenter.js` already exposes a Recon Activity master-detail surface, but the list entries are nearly identical because they mostly render `activity.label`, severity, status, and `protected_range_key`.
- `core/recon_activity_store.py` already computes enough summary data to distinguish activities, including representative source IPs, primary destination IP/port, counts, related incident linkage, alert IDs, and investigation intelligence.
- `core/incident_store.py` and `routes/ingest_routes.py` still treat incident creation as primarily severity-gated, with only a narrow pfSense operational-flags exception.
- Existing honeypot rules intentionally describe routine scanner and admin probing as visibility or review signals, not automatic case signals.
- The repo already contains investigation-intelligence helpers and safe P3 auto-close guards from the earlier `analyst-investigation-intelligence` change, so this change should reuse that layer rather than inventing another scoring model.

The audit conclusion is narrow:

1. Recon Activity needs a triage-first UX pass.
2. Incident eligibility needs an actionability policy.
3. Priority needs explainable differentiation.

## Goals / Non-Goals

**Goals**

- Make Recon Activity cards meaningfully distinct while staying compact.
- Let analysts tell whether an activity is new, materially updated, or already reviewed without lying about unread state.
- Make Recon Activity detail identify target, source, service, timing, investigation reasons, and next pivots immediately.
- Replace implementation-heavy wording in touched surfaces with plain-English wording that works at a glance.
- Stop routine honeypot probes and routine aggregate pfSense recon from creating incidents just because they are `HIGH`.
- Keep progression-backed pfSense behavior and stronger honeypot behaviors incident-eligible where operationally justified.
- Replace broad `HIGH -> P2` behavior with a simple P1/P2/P3 policy based on actionability.
- Preserve safe P3 auto-close guards and historical records.

**Non-Goals**

- No new detectors or detector-family redesign.
- No severity-remapping project outside the narrow incident-policy use of existing evidence.
- No new workspace or global navigation redesign.
- No new alert tables, columns, or sidebars beyond scoped recon card/detail changes.
- No historical rewrite of alerts, incidents, priorities, approvals, or closures.

## Design Principles

### 1. At-a-glance understanding is mandatory

Every touched analyst-facing recon or incident label must answer "what is this?" and "why should I care?" in seconds. The fix is concise wording and compact summaries, not long helper paragraphs.

### 2. Show investigation meaning, not raw field dumps

The recon workspace should prefer a short headline, target/service identity, timing, and investigation reasons over repeated generic titles or low-signal metadata.

### 3. New or updated state must be truthful

Do not fake an unread system that resets on refresh. If durable viewed-state persistence would be disproportionate, implement the smallest honest alternative and expose its limitation clearly in the design.

### 4. Incident eligibility is not severity

Severity remains the danger label. Incident eligibility answers whether a case is warranted. Routine hostile recon can remain visible without becoming a case.

### 5. Priority must describe response urgency

P1 is for immediate action. P2 is for materially actionable investigation. P3 is for valid but non-urgent case ownership. Everything else should stay outside incidents.

## Architecture

### Recon Activity UX Layer

This change keeps Recon Activity as the existing object and improves only its projections:

```text
recon_activities row
    + existing summary / investigation_intelligence
    + viewed-state metadata
    -> compact card summary projection
    -> detail identity projection
    -> high-value navigation actions
```

Recommended additions:

- Add a small viewed-state store keyed by recon activity and analyst-safe viewer context if an existing user/session mechanism supports it safely.
- If durable per-user persistence is not available without disproportionate work, persist a truthful activity-level "last reviewed at" marker only when the activity is opened and compare it to `updated_at`. This supports `Updated` truthfully, while `New` can be limited to "not yet reviewed in this environment" rather than "not yet reviewed by this human."
- Expose a backend-authored card summary contract so the UI does not invent inconsistent wording.

### Incident Policy Layer

This change adds an incident-policy helper, not a new incident system:

```text
alert severity + alert_type + context + investigation evidence
    -> incident eligibility decision
    -> grouped ownership decision
    -> priority decision + visible reasons
```

The policy should live close to `core/incident_store.py` and be called from the existing ingest incident path in `routes/ingest_routes.py`.

### Existing Safe Closure Guards

The current P3 auto-close path already checks all required safety conditions. This change preserves that path and only adapts incident creation and grouping logic upstream so fewer low-value incidents enter the lifecycle in the first place.

## Decisions

### 1. Recon Activity cards become compact triage summaries

Each list card should expose only the highest-value fields available:

- analyst-facing headline
- investigation-value label
- primary target or target summary
- representative source when meaningful
- primary port/service
- compact count summary when it clarifies scope
- last activity / updated time
- status
- `New` or `Updated` indicator when truthful

The current repeated `Distributed Internet Reconnaissance Activity` title should become a context-specific headline, such as:

- `Routine Internet Recon`
- `Repeated VPN Recon`
- `Campaign-Linked Public Service Recon`

The backend should author the wording to keep tables, cards, and detail summaries consistent.

### 2. Viewed and updated state should use the smallest truthful persistence model

Preferred behavior:

- `Viewed` means the analyst opened the Recon Activity detail successfully.
- `Updated` means the activity's material investigation summary changed after the last viewed marker. Material changes include `updated_at`, linked alert count growth, related incident linkage, target/service changes, investigation-value change, or campaign-assessment change.
- `New` means the activity has never been reviewed under the chosen persistence model.

Implementation preference order:

1. Reuse an existing durable user-scoped preference or view-state mechanism if the repo already has a safe one for the same kind of UI memory.
2. Otherwise add a minimal recon-activity view-state record keyed to activity and user if user identity is already safely available.
3. If per-user durability is disproportionate, use an activity-level `last_reviewed_at` model and document that it is shared review state, not personal unread state.

This change must not use a refresh-local only unread dot that resets incorrectly across reloads.

### 3. Recon detail must lead with identity and actionability

The detail pane should answer these questions first:

- What target is this about?
- Which source or sources were involved?
- What service was targeted?
- Why should I care?
- What can I open next?

Recommended identity fields:

- `Primary target`
- `Representative source`
- `Additional sources`
- `Primary service`
- `First seen`
- `Last seen`
- `Linked alerts`
- `Related incident`
- `Investigation value`
- `Current assessment`

Do not expand large raw lists by default. Use representative values and counts.

### 4. Investigation pivots stay intentionally small

Approved pivots:

- `View Linked Alerts`
- `Open Related Incident`
- `Open Representative Source`
- `Open Primary Target`

Buttons should render only when the underlying identifier exists and the destination is supported by existing navigation patterns.

### 5. Plain-English wording changes are required in touched surfaces

Examples:

- `protected_range_key` -> `Target range`
- `Underlying alerts` -> `Linked alerts`
- `Coordination status` -> `Coordination evidence` or `Current assessment`
- `Not Established` -> `Coordination not established`

Where reasoning matters, pair the status with short reasons instead of bare status words.

### 6. Investigation Value presentation must stay explainable

This change reuses the existing Investigation Value model and changes only the presentation rules for Recon Activities:

- show label
- show 1-3 concise reasons
- show whether review is recommended
- never show an unexplained numeric score alone

### 7. Incident eligibility must be explicit by rule family and evidence

Approved direction:

- `honeypot_scanner_detected`: alert only
- `honeypot_admin_probe`: alert only
- `honeypot_env_probe_threshold`: alert first by default; incident eligible only with stronger evidence already available in context, such as repeated sensitive-path probing, progression/corroboration, repeated protected-service targeting, campaign linkage, or meaningful recurrence
- `honeypot_credential_stuffing_threshold`: may remain incident eligible when its approved evidence threshold is met
- routine aggregate `pfsense_firewall_port_scan` and routine aggregate `pfsense_firewall_repeated_deny`: alert/recon activity only
- progression-backed pfSense behaviors such as `pfsense_firewall_allow_after_deny` remain incident eligible

This policy must not weaken the alerts themselves. It only changes whether they deserve a case.

### 8. Priority becomes a simple actionability policy

Policy:

- `P1`: critical or likely-compromise evidence requiring immediate action; extremely rare
- `P2`: materially actionable progression, active containment decision, or strong corroborated behavior requiring prompt review
- `P3`: valid case-worthy investigation that is not immediately urgent
- `No Incident`: routine reconnaissance, background scanning, alert-only honeypot probes, or aggregate activity that is visible but not case-worthy

Every created incident must expose plain-English priority reasons.

### 9. Grouped recon ownership remains bounded

Rules:

- one recon activity may own at most one grouped incident
- member alerts should link to that grouped incident rather than fan out into per-source incidents
- source-specific progression can still create its own actionable incident when it leaves the routine aggregate path
- unrelated activity must not merge only because it is close in time

### 10. Historical behavior remains untouched

This change applies prospectively. It does not rewrite historical alert severities, incident priorities, incidents, approvals, or closures.

## Capability Boundaries

### Capability 1: Recon Activity Triage

Defines compact card summaries, truthful new/updated state, detail identity fields, pivots, and wording clarity.

### Capability 2: Incident Eligibility And Priority

Defines rule-family incident eligibility, grouped ownership, explainable P1/P2/P3 assignment, and preservation of safe closure behavior.

## Expected Files

- `core/recon_activity_store.py`
- `core/incident_store.py`
- `routes/ingest_routes.py`
- `frontend/src/components/SocCommandCenter.js`
- `frontend/src/components/IncidentsPanel.js`
- `frontend/src/components/AlertDetailsPanel.js`
- `frontend/src/services/reconActivityService.js`
- focused tests in `tests/` and `frontend/src/components/*.test.js`

Settings changes are explicitly out of scope unless the implementation discovers a currently exposed incident or recon setting that is stale or misleading.

## Implementation Phases

### Phase 1: OpenSpec authoring and validation

Create the narrow change, capability specs, and tasks for Recon Activity triage and incident policy only.

### Phase 2: Recon Activity analyst UX

Implement compact card summaries, truthful viewed/updated state, detail identity fields, pivots, and wording improvements.

### Phase 3: Incident policy

Implement explicit incident eligibility, grouped ownership, and actionability-based priority reasoning.

### Phase 4: Verification and handoff

Run focused backend/frontend tests, production build, strict OpenSpec validation, and diff hygiene. Confirm no VM work, commit, push, or deployment occurred.

## Risks / Trade-offs

- **Viewed-state persistence may be harder than the UX benefit justifies.** Mitigation: prefer the smallest truthful shared-review model over fake per-user unread state.
- **Rule-family incident policy can drift from detector intent.** Mitigation: align policy with existing rule catalog guidance and preserve alert generation unchanged.
- **Recon cards can become noisy if too many fields are shown.** Mitigation: keep the projection compact and backend-authored.
- **Priority reasoning can become duplicated across backend and UI.** Mitigation: generate reasons in the backend and render them directly.
- **Existing dirty-worktree investigation-intelligence changes touch some of the same files.** Mitigation: integrate carefully with those additive changes and avoid reverting unrelated work.

## Validation Plan

- `openspec validate improve-recon-activity-triage-and-incident-policy --strict`
- `git diff --check`
- later implementation pass:
  - focused backend incident-policy tests
  - focused backend recon-store/API tests
  - focused honeypot and pfSense ingest tests
  - focused frontend SOC Command Center and Incidents tests
  - `python3 -m py_compile` on changed backend/test files
  - `npm run build`

## Success Criteria

- Recon Activity cards are distinguishable at a glance.
- Analysts can tell whether activity is new, updated, or already reviewed without misleading state.
- Detail view surfaces source, target, service, timing, investigation reasons, and next pivots immediately.
- Routine honeypot and routine aggregate pfSense recon stop creating unnecessary incidents.
- P1/P2/P3 meaningfully reflect actionability.
- No alert multiplication is introduced.
