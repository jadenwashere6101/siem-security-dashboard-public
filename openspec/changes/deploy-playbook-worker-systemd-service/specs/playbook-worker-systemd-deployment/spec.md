## ADDED Requirements

### Requirement: Repo-owned playbook worker systemd unit
The system SHALL provide a repo-owned systemd unit definition for `soar-playbook-worker.service` without installing, enabling, or starting it automatically.

#### Scenario: Unit file is present in the repo
- **WHEN** the deployment change is implemented
- **THEN** the repository contains a systemd service definition for `soar-playbook-worker.service`
- **AND** the service definition is not installed to `/etc/systemd/system` by repository checkout alone

### Requirement: Worker service runtime contract
The `soar-playbook-worker.service` unit SHALL run the existing playbook worker daemon from the VM project directory using the project virtualenv.

#### Scenario: Unit uses expected VM runtime
- **WHEN** an operator inspects the service definition
- **THEN** it specifies `User=jaden`
- **AND** it specifies `Group=jaden`
- **AND** it specifies `WorkingDirectory=/home/jaden/siem-security-dashboard`
- **AND** it loads `EnvironmentFile=/home/jaden/siem-security-dashboard/.env`
- **AND** it uses `/home/jaden/siem-security-dashboard/venv/bin/python3`
- **AND** it runs `scripts/soar_playbook_worker_daemon.py`

### Requirement: Simulation-safe service environment
The worker service unit MUST pin simulation-safe environment variables and MUST NOT enable real remediation adapters.

#### Scenario: Service pins simulation mode
- **WHEN** an operator inspects the service definition
- **THEN** it sets `INTEGRATION_MODE=simulation`
- **AND** it sets `SOAR_EXECUTION_MODE=simulation`
- **AND** it sets `SOAR_REAL_SLACK_ENABLED=false`
- **AND** it sets `SOAR_REAL_TEAMS_ENABLED=false`
- **AND** it sets `SOAR_REAL_EMAIL_ENABLED=false`
- **AND** it sets `SOAR_REAL_WEBHOOK_ENABLED=false`
- **AND** it sets `SOAR_REAL_FIREWALL_ENABLED=false`

#### Scenario: Real adapter behavior remains unchanged
- **WHEN** the service deployment artifacts are added
- **THEN** no integration adapter behavior is changed
- **AND** no real firewall, Slack, Teams, email, webhook, or other real adapter execution is enabled

### Requirement: Service restart, shutdown, and logging behavior
The service unit SHALL define bounded restart behavior, graceful shutdown signaling, and journal logging.

#### Scenario: Service lifecycle directives are defined
- **WHEN** an operator inspects the service definition
- **THEN** it specifies `Restart=on-failure`
- **AND** it specifies `RestartSec=15`
- **AND** it specifies `KillSignal=SIGTERM`
- **AND** it specifies `TimeoutStopSec=60`
- **AND** it sends standard output and standard error to the journal

### Requirement: Operator-controlled install workflow
The system SHALL document or provide a helper for installing the worker service through explicit operator commands.

#### Scenario: Install workflow is explicit
- **WHEN** an operator follows the install workflow
- **THEN** the workflow includes copying the unit to `/etc/systemd/system/soar-playbook-worker.service`
- **AND** running `systemctl daemon-reload`
- **AND** enabling `soar-playbook-worker.service`
- **AND** starting `soar-playbook-worker.service`
- **AND** checking service status
- **AND** checking journal logs

### Requirement: Operator-controlled rollback workflow
The system SHALL document rollback steps for removing the worker service from systemd.

#### Scenario: Rollback workflow disables service
- **WHEN** an operator follows the rollback workflow
- **THEN** the workflow includes stopping `soar-playbook-worker.service`
- **AND** disabling `soar-playbook-worker.service`
- **AND** removing `/etc/systemd/system/soar-playbook-worker.service`
- **AND** running `systemctl daemon-reload`
- **AND** verifying the service is inactive or absent

### Requirement: Worker deployment verification
The system SHALL define local and VM verification checks for the worker service deployment.

#### Scenario: Local verification is defined
- **WHEN** the implementation is complete
- **THEN** verification includes Python syntax checks for the daemon and worker modules
- **AND** worker tests for the playbook daemon and execution lease behavior

#### Scenario: VM verification is defined
- **WHEN** the service is installed on the VM
- **THEN** verification includes `systemctl status`
- **AND** `systemctl is-enabled`
- **AND** `systemctl is-active`
- **AND** `journalctl` log inspection
- **AND** `/metrics/playbook-worker` when the backend endpoint is available

### Requirement: Backend deploy remains decoupled
The worker systemd deployment SHALL remain separate from the backend VM deploy script during the initial rollout.

#### Scenario: Backend deploy script does not manage worker
- **WHEN** the change is implemented
- **THEN** `scripts/deploy_backend_vm.sh` does not automatically install, enable, start, stop, restart, or reload `soar-playbook-worker.service`
- **AND** backend API deploys do not implicitly trigger continuous playbook worker processing

### Requirement: No SOAR behavior changes
The service deployment change SHALL NOT change SOAR execution semantics, approval gates, protected-target behavior, backend APIs, or database schema.

#### Scenario: Runtime behavior is unchanged except service management
- **WHEN** the deployment artifacts are added
- **THEN** playbook worker logic is unchanged
- **AND** approval gates are unchanged
- **AND** protected-target behavior is unchanged
- **AND** backend API behavior is unchanged
- **AND** database schema is unchanged
- **AND** no mutation endpoint is added
