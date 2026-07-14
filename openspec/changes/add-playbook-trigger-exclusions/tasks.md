## 1. Trigger Capability

- [x] 1.1 Add `exclude_alert_types` recognition to the playbook trigger matcher with case-insensitive alert-type exclusion semantics.
- [x] 1.2 Add narrow trigger-config validation for `exclude_alert_types` in the playbook definition write path without redesigning other trigger semantics.

## 2. Seeded Consumer Update

- [x] 2.1 Update `core-v1-reputation-investigation` to exclude `pfsense_firewall_port_scan`, `pfsense_firewall_repeated_deny`, and `pfsense_firewall_suspicious_allow`.
- [x] 2.2 Verify the seeded generic reputation playbook still matches legitimate non-excluded alert types, including non-pfSense alerts and `pfsense_firewall_noisy_source`.

## 3. Verification

- [x] 3.1 Add matcher tests covering exclusion hits, non-excluded matches, case-insensitive comparison, and invalid exclusion config behavior.
- [x] 3.2 Add playbook route or store validation tests for accepted and rejected `exclude_alert_types` payloads.
- [x] 3.3 Add core playbook pack regression tests proving the dedicated pfSense alert types no longer match the generic reputation playbook while other intended matches remain unchanged.
- [x] 3.4 Run focused affected backend tests, `openspec validate add-playbook-trigger-exclusions --strict`, and `git diff --check`.
