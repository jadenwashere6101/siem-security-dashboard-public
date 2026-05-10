# Design: SOAR Integration Adapter Simulation Foundation

## Proposed Adapter Architecture

Add a small integration layer under `integrations/` that is deliberately separate from
playbook execution, SOAR queue processing, approvals, ingest, detection, and correlation.

The foundation should define:

- A base adapter contract in `integrations/base_integration.py`.
- A registry in `integrations/integration_registry.py`.
- Simulation-only adapter implementations for `slack`, `email`, `firewall`, and optionally
  `webhook`.

Adapters expose a common method:

```python
execute(action: str, params: dict | None = None, context: dict | None = None) -> dict
```

The method must never make network calls in simulation mode. The initial implementation must
support simulation mode only.

## Files Likely To Change

- `integrations/base_integration.py`
- `integrations/integration_registry.py`
- `integrations/slack_simulation_adapter.py`
- `integrations/email_simulation_adapter.py`
- `integrations/firewall_simulation_adapter.py`
- `integrations/webhook_simulation_adapter.py` if included safely
- `tests/test_integration_registry.py`
- `tests/test_integration_simulation_adapters.py`

No playbook executor, route, schema, frontend, ingest, detection, correlation, SOAR queue, or
approval route file should change in this foundation slice.

## INTEGRATION_MODE Behavior

Read `INTEGRATION_MODE` from environment/config with default `simulation`.

Allowed initial values:

- `simulation`

Any other value should fail closed, either by raising a clear configuration error or by
returning an unsupported-mode result. The implementation must not silently enable real mode.

Future values such as `real` or `hybrid` are out of scope. They may be documented but must
not be implemented.

## Simulation Result Format

Each adapter `execute()` call should return a structured dictionary:

```json
{
  "adapter": "slack",
  "action": "send_message",
  "mode": "simulation",
  "simulated": true,
  "executed": false,
  "success": true,
  "message": "Simulated slack action.",
  "params": {},
  "context": {},
  "metadata": {}
}
```

Rules:

- `simulated` must always be `true` in this change.
- `executed` must always be `false` in this change.
- `mode` must be `simulation`.
- `success` may be `false` for invalid actions or invalid params, but failure must still be
  simulated and local.
- Results must not include secrets.
- Params/context may be sanitized if they can include sensitive values.

## Registry Behavior

The registry should expose a small API such as:

```python
get_integration_adapter(name: str, mode: str | None = None)
list_integration_adapters(mode: str | None = None)
```

Expected registry rules:

- Normalize adapter names to lowercase.
- Return simulation adapter instances when mode is `simulation` or unset.
- Reject unknown adapters with a clear `ValueError`.
- Reject non-simulation modes with a clear `ValueError`.
- Do not instantiate real clients in simulation mode.
- Do not read required real-integration secrets in simulation mode.

## Adapter Behavior

### Slack Simulation Adapter

May accept actions such as `send_message` or `notify_channel`. It must not call Slack APIs or
webhook URLs.

### Email Simulation Adapter

May accept actions such as `send_email` or `notify_owner`. It must not call SMTP, SendGrid,
SES, or any provider client.

### Firewall Simulation Adapter

May accept actions such as `block_ip`, `unblock_ip`, or `tag_ip`. It must not mutate
`blocked_ips`, local firewall state, cloud firewall state, or any network/security appliance.

### Webhook Simulation Adapter

May be included only if it is guaranteed to never issue HTTP requests. It should only record
what would have been sent.

## Safety Boundaries

- Simulation mode only.
- Default mode must be `simulation`.
- No real network calls.
- No real integration clients.
- No required secrets.
- No firewall or blocklist mutation.
- No SOAR queue enqueueing.
- No approval creation or decision.
- No playbook executor wiring in this change.
- Preserve existing playbook executor behavior.
- Preserve existing ingest, detection, correlation, incident, approval, and SOAR queue tests.

## Failure Behavior

- Unknown adapter name: raise `ValueError` or return a clear local error.
- Unknown action: return `success: false` with `simulated: true`, `executed: false`, and a
  clear message.
- Invalid params: return `success: false` with local validation details.
- Non-simulation mode: fail closed with a clear configuration error.
- Missing secrets in simulation mode: must not fail, because simulation mode must not require
  secrets.

## Test Strategy

Add focused backend tests for:

- Registry defaults to simulation mode.
- Registry returns the expected simulation adapters.
- Unknown adapter names fail locally.
- Non-simulation mode is rejected.
- Simulation adapters return the stable result shape.
- Every result has `mode: simulation`, `simulated: true`, and `executed: false`.
- Slack, email, firewall, and webhook simulation adapters do not call network libraries.
- Simulation mode does not require secrets.
- Firewall simulation does not mutate `blocked_ips`.
- No SOAR queue rows are created.
- Existing playbook executor behavior is unchanged.

Network calls should be guarded with monkeypatches that fail the test if `requests`, SMTP,
socket, or similar network primitives are invoked.

## Risks / Stop Conditions

- Stop if adapter construction requires real credentials.
- Stop if a simulation adapter needs to import or instantiate a real provider client.
- Stop if tests require network access.
- Stop if implementation requires schema changes beyond a proven tiny additive change.
- Stop if playbook executor wiring becomes necessary.
- Stop if any implementation touches ingest, detection, correlation, SOAR queue behavior,
  approval decisions, frontend, daemon/systemd worker code, or firewall/blocklist mutation.
