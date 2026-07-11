## ADDED Requirements

### Requirement: Non-destructive runtime Blocklist remediation
Runtime remediation SHALL classify matching records before action and SHALL use only the canonical supported removal workflow.

#### Scenario: Runtime record classification
- **WHEN** VM AI is explicitly authorized to inspect a target IP
- **THEN** it SHALL verify the clean approved deployment and classify every match as active, expired, historical, removed, protected, or unknown using sanitized read-only evidence

#### Scenario: Authorized applicable removal
- **WHEN** a matching record is active, non-protected, unambiguous, and the user separately authorizes mutation
- **THEN** VM AI SHALL invoke the supported removal workflow once, preserve historical rows, append canonical registry/audit evidence, and verify no unrelated records changed

#### Scenario: Unsafe or unnecessary removal
- **WHEN** the record is terminal, protected, ambiguous, the VM is dirty, or the deployed SHA is unapproved
- **THEN** VM AI SHALL stop without mutation and report the blocking classification

### Requirement: Removal outcome truth
Blocklist tracking removal SHALL remain distinct from firewall or external enforcement.

#### Scenario: Removal succeeds
- **WHEN** canonical `remove_tracking` succeeds
- **THEN** the resulting API and UI state SHALL describe inactive SIEM tracking and preserved history and SHALL NOT claim that an external firewall rule was removed

