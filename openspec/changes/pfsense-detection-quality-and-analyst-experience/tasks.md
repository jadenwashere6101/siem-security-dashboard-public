This spec's authoring step (creating proposal.md/design.md/tasks.md/specs/) makes no code changes. Section 1 reflects the verification work completed to write this spec (folded in from the prior detection-noise and operational-reliability audits, re-confirmed directly against code). Section 2 lists this spec's own future implementation work, to be executed only in a separate, later, explicitly-requested implementation pass, broken into backend/frontend phases.

## 1. Verification (completed as part of writing this spec)

- [x] 1.1 Re-confirm the four pfSense detector functions' exact aggregation logic and thresholds in `engines/detection_engine.py` (`_generate_pfsense_repeated_deny_alerts_core`, `_generate_pfsense_port_scan_alerts_core`, `_generate_pfsense_suspicious_allow_alerts_core`, `_generate_pfsense_noisy_source_alerts_core`).
- [x] 1.2 Confirm `engines/detection_config.py`'s module-level pfSense constants and confirm the `detection_config` table + `routes/admin_routes.py:PATCH /admin/detection-rules/<rule_id>` already provide a live, no-migration threshold override mechanism, scoping this spec to logic (not raw numbers).
- [x] 1.3 Confirm all four detectors dedup only against a currently-`open` alert (`status = 'open'`) with no recently-closed lookback.
- [x] 1.4 Confirm `alerts` (`migrations/0002_base_siem_core.sql`) has no `resolved_at`/`closed_at` column, and confirm `audit_log` (`migrations/0003_auth_rbac_and_metadata.sql`) already records `UPDATE_ALERT_STATUS` events keyed by indexed `target_alert_id`/`created_at`, making a no-migration cooldown lookup feasible.
- [x] 1.5 Confirm all four pfSense playbooks in `core/core_playbook_pack_v1.py` end in an unconditional `notify_slack` step, and confirm investigation-only (`monitor`) and containment (`require_approval` + `block_ip`) playbooks currently carry identical Slack urgency.
- [x] 1.6 Confirm each detector already writes a `context` JSONB field with detection-specific evidence (counts, first/last seen, direction) suitable for a read-only "why this fired" projection with no new data collection.
- [x] 1.7 Confirm no existing endpoint aggregates alert counts by `alert_type`/time for a detection-health/top-firing view.
- [x] 1.8 Document the per-rule improvement plan, migration assessment (audit_log-based cooldown as default, `alerts.resolved_at` as an explicitly-flagged, not-assumed fallback), non-goals, and risks in `design.md`.
- [x] 1.9 Refine Detection Health to a fixed-shape ranked list (rule name linking to `/admin/detection-rules/<rule_id>`, 24-hour fired count, highest severity in window, last-fired timestamp, and an optional deterministic Noisy/Needs Review/Normal badge with fixed cutoffs 20/5), explicitly excluding charts, trend analytics, false-positive scoring, AI-derived judgments, a new rule-management surface, and any duplicate threshold control; re-validated with `openspec validate --strict`.

## 2. Implementation (this spec's own future work — not started, not part of this authoring step)

### Phase A — Backend: Detection Logic Quality (`engines/detection_engine.py`, `engines/detection_config.py`) — IMPLEMENTED

- [x] 2.1 Add a distinct-destination-host dimension to `_generate_pfsense_port_scan_alerts_core` alongside the existing distinct-port count; surface both in `context` and in the alert message. Implemented via a new `host_threshold` rule parameter (`PFSENSE_PORT_SCAN_HOST_THRESHOLD`, default 5) and an `OR COUNT(DISTINCT destination_ip) >= %s` arm on the existing `HAVING` clause, flowing through the existing generic `detection_config` override mechanism.
- [x] 2.2 Change `_generate_pfsense_suspicious_allow_alerts_core` to gate severity on repetition/context instead of hardcoding `severity = "high"` unconditionally. Implemented: high severity now requires known-bad reputation (unchanged path), OR event count meeting the new `high_confidence_repeat_threshold` (default 3), OR distinct sensitive ports touched meeting the new `distinct_port_escalation_threshold` (default 2); otherwise `medium`. `distinct_sensitive_port_count` added to `context`.
- [x] 2.3 Add direction-aware severity/messaging to `_generate_pfsense_repeated_deny_alerts_core` distinguishing LAN→WAN from WAN→LAN denies, without introducing a new `alert_type`. Implemented: `_pfsense_escalated_severity` accepts an optional `direction`; `direction="out"` uses an escalation multiplier of 1 instead of `PFSENSE_SEVERITY_ESCALATION_MULTIPLIER`, and the alert message is distinct for outbound denies.
- [x] 2.4 Add a bounded post-close cooldown check to all four detectors' pre-insert dedup guard, with escalation breakout. Implemented as `_pfsense_cooldown_suppresses()`, querying the most recent `UPDATE_ALERT_STATUS` `audit_log` row per `(source_ip, alert_type)` within `PFSENSE_ALERT_COOLDOWN_MINUTES` (60, new constant) and comparing severity rank; a strictly higher-severity candidate always breaks through.
- [x] 2.5 No migration was needed — the `audit_log` join performed acceptably in the full local regression run (1871 tests, ~171s); flagged fallback (`alerts.resolved_at`) remains undecided/not pursued, reviewed here rather than added silently.
- [x] 2.6 `engines/detection_config.py` rule descriptions updated in place for `pfsense_firewall_port_scan` and `pfsense_firewall_suspicious_allow` to describe the new logic; the generic override mechanism (`validate_detection_rule_config`, `detection_config` table) was not changed.

### Phase B — Backend: Severity/Notification Routing (`core/core_playbook_pack_v1.py`) — IMPLEMENTED

- [x] 2.7 Split notification behavior: the `notify_slack` step was removed from `core-v1-pfsense-repeated-deny-investigation` and `core-v1-pfsense-port-scan-investigation` (both investigation-only, `monitor`-outcome playbooks); their `enrich_context`/`monitor` steps and descriptions are otherwise unchanged. `core-v1-pfsense-port-scan-containment` and `core-v1-pfsense-suspicious-allow-containment` (both `require_approval` + `block_ip`) keep their `notify_slack` step exactly as before — no change to containment Slack timing or content. All non-pfSense playbooks in the pack are untouched.
- [x] 2.8 Confirmed via the existing playbook-execution tests (`test_pfsense_suspicious_allow_containment_pauses_for_approval_then_blocks`, `test_pfsense_suspicious_allow_containment_denied_does_not_block`, `test_pfsense_port_scan_containment_matches_only_high_severity`) that containment approval gating, block execution, and denial handling are unaffected — all pass unchanged.

### Phase C — Backend: Analyst Investigation & Detection Health APIs (new, read-only routes)

- [x] 2.9 Add a read-only "why this fired" projection for pfSense alerts, sourced entirely from the existing `context` JSONB field (no new columns, no new writes).
- [x] 2.10 Add a read-only Detection Health endpoint returning exactly one row per pfSense rule (rule name, 24-hour fired count, highest severity in that window, last-fired timestamp, and the fixed-cutoff Noisy/Needs Review/Normal badge), ranked by 24-hour count descending, computed via aggregation over existing `alerts` rows — no chart data, no trend series, no false-positive/AI-derived fields.
- [x] 2.11 Add regression tests for the Detection Health endpoint's fixed shape and edge cases (no data, single rule, tie-breaking by rule name, each badge boundary at exactly 5 and 20).

### Phase D — Frontend: Alert Investigation UX

- [x] 2.12 Add a "why this fired" section to the pfSense alert detail view consuming Phase C's projection endpoint.
- [x] 2.13 Add a suppression/cooldown indicator on alert detail/list reflecting Phase A's cooldown decision when it suppressed a would-be duplicate.

### Phase E — Frontend: Detection Health Panel

- [x] 2.14 Add a small "Detection Health" ranked-list panel (rule name, 24-hour fired count, highest severity, last-fired timestamp, optional fixed-cutoff badge) consuming Phase C's health endpoint; rule name links to the existing `/admin/detection-rules/<rule_id>` workspace. No chart, no trend view, no new threshold-editing control is built here.
- [x] 2.15 Add focused component tests and a dark-theme/accessibility pass for the new panel and alert-detail additions, per this repo's UI change gate.

### Phase F — Validation (Phase A/B portion complete; Phase C/D/E validation still pending those phases)

- [x] 2.16 Ran the full existing pfSense detection, playbook, ingest, source-aware, and detection-applicability test suites, plus the full repository suite (1871 passed, 3 pre-existing failures confirmed unrelated by reproducing them identically on unmodified `main` via `git stash`). Zero regressions attributable to this change.
- [x] 2.17 Added 8 new focused tests: host-breadth port-scan (few ports/many hosts), 2 direction-aware repeated-deny cases (outbound escalates, inbound unchanged), 2 cooldown tests (suppresses equal-severity recurrence, escalation breaks suppression), and 3 suspicious-allow corroboration cases (uncorroborated-medium, repeat-escalates, distinct-port-escalates) — plus updated 5 existing tests whose expectations changed by design (single-uncorroborated-allow no longer forces high; noisy-source fixture rebalanced to stay under the new host-breadth threshold; ingest-dispatch and high-reputation tests aligned to the new gating).
- [x] 2.18 Ran `openspec validate pfsense-detection-quality-and-analyst-experience --strict` after the Detection Health refinement — valid.
- [x] 2.19 Final Mac closeout completed: full frontend suite passed (`68/68` suites, `858/858` tests), full backend suite finished at `1880 passed / 3 failed` with failures isolated outside this change in `tests/test_alert_mutation_api_contracts.py` and `tests/test_soar_adapter_interface.py`, `npm run build` succeeded with pre-existing warnings in untouched files, `python3 scripts/validate_schema_snapshot.py` confirmed migration `0018`, `python3 -m py_compile ...` passed, `git diff --check` passed, and the final evidence/VM handoff was written to `verification.md`.

## Safety Boundaries (for this authoring step)

- [x] Creating this spec's proposal/design/tasks/spec files makes no changes under `engines/`, `core/`, `routes/`, `migrations/`, `frontend/`, or `tests/`.
- [x] No schema migration is introduced or assumed by this authoring step.
- [x] No existing OpenSpec change or archived spec is modified.
- [x] Do not commit.
- [x] Do not push.
- [x] Do not access the VM.
