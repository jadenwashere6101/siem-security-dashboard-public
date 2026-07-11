## 1. Mac AI Phase 1 — Filtering Foundation

- [x] 1.1 Reconfirm the audited listener-to-route-to-ingest call graph and capture focused baseline tests before changing behavior.
- [x] 1.2 Add the `pfsense_ingest_config` migration, deterministic default rows, constraints, indexes, rollback behavior, and matching schema snapshot updates without creating a second configuration source.
- [x] 1.3 Implement the effective-policy repository/service with per-request reads, strict boolean and sensitive-port validation, transactional updates, and safe code-default fallback when stored configuration is missing, invalid, or unavailable.
- [x] 1.4 Implement a pure, unit-tested policy evaluator with documented OR precedence for block, inbound sensitive-port allow, all allow, DNS port-53, and ICMP categories.
- [x] 1.5 Place the policy decision after normalized-event validation and before geolocation and `ingest_normalized_event()`, returning a distinct filtered outcome and proving filtered events cannot enter storage or downstream processing.
- [x] 1.6 Replace duplicated sensitive-port constants with one canonical validated configuration used by both retention policy and suspicious-allow detection, preserving the approved default union.
- [x] 1.7 Extend the pfSense parser and normalized-event validation only as needed for common IPv4 ICMP filterlog records, while retaining all blocked ICMP and applying the ICMP toggle only to allowed ICMP.
- [x] 1.8 Update listener backend-response classification and bounded counters so forwarded, filtered, rejected, ingested, and backend-failed outcomes remain distinct.
- [x] 1.9 Add focused parser, validator, policy, route-ordering, fail-safe, canonical-port, detector, response-contract, counter, and no-secondary-storage regression tests.

## 2. Mac AI Phase 2 — Administration and End-to-End Verification

- [x] 2.1 Add super-admin-only effective-policy read and validated update APIs using existing RBAC, error, transaction, and response conventions.
- [x] 2.2 Emit existing-format audit records for successful configuration changes with actor and safe old/new values, and verify denied or failed updates cannot change policy.
- [x] 2.3 Expose bounded aggregate decision counts, reason counts, fallback state, and listener outcome statistics without persisting raw dropped events or sensitive payloads.
- [x] 2.4 Add the Administration service client and panel with toggles for block events, inbound sensitive-port allows, all allows, DNS port-53 traffic, and allowed ICMP plus a validated canonical sensitive-port editor.
- [x] 2.5 Make the panel accurately explain precedence, inbound scope, DNS port-53 semantics, restartless effect, safe-default fallback, validation failures, permissions, loading, and save results.
- [x] 2.6 Add API authorization/audit tests and focused React service/component tests covering each control, invalid ports, fallback display, failure states, and role restrictions.
- [x] 2.7 Run a local end-to-end retained/filtered matrix and prove geolocation, event inserts, detections, and other downstream work occur only for retained events.
- [x] 2.8 Run affected backend suites, frontend tests, production build, migration/schema verification, dark-theme/spacing/accessibility review, strict OpenSpec validation, and `git diff --check`.
- [x] 2.9 Produce a VM handoff containing the approved commit requirement, exact migration/deploy commands, defaults, synthetic fixtures and expected outcomes, counter/DB queries, fallback checks, restartless checks, and rollback procedure.
