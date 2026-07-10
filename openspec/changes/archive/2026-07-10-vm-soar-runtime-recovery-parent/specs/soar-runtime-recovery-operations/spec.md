## ADDED Requirements

### Requirement: Secret-safe worker recovery
The operator SHALL restore the response-action worker using the authoritative VM secret configuration without exposing secret values or editing source code on the VM.

#### Scenario: Malformed SMTP password is repaired
- **WHEN** the operator corrects the SMTP password assignment
- **THEN** configuration parsing and worker startup SHALL succeed without printing the password and the service SHALL remain healthy across subsequent timer invocations

### Requirement: Verified real-delivery kill-switch
The production runtime SHALL provide one documented authoritative kill-switch whose effective process environment disables all real notification adapters when activated.

#### Scenario: Kill-switch is validated
- **WHEN** the operator activates the kill-switch in a maintenance window
- **THEN** sanitized process evidence and non-delivering checks SHALL prove Slack, Email, Webhook, and Teams real-delivery guards are disabled before the switch is accepted as operational

#### Scenario: Intended mode is restored
- **WHEN** kill-switch validation ends
- **THEN** the operator SHALL restore Slack, Email, and Webhook to their approved real state while Teams and firewall remain disabled and SHALL record post-restore evidence

### Requirement: Auditable backlog disposition
The operator SHALL classify queue, dead-letter, and approval records before applying bounded, idempotent, evidence-preserving dispositions.

#### Scenario: Stuck queue item is handled
- **WHEN** pending response-action queue item 77 is reviewed
- **THEN** it SHALL be safely processed, skipped, failed, or escalated with a recorded reason and SHALL NOT remain indefinitely pending

#### Scenario: Dead letters are triaged
- **WHEN** open or retrying dead letters are reviewed
- **THEN** only transient, relevant, idempotent failures SHALL be retried and all other reviewed records SHALL receive an explicit non-success disposition or escalation without deletion

#### Scenario: Approval backlog is reviewed
- **WHEN** pending and expired approval requests are analyzed
- **THEN** current pending work SHALL receive a policy-valid decision or escalation and historical expiry evidence SHALL be retained with an operational remediation recommendation

### Requirement: Source-of-truth handoff
The VM operator SHALL stop before any durable source edit and SHALL hand the finding, evidence, acceptance criteria, and deployment verification steps to the Mac AI.

#### Scenario: Runtime diagnosis requires a wrapper or unit change
- **WHEN** recovery identifies a required change to a tracked launcher, systemd unit, backend, frontend, test, or documentation file
- **THEN** the VM AI SHALL NOT edit that file on the VM and SHALL link the work to `mac-soar-mode-accuracy-parent`
