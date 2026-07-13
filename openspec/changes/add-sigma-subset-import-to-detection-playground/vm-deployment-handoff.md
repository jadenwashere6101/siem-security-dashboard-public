# VM Deployment Handoff — add-sigma-subset-import-to-detection-playground

**Owner after Mac commit/push:** VM AI  
**Mac must not access the VM for this handoff.** Deploy only after explicit user authorization of a specific commit.

## What changed (expected files)

Backend (restart required):

- `engines/sigma_playground.py` (new)
- `engines/detection_simulator.py`
- `routes/detection_simulator_routes.py`
- `requirements.txt` (`PyYAML==6.0.3`)
- `tests/test_sigma_playground.py` (tests only; not required on VM runtime)

Frontend (artifact deploy):

- `frontend/src/components/DetectionSimulatorPanel.js`
- `frontend/src/components/DetectionSimulatorSigmaImport.js` (new)
- `frontend/src/components/DetectionSimulatorSigmaPreview.js` (new)
- `frontend/src/utils/detectionSimulatorPlaygroundContract.js`
- `frontend/src/utils/detectionSimulatorSigmaSamples.js` (new)
- `frontend/src/services/detectionSimulatorService.js`
- related frontend tests (not required at runtime)

OpenSpec / docs (optional on VM):

- `openspec/changes/add-sigma-subset-import-to-detection-playground/**`

## Migration

**None.** Do not run migration apply for this change.  
If `deploy_backend_vm.sh --dry-run-migrations` unexpectedly reports a pending migration, **stop and report** — do not invent a workaround.

## Deployment order

1. Confirm VM clean-tree gate per `docs/mac-vm-source-of-truth-policy.md`.
2. Sync VM to the **explicitly approved** commit (`git fetch` + `git reset --hard` to that commit — never merge/pull).
3. Install/refresh Python deps so `PyYAML==6.0.3` is present in the runtime venv.
4. Restart **backend** services only (Detection Simulator is served by the Flask API).
5. Health check: `curl -fsS http://127.0.0.1:5051/health`
6. Deploy Mac-built frontend artifact (`frontend/build/`) via the approved rsync path.
7. No DB migration step.

## Read-only / production-safe checks (VM AI)

- Log in as analyst (or super-admin) and open Detection Simulator.
- Confirm three modes: Existing Production Rule, Temporary Playground Rule, Sigma Subset Import.
- Sigma mode:
  - Load sample Sigma rule + sample events → Run Simulation.
  - Expect normalized internal-rule preview, subset compatibility disclosure (“not full Sigma”), shared pipeline + explainability, rollback/non-persistence wording.
  - Paste unsupported construct (e.g. `|re` modifier or `1 of selection*`) → expect structured validation error; no results panel.
- Regression: run one V1 production-rule simulation and one V2 temporary-rule simulation; behavior unchanged.
- Confirm no durable rows appear for simulation runs (events/alerts/queue/playbook_executions unchanged for the canary).
- Confirm UI never claims full Sigma compatibility.

## Rollback

- Application-version rollback to the prior approved commit (backend restart + prior frontend artifact).
- No database down-migration.
- Feature is request-scoped; rolling back code removes Sigma mode with no data cleanup required.

## Out of scope for VM AI

- Source edits on the VM
- Commits/pushes
- Inventing broader Sigma support
- Applying migrations for this change
