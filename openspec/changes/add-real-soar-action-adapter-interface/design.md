# Design: Real SOAR Action Adapter Interface

---

## 1. Design Boundary

The worker already has the right execution boundary:

```python
result = executor(row)
```

The adapter layer should preserve that boundary. The worker should not learn
about Linux firewall commands, cloud SDK clients, Slack payloads, SMTP, or vendor
credentials. It should continue to receive a queue row, call one executor, inspect
the returned result or raised exception, transition queue status, and write the
audit log.

The new adapter architecture should sit below a real executor/factory layer:

```text
SOAR worker
  -> executor callable
    -> adapter registry/factory
      -> selected adapter
        -> integration-specific implementation
```

`SimulationExecutor` remains the default executor. Real adapter-backed execution
is opt-in.

---

## 2. Adapter Interface Contract

Adapters are small classes that execute one integration concern. They should not
own queue transitions, database writes, Flask request state, or audit logging.

Recommended abstract contract:

```python
class BaseSoarActionAdapter:
    adapter_name: str
    supported_actions: set[str]

    def __init__(self, config: dict):
        self.config = config

    def can_handle(self, action: str) -> bool:
        return action in self.supported_actions

    def execute(self, row: dict, context: dict | None = None) -> dict:
        ...

    def test_connection(self) -> dict:
        ...
```

### Adapter input

The adapter receives the queue row produced by `claim_next_pending_action()`:

| Field | Type | Notes |
|---|---|---|
| `id` | int | Queue ID |
| `action` | str | Action name such as `block_ip` or `notify_slack` |
| `source_ip` | str \| None | Target IP when applicable |
| `alert_id` | int \| None | May be null if alert was deleted |
| `retry_count` | int | Current retry count |
| `max_retries` | int | Retry ceiling |
| `status` | str | Expected to be `running` |

Adapters must treat the input as read-only.

### Adapter output

Adapters return the same shape the worker already accepts from executors:

```python
{
    "code": "linux_firewall_block_created",
    "message": "Blocked 203.0.113.10 via ufw",
    "details": {
        "adapter": "linux_firewall",
        "action": "block_ip",
        "source_ip": "203.0.113.10",
        "provider_object_id": "optional external ID",
        "simulated": False,
    },
}
```

Required:

- `code`: non-empty machine-readable string
- `message`: non-empty human-readable summary

Optional:

- `details`: JSON-serializable dict with adapter-specific metadata

Adapters must not return raw SDK/client objects, exceptions, credentials, or
unbounded response bodies.

---

## 3. Adapter Result Format

Result `code` values should be stable and specific:

- `linux_firewall_block_created`
- `linux_firewall_block_already_present`
- `azure_nsg_rule_created`
- `azure_nsg_rule_already_present`
- `aws_security_group_rule_created`
- `slack_message_sent`
- `email_message_sent`

Result `message` should be safe for logs and `response_actions_log.details`.

Result `details` should include:

| Key | Requirement |
|---|---|
| `adapter` | Always include adapter name |
| `action` | Always include queue action |
| `source_ip` | Include when action targets an IP |
| `alert_id` | Include when available |
| `simulated` | `False` for real adapters, `True` for simulation-compatible fake adapters |
| provider IDs | Optional, only if not sensitive |

Never include:

- API keys
- webhook secrets
- SMTP credentials
- cloud access tokens
- full provider error payloads if they contain sensitive request metadata

---

## 4. Integration With `SimulationExecutor` and Worker

### Worker contract stays stable

No worker public contract should change. `process_next_action(conn, now=None,
executor=None)` continues to accept a callable executor.

### Simulation remains default

If no executor is provided, the worker continues using `SimulationExecutor()`.
This keeps tests and local development free of real side effects.

### Future real executor

Add a future executor such as:

```python
class AdapterBackedExecutor:
    def __init__(self, registry):
        self.registry = registry

    def __call__(self, row):
        adapter = self.registry.get_adapter_for_action(row["action"])
        return adapter.execute(row)
```

This executor adapts the registry/adapter model to the worker's existing callable
interface. The worker still sees only a result dict or SOAR exception.

### Relationship to `SimulationExecutor`

`SimulationExecutor` should not become a real adapter. It remains a test-safe
executor that validates action semantics and simulates outcomes. Real adapter
selection happens only when explicitly constructing an `AdapterBackedExecutor`.

---

## 5. Module Placement

Recommended layout:

```text
engines/
  soar_executor.py             # SimulationExecutor; future AdapterBackedExecutor
  soar_errors.py               # shared SOAR exception types
  soar_action_worker.py        # unchanged worker orchestration

integrations/
  __init__.py
  soar_adapters/
    __init__.py
    base.py                    # BaseSoarActionAdapter and shared validation helpers
    registry.py                # adapter registration/factory
    config.py                  # environment/config loading
    linux_firewall.py          # future
    windows_firewall.py        # future
    azure_nsg.py               # future
    aws_security_group.py      # future
    slack.py                   # future
    email.py                   # future
```

Use `integrations/` for systems outside the SIEM process. Keep `engines/` for
SOAR orchestration and executor wiring.

Do not place real adapter code in:

- `core/` — that package is for internal infrastructure helpers.
- `routes/` — routes should not own execution logic.
- `engines/soar_action_worker.py` — the worker should not depend on vendors.

---

## 6. Adapter Selection and Configuration

Real adapter execution must be opt-in.

Recommended environment/config model:

| Setting | Example | Purpose |
|---|---|---|
| `SOAR_EXECUTION_MODE` | `simulation` or `real` | Global mode; default `simulation` |
| `SOAR_ADAPTER_BLOCK_IP` | `linux_firewall` | Adapter for `block_ip` |
| `SOAR_ADAPTER_NOTIFY_SLACK` | `slack` | Adapter for Slack notifications |
| `SOAR_ADAPTER_NOTIFY_EMAIL` | `email` | Adapter for email notifications |
| `SOAR_ACTION_TIMEOUT_SECONDS` | `5` | Default adapter timeout |

Adapter-specific config should use environment variables at first:

- Linux firewall: command path, allowlist, dry-run flag
- Windows firewall: PowerShell command path, rule group name
- Azure NSG: tenant/client/subscription IDs via environment or managed identity
- AWS Security Groups: region, target security group IDs
- Slack: webhook URL or bot token
- Email: SMTP host/port/user, from address

Sensitive values must never be stored in playbook definitions, queue rows, or
`response_actions_log.details`.

### Registry behavior

The registry should:

- fail closed if real mode is requested without a configured adapter
- reject unknown adapter names
- reject adapters that do not support the requested action
- allow simulation mode to bypass real adapter construction entirely

---

## 7. Failure Classification

Adapters should classify failures with existing SOAR exception types.

### Retryable

Raise `RetryableActionError(message, code=...)` for transient failures:

- network timeout
- cloud API 429/503
- temporary DNS failure
- SMTP temporary failure
- Slack webhook transient 5xx
- command lock contention

Worker behavior:

- retries while `retry_count < max_retries`
- no `response_actions_log` row until terminal failure or success
- writes failed log row when retries are exhausted

### Skipped

Raise `SkippedAction(message, code=...)` when the action should not execute and
retrying will not help:

- unsupported action
- missing required `source_ip`
- missing required `alert_id`
- private/reserved IP blocked by safety policy
- target already blocked and idempotency check chooses no-op
- real mode disabled
- adapter disabled by configuration
- destination allowlist/denylist policy rejects the action

Worker behavior:

- queue status becomes `skipped`
- `response_actions_log` row has `status="skipped"`

### Terminal failure

Raise a non-`RetryableActionError` exception, preferably a future
`TerminalActionError`, for non-transient execution failures:

- authentication failure
- authorization denied
- malformed provider configuration
- command binary missing
- provider validation rejects request permanently
- cloud resource not found

Worker behavior:

- queue status becomes `failed`
- `response_actions_log` row has `status="failed"`

---

## 8. Timeout Expectations

Every real adapter must use explicit timeouts.

Defaults:

- command execution: 5 seconds
- HTTP/cloud calls: 5 seconds connect/read equivalent
- email/Slack sends: 5 seconds

Rules:

- no unbounded subprocess calls
- no unbounded SDK/network calls
- timeout values are configurable per adapter, with sane upper bounds
- timeout exceptions are retryable unless the adapter can prove otherwise
- logs must include timeout code and adapter name, not credentials or full payloads

For subprocess adapters, use APIs that support timeout parameters. For cloud/SaaS
SDKs, configure SDK client timeouts explicitly.

---

## 9. Logging Expectations

Adapters should use `logging.getLogger(__name__)`, not Flask `current_app`.

Log at:

- INFO for action start with non-sensitive metadata
- INFO for successful completion
- WARNING for skipped action
- WARNING for retryable failure
- ERROR for terminal failure

Include:

- `queue_id`
- `adapter`
- `action`
- `alert_id`
- `source_ip`
- machine-readable `code`

Do not include:

- credentials
- full webhook URLs
- bearer tokens
- raw cloud SDK request objects
- unredacted provider error payloads

Audit logging remains the worker's responsibility through `log_response_action()`.
Adapters do not write to `response_actions_log`.

---

## 10. Safety Controls for Dangerous Actions

`block_ip` and cloud firewall changes are dangerous. Real adapters must fail
closed.

Required controls:

- `SOAR_EXECUTION_MODE=real` required for real side effects.
- Adapter-specific enabled flag required, e.g. `SOAR_LINUX_FIREWALL_ENABLED=true`.
- Dry-run/simulation remains default.
- Public-IP validation before block operations.
- Configurable denylist for internal/private/reserved networks.
- Optional allowlist of CIDR ranges where automated action is permitted.
- Idempotency check before creating firewall/cloud rules.
- Provider rule naming convention includes SIEM queue/action context.
- Maximum rule count / rate guard to prevent alert floods from creating unlimited
  firewall rules.
- Clear skipped outcome when safety policy blocks execution.

Human approval gates are out of scope for this phase, but the adapter interface
should not make them hard to add later.

---

## 11. Future Adapter Notes

### Linux firewall (`iptables`/`ufw`)

Recommended first real adapter candidate if tested on a disposable VM.

Risks:

- can lock out SSH or management access
- command path and privilege requirements vary
- rule ordering matters

Controls:

- dry-run first
- explicit command allowlist
- timeout on subprocess
- never shell-concatenate untrusted IPs
- validate public IP before command construction

### Windows firewall

Risks:

- PowerShell invocation and quoting
- administrative privileges
- rule-group cleanup

Controls:

- use structured subprocess argument lists
- name rules predictably
- timeout all commands

### Azure NSG

Risks:

- wrong subscription/resource group/NSG
- credential/managed identity scope
- broad deny rule can disrupt production
- API throttling

Controls:

- explicit target NSG IDs
- tags/rule naming
- rule priority management
- retry 429/503 only
- terminal failure for auth/resource-not-found

### AWS Security Groups

Risks:

- wrong region/security group
- duplicate rules
- broad CIDR blocks
- API rate limits

Controls:

- explicit security group allowlist
- idempotent describe-before-authorize
- retry throttling/5xx
- terminal failure for auth/resource-not-found

### Slack notifications

Risks:

- leaking sensitive alert details
- webhook misconfiguration
- notification floods

Controls:

- redact payload
- timeout
- retry 429/5xx
- skipped for disabled channel/config
- future rate limiting

### Email notifications

Risks:

- SMTP credential leakage
- recipient misconfiguration
- delivery delays

Controls:

- timeout
- restricted recipient allowlist
- retry temporary SMTP failures
- terminal failure for auth/config errors

---

## 12. Testing Strategy

No tests should call real firewall, cloud, Slack, or email services.

### Interface tests

- fake adapter implements `execute(row)` and returns valid result dict
- fake adapter missing `code` or `message` fails through existing worker result
  validation
- unsupported action raises `SkippedAction`
- retryable fake failure raises `RetryableActionError`
- terminal fake failure raises ordinary exception or future terminal exception

### Registry/config tests

- default mode is simulation
- real mode without configured adapter fails closed
- unknown adapter name fails closed
- adapter that does not support action raises skipped/terminal config failure
- credentials are not included in result `details`

### Timeout tests

- fake adapter timeout maps to `RetryableActionError`
- subprocess/http wrappers pass timeout values
- no adapter has an unbounded call path

### Safety tests

- block private/reserved IPs before adapter side effects
- block missing `source_ip`
- enforce enabled flag for real adapters
- idempotent already-present provider state returns success or skipped by
  adapter-specific policy

### Worker integration tests

- `AdapterBackedExecutor(fake_registry)` works with `process_next_action()`
- success transitions queue to `success` and worker writes executed log
- skipped transitions queue to `skipped` and worker writes skipped log
- retryable failure with retries remaining requeues and writes no log row
- retryable failure with retries exhausted writes failed log
- terminal failure writes failed log

### No-network guard

- tests assert no real adapter imports cloud SDKs or network clients until those
  adapters are implemented behind explicit test fakes
- CI defaults to `SOAR_EXECUTION_MODE=simulation`

