## Why

`core-v1-reputation-investigation` is intentionally a generic reputation playbook, but its current trigger only requires `min_severity` and `reputation_score_min`. Because the playbook engine treats absent `alert_type` criteria as match-all, pfSense alerts with elevated reputation also match this generic playbook even when dedicated pfSense playbooks already own those alert types.

That overlap creates duplicate playbook executions, duplicate Slack notifications, and competing automation paths for the same pfSense alert. Muting Slack on one path would only hide one symptom while leaving duplicate execution intact. Raising reputation thresholds would change detection semantics rather than fixing the orchestration boundary. Replacing the generic trigger with a positive `alert_type` allowlist would make the reputation playbook less reusable and force ongoing maintenance as new alert types are added.

The smallest architectural improvement is a narrow trigger-language enhancement that lets a generic playbook explicitly exclude alert types already owned by dedicated playbooks.

## What Changes

- Add `exclude_alert_types` as an optional playbook `trigger_config` field.
- Extend trigger matching so excluded alert types fail the match before the rest of the trigger is evaluated.
- Validate `exclude_alert_types` as a bounded list of non-empty alert-type strings.
- Update `core-v1-reputation-investigation` to exclude the three pfSense alert types already owned by dedicated pfSense playbooks:
  - `pfsense_firewall_port_scan`
  - `pfsense_firewall_repeated_deny`
  - `pfsense_firewall_suspicious_allow`
- Add focused matcher, validation, and seeded-playbook regression tests.
- Document why exclusions are preferred to Slack-only suppression, threshold changes, or positive allowlists.

## Capabilities

### New Capabilities

- `playbook-trigger-exclusions`

### Modified Capabilities

- `core-playbook-pack-v1`

## Impact

- Eliminates duplicate playbook execution for the three dedicated pfSense alert types while preserving generic reputation investigations for all other alert types, including `pfsense_firewall_noisy_source`.
- Keeps the playbook engine as the authoritative orchestration layer without redesigning SOAR or changing database schema.
- Requires backend source and test changes during implementation, plus documentation updates.
- Requires no migration.
