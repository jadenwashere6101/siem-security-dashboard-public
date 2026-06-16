## Why

The SOAR playbook worker daemon code exists, but it is not deployed as a managed VM service. Operators need a safe, repeatable, and explicitly controlled systemd deployment path before enabling continuous playbook processing.

## What Changes

- Add a repo-owned systemd service definition for `soar-playbook-worker.service`.
- Define an operator-controlled install, update, verification, and rollback workflow.
- Pin simulation-safe environment guards in the service so daemon rollout does not enable real remediation.
- Document VM runtime expectations: service user, working directory, environment file, project virtualenv, restart policy, graceful shutdown, and journal logging.
- Keep the worker service separate from `scripts/deploy_backend_vm.sh` initially so backend deploys do not automatically start or restart continuous playbook processing.
- Avoid any changes to SOAR worker logic, playbook execution semantics, approval gates, integration adapters, backend APIs, or schema.

## Capabilities

### New Capabilities
- `playbook-worker-systemd-deployment`: Operator-controlled systemd deployment contract for the simulation-safe SOAR playbook worker daemon.

### Modified Capabilities

None.

## Impact

- Deployment artifacts: introduces a future repo-owned systemd unit file and optional helper/documentation for installing it on the VM.
- Operations: adds explicit start, status, journal, and rollback steps for `soar-playbook-worker.service`.
- Safety: pins simulation mode and real-adapter disable flags at the service layer.
- Backend/API/schema: no changes.
- SOAR behavior: no changes to playbook execution, approvals, queue semantics, protected-target handling, or adapter behavior.
