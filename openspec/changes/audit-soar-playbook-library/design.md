## Context

This audit covers the SOAR playbook subsystem as of 2026-07-06: `engines/playbook_engine.py`, `engines/playbook_registry.py`, `engines/playbook_step_executor.py`, `engines/soar_playbook_orchestrator.py`, `engines/soar_playbook_worker.py`, `core/playbook_store.py`, `core/response_action_queue_store.py`, `engines/soar_action_worker.py`, `engines/soar_enqueue_orchestrator.py`, `core/soar_response_outcomes.py` / `soar_response_outcomes_legacy.py`, `migrations/0006`, `0007`, `0012`, `routes/playbook_routes.py`, and the AbuseIPDB (`core/ip_helpers.py`) and MITRE (`helpers/enrichment_helpers.py`) touchpoints. It is read-only: no source, schema, or data was changed to produce it.

The audit is written from a SOC architect's perspective — the question is not "does the code run" but "does this look like automation a working SOC would trust, and would it read as strong signal to a Detection Engineering interviewer." All 13 audit-scope facts below were verified directly against the code (file:line citations retained in the working notes; the roadmap items reference the relevant modules by name).

## Goals / Non-Goals

**Goals:**
- Establish ground truth on what the playbook subsystem actually contains vs. what it appears to contain from architecture docs alone.
- Give every existing unit (framework, action primitive, parallel automation path) an explicit KEEP / KEEP WITH IMPROVEMENTS / MERGE / REPLACE / RETIRE call.
- Catalog realistic, high-interview-value playbooks that don't exist yet, each grounded in an alert type or capability that actually exists in this codebase today (not hypothetical).
- Name the larger structural gaps (orchestration, chaining, rollback, branching) without prescribing their implementation.
- Produce a roadmap the user can pull individual scoped OpenSpec changes from, ordered by value and effort.

**Non-Goals:**
- Not a design for any specific playbook, migration, or code change.
- Not a decision to deprecate the response action queue path, the playbook engine, or any adapter — recommendations are advisory input to future proposals, not authorization to act.
- Not a security review of adapter credential handling (covered by the existing Real Integration Safety Model work, SPEC-INTEG-005).

## 1. Executive Summary

The SOAR platform's *engine* is more mature than its *content*. Lease-based execution, stale recovery, dead letters, canonical response outcomes, and audit trails are all genuinely solid, production-grade reliability engineering. But the thing the engine executes — the playbook library — does not exist. There are zero named, persisted playbook definitions anywhere in the codebase; the seven supported "actions" are almost entirely no-op simulations (`monitor` and `flag_high_priority` write nothing but a log line; `block_ip` never touches a real firewall and never checks the protected-target policy that the *other* SOAR path enforces); and the engine cannot branch, chain, roll back, or re-enrich mid-execution. In its current state, a live demo of "SOAR playbooks" would show an empty list with a well-designed but contentless create form.

A second, more consequential finding: this project actually contains **two parallel, independently triggered SOAR automation systems** that fire off the same alert-commit event — the playbook engine (`soar_playbook_orchestrator` → `playbook_executions` → `playbook_step_executor`) and an older response-action queue (`soar_enqueue_orchestrator` → `response_actions_queue` → `soar_action_worker`). They implement overlapping actions (both can `block_ip`) with inconsistent safety guarantees: the queue path enforces `require_unprotected_target` and requires approval for `block_ip` by policy constant; the playbook path's `block_ip` step does neither. Today this is inert because both paths simulate, but it is exactly the kind of architectural duplication that reads as a red flag in a senior review and should be resolved before either path is extended further.

The highest-value next step is not "write more engine code." It is: (1) decide the relationship between the two automation paths, (2) author a small, high-quality set of concrete playbooks against alert types that already exist in this codebase (`password_spraying_threshold`, `successful_login_after_spray`, `port_scan_threshold`, honeypot alert types, IP reputation), and (3) close the handful of specific correctness gaps (unincremented `attempt_count`, `notify_teams` reachable-but-unvalidated, no protected-target check on playbook `block_ip`) that would embarrass the project in a live code walkthrough.

## 2. Current Playbook Inventory

**Zero concrete playbooks exist.** `playbook_definitions` has no seed data, no fixture file, no demo/onboarding script, and no row inserted by any migration. The only "playbook-shaped" content anywhere is:

| Artifact | What it actually is |
|---|---|
| `frontend/src/components/PlaybooksPanel.js` create-form placeholder | A single illustrative string, `[{"action":"monitor","params":{},"on_failure":"abort"}]`, shown as textarea placeholder text — never persisted, not a real playbook. |
| Test fixtures (`tests/test_playbook_step_executor.py`, `tests/test_playbook_store.py`) | Synthetic ids (`pb_x`, `pb_bad`, `pb_lease_notify`, etc.) built purely to exercise executor/registry code paths — not meant to represent, and not usable as, real SOC automation. |

There is therefore no "playbook" to inventory in the sense the audit request assumes (a named, running, alert-linked automation). What exists instead is a **generic playbook framework**: a schema (`playbook_definitions`, `playbook_executions`, `playbook_schedules`), a trigger matcher (`playbook_engine.match_playbooks`), a linear step executor, and seven reusable action primitives. The rest of this audit treats that framework, its primitives, and the parallel response-action-queue system as the "current inventory" in place of named playbooks, because those are the real units a KEEP/RETIRE call can be made against.

`playbook_schedules` deserves a specific inventory note: it is a fully modeled table (schedule expression, timezone, missed-run policy, max concurrent runs) with complete CRUD and read routes, but **no process anywhere reads `next_run_at` or `schedule_expression` to actually trigger a run**. It is schema and API surface for a feature that does not exist yet — worth knowing before anyone assumes scheduled playbooks work today.

## 3. Playbook Quality Assessment

Assessed against: does it solve a real SOC problem, does it provide meaningful automation (vs. simulated no-op), does it demonstrate engineering skill, would it survive a live interview walkthrough.

| Unit | Real automation? | Engineering quality | Interview walkthrough survives? |
|---|---|---|---|
| Playbook engine + registry + step executor | Framework only — no content | High (leases, idempotency-safe replays, savepoint-isolated outcome writes) | Yes, as infrastructure — but "show me a playbook" has no answer today |
| `require_approval` gate | Yes — genuinely gates execution, RBAC-enforced | High | Yes |
| `notify_slack` / `notify_teams` / `notify_email` / `notify_webhook` | Yes when real mode is enabled; deduplicated, delivery-tracked | High | Yes |
| `block_ip` | No — always simulated, no protected-target check, no real firewall or blocklist mutation | Low as implemented (looks real, isn't, and skips a safety check the sibling system enforces) | No — a follow-up question ("does this check protected IPs like the other path does?") exposes it immediately |
| `monitor`, `flag_high_priority` | No — hardcoded log-only stub | Low | No — these read as placeholder actions, not automation |
| Response action queue (`soar_enqueue_orchestrator`/`soar_action_worker`) | Partially — enforces protected-target policy and real approval-required set for `block_ip`; still simulation-backed | Medium-high | Mixed — good safety modeling, but its existence alongside the playbook engine is the finding, not the queue itself |
| Canonical response outcome model (`soar_response_outcomes.py` + migration 0012) | N/A (observability layer) | High — append-only, redacted, idempotent, booleans enforced at both SQL and Python layers | Yes, arguably the strongest single piece in the whole SOAR subsystem |
| Dead letter capture for playbook failures | Yes, narrowly | Medium — capture is solid; "retry" is a bare status flip, real re-run requires a separate full-execution retry route | Yes, with the caveat explained plainly |
| MITRE tagging (`helpers/enrichment_helpers.py`) | No — static `alert_type → technique_id` dict, display-only | Low-medium | Survives only if framed honestly as "mapping for reporting," not "MITRE-driven detection logic" |
| AbuseIPDB enrichment | Yes, but only at ingest time; not available inside playbook execution | Medium | Survives if the boundary (ingest-time only) is stated up front |

## 4. Individual Playbook Recommendations

Since no named playbooks exist, recommendations are given per real unit:

- **Playbook engine / registry / step executor (framework)** — **KEEP WITH IMPROVEMENTS.** The reliability scaffolding (leases, stale recovery, canonical outcomes, dead letters) is worth keeping and building on. Improvements needed before it's demo-worthy: add at least one real conditional/branch primitive, wire `attempt_count` so the existing retry-eligibility check is not dead code, and fix the `notify_teams`/`SUPPORTED_ACTIONS` registry mismatch (reachable at execution time, rejected at definition-save time).
- **`require_approval`** — **KEEP.** This is the one gate in the system that behaves exactly as advertised (RBAC-restricted, TTL-bound, materializes expiry lazily and correctly). No changes needed.
- **Notification actions (`notify_slack`/`teams`/`email`/`webhook`)** — **KEEP.** Delivery tracking, idempotency keys, and real/simulation mode separation are well built. Low priority for change.
- **`block_ip`** — **REPLACE.** As implemented it is a decorative action: it never validates the target, never checks `soar_protected_targets`, and never can succeed for real (the firewall adapter is hardcoded to simulation regardless of `INTEGRATION_MODE`). Replace with a version that either (a) calls the same protected-target guard the queue path uses, or (b) is explicitly merged into the queue path so there is one `block_ip` implementation, not two.
- **`monitor` / `flag_high_priority`** — **MERGE.** Both are indistinguishable no-op log stubs. Collapse into a single `annotate`/`tag_alert` primitive, or retire both in favor of a real "flag for analyst review" action that actually sets a field analysts can filter on (today `flag_high_priority` sets nothing an analyst-facing view reads).
- **Response action queue path (`soar_enqueue_orchestrator` → `response_actions_queue` → `soar_action_worker`)** — **KEEP WITH IMPROVEMENTS, pending a consolidation decision.** Its safety modeling (protected targets, approval-required-action set, real `retry_count` incrementing) is arguably better than the playbook engine's equivalent. The two paths should not keep evolving independently — see Architectural Recommendations.
- **`playbook_schedules`** — **RETIRE OR FINISH.** As shipped it is unused API surface: full CRUD, no consumer. Either wire a scheduler consumer or remove the table/routes so the project doesn't present nonfunctional surface area as a feature.
- **Canonical response outcome model** — **KEEP.** No changes recommended; this is the piece most worth highlighting unprompted in an interview.
- **Legacy outcome inference module (`soar_response_outcomes_legacy.py`)** — **KEEP**, scoped as a backfill/read-compat shim. Revisit for retirement only once a backfill pass confirms every historical record has a canonical decision linked.
- **MITRE tagging** — **KEEP WITH IMPROVEMENTS.** Fine as a reporting/display feature; misleading if left unlabeled. At minimum, document (in-app or in the demo narrative) that it is a static lookup, not attack-technique detection logic, and consider exposing `mitre_technique_id` as an optional playbook trigger key so technique-based automation becomes possible later.

## 5. Missing Playbooks

Every entry below is grounded in an alert type, correlation type, or capability that already exists in this codebase (cited), so none of this requires inventing new detection logic unless explicitly noted as a dependency.

### 5.1 Brute-force containment
- **SOC problem:** Repeated failed logins from one source should be contained before an account is compromised, not just logged.
- **Trigger:** `alert_type = "failed_login_threshold"` (exists, `engines/detection_engine.py`), `min_severity` medium+.
- **Enrichment required:** AbuseIPDB reputation (already computed at ingest, `alerts.reputation_score`).
- **Automation steps:** flag alert → (if `reputation_score` above threshold) require_approval(risk=medium) → block_ip → notify_slack.
- **Approval:** required before containment (medium risk).
- **Response actions:** `flag_high_priority` (replacement), `require_approval`, `block_ip` (replacement), `notify_slack`.
- **Interview value:** high — the canonical "here's a SOAR playbook" example, easy to narrate end-to-end.
- **Implementation complexity:** Small.
- **Dependencies:** fixed `block_ip` primitive (§4).

### 5.2 Password spraying investigation
- **SOC problem:** Low-and-slow credential attacks across many accounts need investigation, not just a threshold alert.
- **Trigger:** `alert_type = "password_spraying_threshold"` (exists, `engines/correlation_engine.py`).
- **Enrichment required:** source-IP reputation + source-IP context (existing Source-IP Context API).
- **Automation steps:** monitor/annotate → notify_slack with source-IP context link → no automatic containment (investigation-only).
- **Approval:** none (enrichment-only, no destructive action).
- **Response actions:** `notify_slack`, annotate.
- **Interview value:** medium-high — demonstrates restraint (not every alert should auto-block).
- **Implementation complexity:** Small.
- **Dependencies:** none new.

### 5.3 Success-after-spray response
- **SOC problem:** A successful login following a spray pattern is a near-certain compromise and should get the strongest automated response in the library.
- **Trigger:** `alert_type = "successful_login_after_spray"` / correlation_type `spray_then_success_pattern` (both exist, `engines/correlation_engine.py`).
- **Enrichment required:** account/user identity from the alert payload, reputation.
- **Automation steps:** flag critical → require_approval(risk=critical) → block_ip → notify_slack + notify_email (escalation).
- **Approval:** required, critical risk, short TTL.
- **Response actions:** all four non-notify primitives plus two notification channels.
- **Interview value:** very high — best "why this matters" narrative in the whole set (uses an actual correlation feature already built).
- **Implementation complexity:** Small.
- **Dependencies:** fixed `block_ip` primitive.

### 5.4 Malicious IP containment (high-confidence IOC response)
- **SOC problem:** A source IP already known-bad (via reputation feed) should be actioned faster/harder than a first-seen IP.
- **Trigger:** `reputation_score_min` trigger key (already supported in `playbook_engine.py`) combined with `alert_type = "correlated_activity"` or any alert carrying a high `reputation_score`.
- **Enrichment required:** AbuseIPDB (already at ingest).
- **Automation steps:** block_ip (no approval gate — this is the one case where skipping the gate is defensible given confidence) → notify_slack.
- **Approval:** none, given sufficiently high confidence threshold — worth calling out explicitly as a deliberate design choice in the playbook description so it doesn't read as an oversight.
- **Response actions:** `block_ip` (replacement), `notify_slack`.
- **Interview value:** high — a good prompt to discuss when auto-remediation without human approval is/isn't appropriate.
- **Implementation complexity:** Small.
- **Dependencies:** fixed `block_ip` primitive.

### 5.5 Enrichment-only investigation workflow
- **SOC problem:** Many alerts need context gathering, not action — a playbook that only enriches and hands off to an analyst.
- **Trigger:** any alert type, low/medium severity.
- **Enrichment required:** reputation + source-IP context.
- **Automation steps:** annotate with enrichment output → notify_slack (analyst channel) → no containment.
- **Approval:** none.
- **Response actions:** annotate, `notify_slack`.
- **Interview value:** medium — demonstrates that not everything needs a block action.
- **Implementation complexity:** Small. **Dependency:** none new, but highlights the gap in §9 (no `enrich_ip` step type exists — this would currently have to be faked as a `monitor` step with no real enrichment output attached).

### 5.6 Ransomware early response
- **SOC problem:** Rapid file-modification/encryption indicators need the fastest, most conservative response in the library.
- **Trigger:** would require a new alert type (e.g., mass file-write rate) — **not present today**.
- **Enrichment required:** host identity, affected file count.
- **Automation steps:** flag critical → require_approval(risk=critical, short TTL) → isolate host (new action, not `block_ip`) → notify_email + notify_slack.
- **Approval:** required, critical.
- **Response actions:** new `isolate_host` primitive, notifications.
- **Interview value:** very high — but honest framing matters: this requires new detection input this project does not currently ingest (no EDR/file-integrity telemetry source).
- **Implementation complexity:** Large.
- **Dependencies:** new detection source/alert type; new `isolate_host` action; likely a new ingestion adapter.

### 5.7 Suspicious PowerShell investigation
- **SOC problem:** Living-off-the-land technique investigation.
- **Trigger:** requires host/process telemetry — **not present today** (this SIEM currently ingests bank_app/web_log/Azure/OTLP/honeypot sources, no endpoint/process telemetry).
- **Interview value:** high in concept, but should be framed as a roadmap item requiring a new ingestion source, not something buildable on current data.
- **Implementation complexity:** Large. **Dependencies:** endpoint telemetry ingestion adapter (does not exist).

### 5.8 Impossible travel investigation
- **SOC problem:** Same-identity logins from geographically implausible locations in a short window.
- **Trigger:** requires geolocation + identity correlation over time — partially possible (honeypot backfill already does IP geolocation, `scripts/backfill_honeypot_locations.py`) but no existing alert_type encodes "impossible travel."
- **Enrichment required:** IP geolocation (exists), identity/session correlation (does not exist as a first-class join).
- **Automation steps:** flag high → require_approval(high) → force session/credential action (new action) → notify.
- **Interview value:** high — good "gap I identified" talking point.
- **Implementation complexity:** Medium-large. **Dependencies:** new correlation rule joining geolocation + identity + time window; no session/credential-revocation action exists today.

### 5.9 Privileged account monitoring
- **SOC problem:** Admin/privileged account activity warrants a different (stricter) automated posture than a normal user.
- **Trigger:** would need an `is_privileged_account` flag on identity data — **not present today**; `honeypot_admin_probe_threshold` exists but that is honeypot admin-path probing, not real privileged-account activity monitoring.
- **Interview value:** medium — valuable to name as a gap even without building it.
- **Implementation complexity:** Medium. **Dependencies:** identity/role metadata not currently modeled for real (non-honeypot) accounts.

### 5.10 Repeated malware detections
- **SOC problem:** Same malware signature/hash recurring across hosts indicates spread, not isolated incidents.
- **Trigger:** requires malware/AV telemetry — **not present today** (no AV/EDR ingestion source).
- **Interview value:** medium. **Implementation complexity:** Large. **Dependencies:** new ingestion source.

### 5.11 Suspicious outbound traffic / beaconing investigation
- **SOC problem:** Regular-interval outbound connections to a single destination suggest C2 beaconing.
- **Trigger:** would need network flow telemetry with timing analysis — closest existing signal is `high_request_rate_threshold` / `http_error_threshold`, but neither currently encodes periodicity.
- **Interview value:** high in concept (a strong "what I'd build next" answer), but honestly a **new detection capability**, not a playbook gap.
- **Implementation complexity:** Large. **Dependencies:** periodicity/beaconing detection logic (does not exist); no such rule currently in `correlation_engine.py`.

### 5.12 Suspicious process investigation
- Same dependency gap as §5.7 (no endpoint/process telemetry source). List for roadmap completeness; not independently buildable today.

### 5.13 Suspicious authentication chains
- **SOC problem:** A sequence of auth events across services (e.g., failed → password reset → success) is more suspicious as a chain than any single event.
- **Trigger:** would combine `failed_login_threshold` + a password-reset event type — **reset events are not currently ingested/modeled**.
- **Interview value:** medium-high as a concept. **Implementation complexity:** Medium. **Dependencies:** password-reset/account-change event ingestion (does not exist).

### 5.14 Threat hunting helper workflow
- **SOC problem:** On-demand playbook an analyst triggers manually to pull enrichment + related alerts for a given IP/user, not tied to an automatic trigger.
- **Trigger:** manual invocation only — **the playbook engine currently has no "run this playbook against an arbitrary target" entry point**, only automatic ingest-time matching and failed-execution retry (`routes/playbook_routes.py`).
- **Enrichment required:** reputation, source-IP context.
- **Interview value:** high — directly demonstrates SOC-analyst-centric thinking, and surfaces a real product gap (no manual/ad hoc playbook trigger route exists today).
- **Implementation complexity:** Medium. **Dependencies:** a new manual-trigger API surface (does not exist).

### 5.15 Analyst evidence collection
- **SOC problem:** Capture a durable, exportable snapshot of everything known about an alert/incident at time of investigation.
- **Trigger:** manual, from an alert or incident view.
- **Enrichment required:** all existing enrichment (reputation, MITRE tag, source-IP context, related alerts).
- **Automation steps:** collect + snapshot → attach to incident record → (optionally) notify.
- **Interview value:** high — pairs well with the existing PDF reporting helpers (`helpers/reporting_helpers.py`, `helpers/pdf_helpers.py`), which already assemble similar content for reports.
- **Implementation complexity:** Medium. **Dependencies:** an evidence-snapshot data model (does not exist); can reuse existing reporting helpers as a base.

### 5.16 Automated case enrichment
- **SOC problem:** New incidents should be pre-populated with reputation/MITRE/related-alert context automatically, not left for an analyst to gather by hand.
- **Trigger:** incident creation.
- **Interview value:** medium-high — a natural extension of existing MITRE/reputation helpers, currently only invoked at alert-list/report time, not at incident-creation time.
- **Implementation complexity:** Small-medium. **Dependencies:** none new; wiring only.

### 5.17 Response approval workflows (beyond current single-gate model)
- **SOC problem:** Real SOCs often need multi-approver or escalating approval (e.g., analyst → team lead → on-call), not a single flat gate.
- **Trigger:** N/A — this is a capability gap, not a playbook. See Missing SOAR Capabilities §6.
- **Interview value:** high to discuss; not buildable as "a playbook" — it is an approval-model gap.

### 5.18 Playbook chaining
- **SOC problem:** Complex incidents need one playbook's output to hand off into another (e.g., containment playbook triggers an evidence-collection playbook).
- **Trigger:** N/A — capability gap, not a playbook. See §6.

Items §5.17 and §5.18 are intentionally listed here per the audit request but are structural capabilities, not individually authorable playbooks — they are cross-referenced into the Missing SOAR Capabilities section rather than double-specified.

## 6. Missing SOAR Capabilities

Facts only; no implementation proposed.

- **Orchestration across two automation paths.** The playbook engine and the response action queue are separately triggered from the same ingest event (`routes/ingest_routes.py` calls both `enqueue_committed_alerts` and `create_pending_executions_for_committed_alerts`) with no shared decision layer. There is no single place that decides "this alert gets exactly one response path."
- **Playbook chaining.** No mechanism for one playbook's completion to trigger another. `playbook_executions` has no parent/child or "chained_from" linkage.
- **Reusable playbook actions.** The seven actions in `SUPPORTED_ACTIONS` are the only vocabulary; there is no plugin/registration mechanism for adding a new action without touching both the registry and the executor's dispatch table by hand, and no shared step "library" concept beyond that fixed set.
- **Reusable enrichment steps.** Enrichment (reputation, MITRE, source-IP context) happens at ingest time or in unrelated read routes — never as a composable step inside a playbook. There is no `enrich` action.
- **Reusable investigation stages.** No concept of a shared sub-sequence of steps reusable across multiple playbook definitions; every playbook's `steps` JSON is fully self-contained and duplicated if reused.
- **Analyst checkpoints (beyond binary approve/deny).** `require_approval` is the only checkpoint primitive; there's no "pause for analyst annotation" step that doesn't also gate on approve/deny.
- **Incident timelines.** `playbook_executions.steps_log` and `soar_response_outcome_events` each provide a timeline for a single execution/decision, but there is no cross-execution, cross-alert incident-level timeline view stitching multiple playbook runs, queue actions, and manual actions into one chronological narrative.
- **Evidence collection.** No data model or action captures a durable, attachable evidence snapshot tied to an incident (see §5.15).
- **Rollback support.** Confirmed absent everywhere (§ audit finding: no compensating/undo action, `unblock_ip`/`tag_ip` exist on the firewall adapter class but are unreachable through the playbook registry, which only recognizes `block_ip`).
- **Conditional branching.** Confirmed strictly linear (`playbook_step_executor._process_steps` is a flat index walk); the only non-linear behavior is the approval-gate pause/resume and the binary `on_failure: abort|continue`.
- **Multi-stage workflows spanning playbooks.** Not supported — an execution belongs to exactly one playbook definition for its whole lifecycle.
- **Execution metrics beyond current dashboard.** A metrics dashboard exists (`SoarMetricsDashboard`/`routes/metrics_routes.py`, per prior spec work) — this audit did not find gaps here beyond what's already tracked; noted as adequately covered, not a gap.
- **Execution history / long-term retention semantics.** `steps_log`/outcome events are retained indefinitely with no reviewed retention policy found in this pass (response outcome retention has its own dedicated test file, `tests/test_response_outcome_retention.py`, suggesting this was considered for the outcome model specifically — but not confirmed for `playbook_executions.steps_log` itself).
- **Idempotency improvements.** Notification delivery and step-log replay are idempotency-guarded; `attempt_count` on `playbook_executions` is modeled but never incremented, so the "requeue vs. permanently fail" decision in `mark_stale_execution_for_recovery` is effectively dead logic (always requeues).

## 7. Architectural Recommendations

(Direction, not implementation — no code changes authorized by this document.)

1. **Resolve the dual-path duplication first.** Before adding a single new playbook, decide whether the response action queue (`soar_enqueue_orchestrator`/`soar_action_worker`) is (a) merged into the playbook engine as its execution backend, (b) kept as a permanently separate "fast path" with an explicit, documented boundary of which alerts go where, or (c) retired in favor of the playbook engine alone. Whichever direction, the two paths must not keep independently implementing overlapping actions (`block_ip`) with different safety guarantees.
2. **Author a small, real playbook set before adding engine features.** §5.1–5.4 are buildable today with zero new detection work. This is higher interview value than any further engine investment, because it's the part a walkthrough actually demos.
3. **Close the specific correctness gaps found in this audit** independent of any larger redesign: `notify_teams` registry/executor mismatch, dead `attempt_count`, playbook `block_ip` missing the protected-target check the sibling system has, and the unused `playbook_schedules` surface.
4. **Treat conditional branching as the next engine capability, not chaining.** Branching unlocks realistic single-playbook logic (e.g., "if reputation high, skip approval"); chaining (playbook-to-playbook) is a bigger structural change and should come after there are enough real playbooks to make chaining meaningful.
5. **Keep enrichment at ingest time; add a narrow read-only "enrichment snapshot" step rather than a live re-query action**, to avoid adding external API calls (AbuseIPDB) into the execution hot path and its rate-limit/circuit-breaker surface unnecessarily.

## 8. Prioritized Roadmap

Value and effort are independent axes; both are given per item.

| # | Item | Value | Effort |
|---|---|---|---|
| 1 | Fix playbook `block_ip` to enforce the protected-target check (align with the queue path) | High | Small |
| 2 | Author brute-force containment playbook (§5.1) | High | Small |
| 3 | Author success-after-spray response playbook (§5.3) | High | Small |
| 4 | Author malicious-IP containment playbook (§5.4) | High | Small |
| 5 | Fix `notify_teams` registry/executor mismatch | Medium | Small |
| 6 | Wire or remove `attempt_count` (make the retry-eligibility branch reachable, or delete the dead columns/logic) | Medium | Small |
| 7 | Decide and document the dual-path (playbook engine vs. response action queue) relationship | High | Medium |
| 8 | Author password-spraying investigation + enrichment-only playbooks (§5.2, §5.5) | Medium | Small |
| 9 | Remove or finish `playbook_schedules` (currently dead surface) | Medium | Small |
| 10 | Add conditional/branching primitive to the step executor | High | Medium |
| 11 | Add a manual/ad hoc playbook trigger route (threat hunting helper, §5.14) | Medium | Medium |
| 12 | Automated case enrichment on incident creation (§5.16) | Medium | Small-Medium |
| 13 | Analyst evidence collection (§5.15) | Medium | Medium |
| 14 | Impossible travel investigation (§5.8) — needs new correlation rule first | Medium | Medium-Large |
| 15 | Multi-approver / escalating approval workflow (§5.17) | Medium | Large |
| 16 | Playbook chaining (§5.18) | Medium | Large |
| 17 | Ransomware early response, suspicious PowerShell/process investigation, beaconing (§5.6, §5.7, §5.11, §5.12) | High (concept) | Large — blocked on new ingestion sources not yet built |
| 18 | Privileged account monitoring, suspicious auth chains, repeated malware detections (§5.9, §5.10, §5.13) | Medium (concept) | Large — blocked on identity/AV telemetry not yet modeled |

## 9. Risks

- **Demo risk:** presenting the SOAR system today without disclosing that zero playbooks are populated risks an interviewer discovering an empty list live. This audit should be treated as a prerequisite to any demo, not a nice-to-have.
- **Safety-parity risk:** as long as two paths can both act on `block_ip`-class alerts with different guardrails, a future change to one path's safety logic (e.g., tightening the protected-target list) can silently fail to apply to the other.
- **Dead-logic risk:** the unincremented `attempt_count` means the stale-execution recovery "give up after N attempts" branch has never been exercised in practice; if it's ever relied upon operationally, it will not behave as documented in `docs/`.
- **Scope-creep risk:** several "missing playbook" ideas (ransomware response, PowerShell/process investigation, beaconing) are genuinely blocked on ingestion sources this project does not have. Treating them as playbook backlog items rather than "needs new detection capability first" items risks under-scoping future work.
- **Documentation/reality drift risk:** `playbook_schedules` is fully documented and API-exposed but functionally inert; anyone reading the schema or API surface without reading the worker code would reasonably but incorrectly assume scheduled playbooks work.

## 10. Future Implementation Strategy

Recommended sequencing for turning this audit into real OpenSpec changes:

1. A small, tightly scoped change to fix the correctness gaps in Roadmap items 1, 5, 6 — no new features, pure hardening, and cheap enough to do before anything else.
2. A decision-and-documentation change (not necessarily code) for Roadmap item 7 (dual-path relationship) — this should be resolved as a design decision before playbook authoring compounds the duplication.
3. A "first playbook pack" change covering Roadmap items 2–4 and 8 — concrete, demoable playbooks against alert types that already exist, no engine changes required.
4. An engine-capability change for conditional branching (Roadmap item 10), scoped narrowly (e.g., a single `condition` step type keyed on prior step output or alert fields) before considering chaining.
5. Everything blocked on new ingestion sources (Roadmap item 17–18) should be deferred to a separate ingestion-capability initiative and explicitly not bundled into playbook-library work.

Each of the above should become its own OpenSpec change with its own proposal/design/tasks/spec — this document is the map, not the implementation.

## Open Questions

- Should the response action queue be merged into the playbook engine, kept as a documented separate fast path, or retired? (Roadmap item 7 — a decision, not a code question, and it should be made before further playbook authoring.)
- Is `playbook_schedules` worth finishing (a real scheduler consumer) or should it be removed as dead surface?
- Should `block_ip` gain a real (non-simulated) execution mode at all, given the firewall adapter is currently hardcoded to simulation-only by design (per SPEC-INTEG-005's permanent firewall boundary)? If firewall real-mode stays permanently out of scope, playbook `block_ip` recommendations above should be re-read as "fix the simulated safety-check parity," not "make it real."
