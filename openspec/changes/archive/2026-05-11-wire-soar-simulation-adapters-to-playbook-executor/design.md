# Design: Wire SOAR Simulation Adapters To Playbook Executor

## Proposed Executor / Adapter Architecture

The existing playbook step executor remains the only consumer of `playbook_executions`.
This change should add a narrow adapter-dispatch path for integration-shaped actions while
preserving existing simulation behavior for non-integration actions and approval gates.

The executor should:

1. Load the playbook execution and definition as it does today.
2. For each step, detect whether the step action maps to a simulation integration adapter.
3. Resolve the adapter through `integrations.integration_registry`.
4. Call `adapter.execute(...)` in simulation mode only.
5. Write the adapter result into the step's `steps_log` entry.
6. Continue or fail according to existing step `on_failure` behavior.

No route handler, SOAR queue worker, ingest path, detection engine, or correlation engine
should call adapters in this change.

## Action-To-Adapter Mapping

Initial mapping:

| Playbook step action | Adapter | Adapter action |
|---|---|---|
| `notify_slack` | `slack` | `send_message` |
| `notify_email` | `email` | `send_email` |
| `block_ip` | `firewall` | `block_ip` |
| `notify_webhook` | `webhook` | `post_event` |

Mapping should live near the executor or in a small helper module only if that keeps the
executor readable. Do not put routing logic in the registry; the registry resolves adapters
by integration name.

## steps_log Output Format

Adapter-backed step logs should keep the current step log shape and add adapter details in
the `output` field:

```json
{
  "step_index": 0,
  "action": "notify_slack",
  "status": "success",
  "mode": "simulation",
  "simulated": true,
  "executed": false,
  "started_at": "...",
  "completed_at": "...",
  "message": "Simulated adapter action completed.",
  "output": {
    "adapter_result": {
      "adapter": "slack",
      "action": "send_message",
      "mode": "simulation",
      "simulated": true,
      "executed": false,
      "success": true,
      "message": "Simulated slack action. No webhook or API call was made.",
      "params": {},
      "context": {},
      "metadata": {}
    }
  }
}
```

Failure entries should set step `status: "failed"` when adapter result has
`success: false`, while still preserving `simulated: true` and `executed: false`.

## Simulation Mode Behavior

- The executor may call the adapter registry only while `INTEGRATION_MODE` resolves to
  `simulation`.
- If registry mode resolution fails because mode is non-simulation, the step must fail
  safely without real execution.
- The executor must not instantiate provider clients directly.
- Adapter params should come from the playbook step `params`.
- Adapter context should include relevant execution context such as `playbook_id`,
  `execution_id`, `alert_id`, `incident_id`, and `step_index`.
- Existing generic simulated actions should keep their behavior unless they are explicitly
  mapped to adapters by this change.

## Failure Behavior

- Unknown playbook step action: preserve existing unsupported-action behavior.
- Known adapter-mapped action but unknown adapter: mark step failed safely.
- Adapter returns `success: false`: mark step failed and respect existing `on_failure`
  behavior.
- Non-simulation `INTEGRATION_MODE`: mark step failed safely; do not call real mode.
- Adapter exception: catch and record a simulated failed step. Do not crash the batch or
  leave the execution in `running` unless existing executor behavior already does that for
  unexpected failures.

## Safety Boundaries

- Simulation-only.
- Real mode remains disabled/fail-closed.
- No real Slack, email, webhook, or firewall calls.
- No provider clients or secrets.
- No network calls in tests.
- No firewall/blocklist mutation.
- No SOAR queue enqueueing or worker changes.
- No approval behavior changes.
- No execution control route changes.
- No frontend changes.
- No schema changes.
- No ingest, detection, or correlation changes.

## Test Strategy

Add focused backend tests around `engines/playbook_step_executor.py`:

- `notify_slack` step records a Slack adapter result and succeeds.
- `notify_email` step records an email adapter result and succeeds.
- `block_ip` step records a firewall adapter result and succeeds without mutating
  `blocked_ips`.
- `notify_webhook` step records a webhook adapter result and succeeds without HTTP calls.
- Adapter-backed steps include `simulated: true`, `executed: false`, and nested
  `adapter_result`.
- Unsupported adapter action or adapter failure marks the step failed and respects
  `on_failure`.
- Non-simulation `INTEGRATION_MODE` fails closed and performs no real calls.
- Existing approval gate pause/resume/deny/expire tests continue to pass.
- Existing SOAR queue and regression tests continue to pass.

Use monkeypatching to fail tests if `socket`, `http.client`, `smtplib`, or similar network
primitives are called.

## Risks / Stop Conditions

- Stop if adapter wiring requires real secrets or provider clients.
- Stop if real mode must be implemented to make tests pass.
- Stop if wiring requires schema, frontend, SOAR queue, ingest, detection, correlation, or
  approval changes.
- Stop if adapter-backed `block_ip` needs to write `blocked_ips`.
- Stop if executor changes break existing approval gate behavior.
- Stop if tests cannot prove no network calls.
