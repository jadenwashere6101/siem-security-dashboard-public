## MODIFIED Requirements

### Requirement: Version 1 Playbook Set
The project SHALL define exactly five Version 1 playbooks — Brute Force Containment, Password Spray Investigation, Successful Login After Spray Response, Malicious IP Containment, and Reputation-Only Investigation — each specified with a trigger, purpose, step-by-step flow, the existing engine actions it uses, dynamic parameter bindings where required, its approval requirement, its expected outcome, and its justification for inclusion in Version 1. The Reputation-Only Investigation trigger SHALL remain broadly reusable across alert types, but it SHALL explicitly exclude alert types already owned by dedicated playbooks when such overlap would otherwise create duplicate playbook execution.

#### Scenario: Every playbook targets a real, existing trigger
- **WHEN** a Version 1 playbook's trigger is read
- **THEN** it SHALL reference only `alert_type`, `min_severity`, `source`, `correlation_flag`, `reputation_score_min`, or `exclude_alert_types` values that correspond to alert types or thresholds already produced by `engines/detection_engine.py` or `engines/correlation_engine.py` today.

#### Scenario: Containment playbooks use dynamic block_ip
- **WHEN** a Version 1 playbook's purpose requires blocking the offending source IP (Brute Force Containment, Successful Login After Spray Response, Malicious IP Containment)
- **THEN** its approved `block_ip` step SHALL bind `params.source_ip` to `{{alert.source_ip}}` (or equivalent syntax defined by `dynamic-playbook-parameter-binding`), not a static IP literal.

#### Scenario: Investigation playbooks omit block_ip by design
- **WHEN** Password Spray Investigation or Reputation-Only Investigation is read
- **THEN** it SHALL NOT include a `block_ip` step — not because of engine limitation, but because spray and low-tier reputation signals warrant investigation without automatic blocking.

#### Scenario: Reputation-Only Investigation excludes dedicated pfSense alert types
- **WHEN** the seeded Version 1 Reputation-Only Investigation playbook is reviewed
- **THEN** its trigger SHALL exclude `pfsense_firewall_port_scan`, `pfsense_firewall_repeated_deny`, and `pfsense_firewall_suspicious_allow` so those alert types remain owned by their dedicated pfSense playbooks rather than also matching the generic reputation playbook.

#### Scenario: Unowned pfSense alert types remain eligible for generic reputation review
- **WHEN** a pfSense alert type does not have a dedicated pfSense playbook owner, such as `pfsense_firewall_noisy_source`
- **THEN** the seeded Reputation-Only Investigation playbook SHALL remain eligible to match it when the alert satisfies the playbook's severity and reputation criteria.
