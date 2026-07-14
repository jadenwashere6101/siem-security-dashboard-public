## ADDED Requirements

### Requirement: Playbook triggers may exclude owned alert types
The playbook trigger language SHALL support an optional `exclude_alert_types` field so a generic playbook can explicitly decline alert types that are already owned by dedicated playbooks.

#### Scenario: Excluded alert type fails the trigger
- **WHEN** a playbook definition has `trigger_config.exclude_alert_types` containing the triggering alert's `alert_type`
- **THEN** the playbook engine SHALL treat the trigger as non-matching for that alert, even if all other trigger fields would otherwise match.

#### Scenario: Non-excluded alert types still use existing trigger semantics
- **WHEN** a playbook definition has `exclude_alert_types` and the triggering alert's `alert_type` is not in that list
- **THEN** the playbook engine SHALL evaluate the remaining recognized trigger fields using the existing AND semantics and produce the same result it would have produced without the exclusion list.

### Requirement: Exclusion lists are validated explicitly
The playbook definition validation path SHALL validate `exclude_alert_types` as a structured trigger field and SHALL reject malformed exclusion lists with an explicit validation error.

#### Scenario: Valid exclusion list is accepted
- **WHEN** a playbook definition is created or updated with `trigger_config.exclude_alert_types` set to an array of non-empty alert-type strings
- **THEN** the definition save SHALL accept that field without requiring any database migration or additional trigger fields.

#### Scenario: Invalid exclusion list is rejected
- **WHEN** a playbook definition is created or updated with `trigger_config.exclude_alert_types` set to a non-array value, an empty-string member, or a non-string member
- **THEN** the definition save SHALL fail with a validation error that identifies `exclude_alert_types` as invalid.

### Requirement: Exclusion matching is case-insensitive
Alert-type exclusion matching SHALL compare values case-insensitively, consistent with existing `alert_type` trigger matching.

#### Scenario: Case differences do not bypass exclusions
- **WHEN** a playbook definition excludes `PFSENSE_FIREWALL_PORT_SCAN` and the triggering alert's `alert_type` is `pfsense_firewall_port_scan`
- **THEN** the playbook engine SHALL treat the alert type as excluded and SHALL NOT match the playbook.

### Requirement: Exclusions prevent overlap without changing other trigger meaning
Adding `exclude_alert_types` SHALL narrow playbook eligibility only for the explicitly excluded alert types and SHALL NOT change the meaning of `alert_type`, `min_severity`, `source`, `correlation_flag`, or `reputation_score_min`.

#### Scenario: Existing trigger fields keep their current behavior
- **WHEN** a playbook definition does not use `exclude_alert_types`
- **THEN** the playbook engine and definition-save behavior for the existing trigger fields SHALL remain unchanged.
