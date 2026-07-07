## ADDED Requirements

### Requirement: Deployment requires clean sync verification before service changes
The deployment workflow SHALL verify GitHub is up to date and both the Mac repo and the VM repo are clean before any service restart or installation step begins.

#### Scenario: GitHub and Mac repo are verified before VM sync
- **WHEN** a deployment begins
- **THEN** the workflow confirms `origin/main` is current
- **AND** confirms the Mac repo working tree is clean

#### Scenario: VM repo is verified clean before and after sync
- **WHEN** the VM is synced to `origin/main`
- **THEN** the workflow confirms the VM working tree is clean before fetch/merge
- **AND** confirms the VM working tree is clean after fetch/merge

### Requirement: Deployment applies migrations before dependent service restarts
The deployment workflow SHALL check for pending schema migrations and apply them before restarting any service that depends on the resulting schema.

#### Scenario: Pending migrations are applied first
- **WHEN** a deployment includes pending schema migrations
- **THEN** the workflow applies those migrations before restarting the backend, workers, or listener

#### Scenario: No pending migrations skips the apply step
- **WHEN** a deployment has no pending schema migrations
- **THEN** the workflow proceeds directly to service restart without an apply step

### Requirement: Deployment restarts services in dependency order with per-service verification
The deployment workflow SHALL restart the backend first, then the playbook/response-action workers, then the pfSense UDP listener, verifying each service before proceeding to the next.

#### Scenario: Backend is verified before workers restart
- **WHEN** the backend service restarts
- **THEN** the workflow verifies the backend health endpoint responds successfully before restarting workers

#### Scenario: Workers are verified before the listener restarts
- **WHEN** the worker services restart
- **THEN** the workflow verifies worker service status is active before restarting or starting the listener

#### Scenario: Listener verification confirms port binding
- **WHEN** the listener service restarts or starts
- **THEN** the workflow verifies the listener service is active
- **AND** verifies the listener is bound to its configured UDP port

### Requirement: Azure NSG changes are gated behind local validation and port/IP confirmation
The infrastructure workflow SHALL NOT create or modify an Azure NSG rule for the pfSense listener port until the listener has passed local or VM-side synthetic validation and the final UDP port and expected pfSense public IP are confirmed.

#### Scenario: NSG rule creation is blocked before validation
- **WHEN** the listener has not yet passed synthetic validation on the VM
- **THEN** no Azure NSG rule for the listener port is created

#### Scenario: NSG rule creation requires confirmed port and IP
- **WHEN** an Azure NSG rule for the listener port is created
- **THEN** the final UDP port has been confirmed
- **AND** the expected pfSense public IP has been confirmed and used to restrict the rule source where possible

### Requirement: VM firewall decision is explicitly recorded
The infrastructure workflow SHALL document an explicit decision on whether a VM-local firewall (defense-in-depth) rule is added for the listener port, regardless of which option is chosen.

#### Scenario: VM firewall decision is documented either way
- **WHEN** the infrastructure sequence completes
- **THEN** a decision to add or defer a VM-local firewall rule for the listener port is recorded with its rationale

### Requirement: Service installation is operator-controlled
The infrastructure workflow SHALL install or update the listener and worker services using an operator-controlled install-helper pattern that does not auto-enable or auto-start the service without an explicit flag.

#### Scenario: Install helper does not auto-start
- **WHEN** the install-helper is run without an explicit enable/start flag
- **THEN** the service unit is installed or updated without being enabled or started

#### Scenario: Explicit flag enables and starts the service
- **WHEN** the install-helper is run with an explicit enable/start flag
- **THEN** the service is enabled and started as requested

### Requirement: Required environment variables are documented before deployment
The infrastructure workflow SHALL document the required environment variables for the backend, workers, and listener before deployment, including bind host/port, source IP allow-list, ingest URL, ingest API key/header, packet size limit, rate limits, timeout, and log level.

#### Scenario: Environment variable inventory exists before deployment
- **WHEN** a deployment is planned
- **THEN** the required environment variables for backend, workers, and listener are documented and available for review before the deployment proceeds

### Requirement: Rollback plan is defined per deployed component
The deployment workflow SHALL define an explicit rollback action for each deployed component: backend, workers, listener service, and any Azure NSG rule.

#### Scenario: Rollback actions exist for every component
- **WHEN** the rollback plan is reviewed
- **THEN** it defines a rollback action for the backend
- **AND** a rollback action for the worker services
- **AND** a rollback action for the listener service
- **AND** a rollback action for removing any Azure NSG rule created for the listener

### Requirement: Runtime validation uses synthetic traffic only
Runtime validation SHALL use synthetic or local test packets to exercise the listener, parser, ingest route, database, dashboard, detection, and playbook behavior, and SHALL NOT use live pfSense production traffic.

#### Scenario: Synthetic packets exercise the full path
- **WHEN** runtime validation is performed
- **THEN** synthetic pfSense filterlog packets are sent to the deployed listener without external/live exposure

#### Scenario: Live traffic is not used for validation
- **WHEN** runtime validation is performed
- **THEN** no live pfSense production traffic is sent or relied upon

### Requirement: Runtime validation verifies parser, ingest, database, and dashboard behavior end to end
Runtime validation SHALL verify that a synthetic packet is parsed correctly, accepted by the ingest route, stored in the database with `source=pfsense` and `source_type=firewall`, and visible on the dashboard.

#### Scenario: End-to-end synthetic event is verified
- **WHEN** a synthetic pfSense packet is sent through the deployed listener
- **THEN** the parser output matches the expected fields
- **AND** the ingest route accepts the forwarded event
- **AND** a normalized event with `source=pfsense` and `source_type=firewall` is present in the database
- **AND** the event is visible on the dashboard

### Requirement: Runtime validation verifies alert, playbook, and approval behavior
Runtime validation SHALL verify that expected detection rules fire on synthetic pfSense events, do not fire on synthetic benign events, and that any resulting playbook execution and approval gates behave correctly.

#### Scenario: Detection fires only where expected
- **WHEN** synthetic pfSense events representing blocked and allowed traffic are ingested
- **THEN** expected detection rules fire for the blocked-traffic case
- **AND** detection rules do not fire for the benign allowed-traffic case

#### Scenario: Playbook and approval behavior is verified where applicable
- **WHEN** a synthetic pfSense alert triggers a playbook
- **THEN** the playbook executes as expected
- **AND** any protected-target approval gate behaves correctly for that execution

### Requirement: Runtime validation verifies safe logging and failure paths
Runtime validation SHALL verify structured safe logging across the listener, ingest route, and worker components, and SHALL verify that malformed, oversized, unauthorized-source, rate-limited, and backend-failure cases are handled safely without crashes.

#### Scenario: Safe logging is verified during synthetic testing
- **WHEN** synthetic packets are processed
- **THEN** logs across listener, ingest route, and worker components contain safe structured metadata without raw payloads or secrets

#### Scenario: Failure paths do not crash the system
- **WHEN** synthetic malformed, oversized, unauthorized-source, rate-limited, or backend-failure cases are exercised
- **THEN** each case is handled safely
- **AND** no component crashes or enters an unrecoverable state

### Requirement: Production readiness requires checklists, health checks, and explicit sign-off
Production readiness SHALL require a completed operator checklist, monitoring checklist, and passing health checks, and SHALL require an explicit deployment sign-off before any pfSense handoff communication.

#### Scenario: Sign-off requires all readiness checks
- **WHEN** deployment sign-off is recorded
- **THEN** the operator checklist is complete
- **AND** the monitoring checklist is complete
- **AND** backend, worker, and listener health checks pass
- **AND** all runtime validation scenarios pass

#### Scenario: Handoff is blocked without sign-off
- **WHEN** deployment sign-off has not been recorded
- **THEN** no uncle/pfSense handoff communication is sent

### Requirement: Rollback and success criteria are explicit and observable
Production readiness SHALL define observable rollback criteria (health check failure, error-rate threshold, listener crash loop) and observable success criteria tied to runtime validation outcomes.

#### Scenario: Rollback criteria are observable
- **WHEN** a deployed component exhibits health check failure, an error-rate threshold breach, or a listener crash loop
- **THEN** the documented rollback criteria identify that condition as a rollback trigger

#### Scenario: Success criteria are tied to validation outcomes
- **WHEN** success criteria are evaluated
- **THEN** they require all runtime validation scenarios in this spec to have passed

### Requirement: pfSense handoff requires confirmed information and readiness gates
The pfSense handoff workflow SHALL document the information required from the uncle, confirm the expected pfSense public IP, provide remote syslog configuration guidance, and complete a final production enablement checklist before requesting pfSense configuration changes.

#### Scenario: Handoff information is documented before contacting the uncle
- **WHEN** a handoff communication is prepared
- **THEN** it documents the information required from the uncle, including confirmation of the pfSense public IP and ability to target the confirmed listener port

#### Scenario: Handoff guidance matches the confirmed configuration
- **WHEN** remote syslog configuration guidance is provided to the uncle
- **THEN** it references the confirmed Azure VM public IP and confirmed listener port

#### Scenario: Handoff is blocked until the final enablement checklist passes
- **WHEN** the final production enablement checklist has not passed
- **THEN** the uncle is not asked to enable pfSense remote syslog

### Requirement: This spec excludes implementation, infrastructure creation, and live traffic
This change SHALL NOT implement parser, ingest, UDP listener, detection, or SOAR code, SHALL NOT implement or create firewall rules or Azure NSG rules, and SHALL NOT perform live deployment or handle production traffic.

#### Scenario: No implementation is performed by this spec
- **WHEN** this spec-creation task is complete
- **THEN** no parser, ingest, listener, detection, or SOAR source code has been added or modified

#### Scenario: No infrastructure or live traffic is created by this spec
- **WHEN** this spec-creation task is complete
- **THEN** no Azure NSG rule or firewall rule has been created
- **AND** no live deployment has been performed
- **AND** no production pfSense traffic has been sent or received
