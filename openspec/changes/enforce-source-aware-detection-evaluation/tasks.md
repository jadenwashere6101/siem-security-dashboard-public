## 1. Contract and Inventory — Mac AI

- [x] 1.1 Reconfirm the 15 base rule IDs in `get_detection_rule_defaults()` match the normative applicability matrix before editing source.
- [x] 1.2 Add canonical source-pair constants and immutable per-rule applicability/classification metadata in a focused backend module.
- [x] 1.3 Add completeness and exact-match tests proving every base rule has coverage and unknown, blank, case-variant, and mismatched pairs fail closed.
- [x] 1.4 Document in code that applicability is read-only code metadata while thresholds/windows remain global runtime configuration.

## 2. Execution Gate and Active Enforcement — Mac AI

- [x] 2.1 Refactor normalized-ingest detector fan-out into explicit rule candidates without changing event-type behavior or execution order.
- [x] 2.2 Gate every candidate on exact source applicability and effective `active` before invoking detector SQL.
- [x] 2.3 Ensure direct detector entry paths use the shared guard or require a validated evaluation context so unsupported/inactive calls cannot bypass policy.
- [x] 2.4 Add focused tests proving inactive and unsupported rules perform no historical aggregation, create no alerts, and do not prevent event storage or unrelated supported detectors.

## 3. Source-Isolated Detection Queries — Mac AI

- [x] 3.1 Constrain failed-login, password-spraying, and successful-after-spray aggregation, temporal joins, and evidence lookups to current source IP and exact source pair.
- [x] 3.2 Constrain generic port-scan, HTTP-error, application-exception, and high-request-rate aggregation and evidence lookups to current source IP and exact source pair.
- [x] 3.3 Constrain all four honeypot detectors and their evidence/location lookups to current source IP and `honeypot/honeypot`.
- [x] 3.4 Constrain all four pfSense detectors and their evidence/location lookups to current source IP and `pfsense/firewall` without changing sensitive-port, escalation, or noisy-source policy.
- [x] 3.5 Preserve duplicate-open-alert behavior while ensuring alert `source` and `source_type` come from the evaluated pair rather than unrelated triggering context.
- [x] 3.6 Add adversarial same-IP fixtures proving supported sources cannot combine thresholds/sequences and unsupported history cannot contribute or be falsely attributed.
- [x] 3.7 Add positive coverage proving every allowed matrix pair still triggers its applicable rules with existing default and overridden thresholds/windows.

## 4. Detection Configuration and API — Mac AI

- [x] 4.1 Extend effective rule responses with deterministic classification and applicable-source metadata from the centralized registry, including fallback responses.
- [x] 4.2 Update the super-admin PATCH contract to accept parameters, active, or both; validate strict booleans; preserve omitted values; and reject applicability mutations.
- [x] 4.3 Persist active state in the existing `detection_config` upsert and include old/new active state and parameter changes in audit evidence.
- [x] 4.4 Add API/config regression tests for list metadata, disable/re-enable behavior, retained global overrides, invalid inputs, RBAC, audit logging, and database/config fallback.

## 5. Detection Rules UI — Mac AI

- [x] 5.1 Update the Detection Rules service to send effective active state while preserving parameter updates and existing error handling.
- [x] 5.2 Update `DetectionRulesPanel` to display an accessible active control/status and read-only applicable-source labels without implying per-source tuning.
- [x] 5.3 Add focused service/component tests for active/inactive rendering, coverage rendering, keyboard interaction, save/reload behavior, validation errors, and unchanged parameter editing.
- [x] 5.4 Review the panel in the dark theme for contrast, focus visibility, screen-reader labeling, compact/responsive layout, and practical visual correctness.
- [x] 5.5 Run the focused frontend tests and `npm run build`.

## 6. Correlation and End-to-End Regression — Mac AI

- [x] 6.1 Verify generic `correlated_activity` still requires independently attributed distinct alert types and known sources and remains outside the base applicability registry.
- [x] 6.2 Verify `web_to_app_attack_pattern`, `spray_then_success_pattern`, and `cloud_app_error_pattern` retain existing source groups, windows, order, and duplicate suppression.
- [x] 6.3 Add regression coverage proving mixed raw events cannot manufacture correlation inputs while valid independently attributed alerts still correlate.
- [x] 6.4 Run all focused detection, normalized-ingest, admin API, alert-source, correlation, and SOAR handoff regression tests.

## 7. Schema, Quality, and Handoff — Mac AI

- [x] 7.1 Confirm no migration or schema snapshot change is required and run migration/schema validation appropriate for a backend behavior change.
- [x] 7.2 Review the final diff for preserved RBAC, audit logging, transaction boundaries, idempotency, duplicate suppression, fail-closed behavior, source evidence, and intentionally cross-source correlation.
- [x] 7.3 Run `git diff --check` and `openspec validate enforce-source-aware-detection-evaluation --strict`.
- [x] 7.4 Produce a Mac-to-VM handoff with expected commit, affected services/artifact, sanitized smoke cases, rollback instructions, and explicit unresolved risks; do not commit or push without authorization.

## 8. Deployment and Production Verification — VM AI

- [ ] 8.1 After explicit deployment authorization, verify the VM worktree is clean, record the approved commit, fetch, and synchronize only through the source-of-truth policy.
- [ ] 8.2 Run the deployment helper's migration dry-run even though no migration is expected, restart only affected backend services, deploy the Mac-built frontend artifact, and verify health/status.
- [ ] 8.3 Using authorized synthetic data and fresh IPs, verify one supported source per rule family still detects, unsupported/mixed sources do not contribute, and `active=false` prevents detection without blocking ingestion.
- [ ] 8.4 Verify generic and targeted cross-source correlation still works from accurately attributed alerts and that Detection Rules shows matching active state and source coverage.
- [ ] 8.5 Restore any active-state changes made for smoke testing, capture sanitized audit/runtime evidence, confirm rollback readiness, and report production outcomes without modifying durable source on the VM.
