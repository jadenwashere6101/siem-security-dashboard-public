# Tasks: Real SOAR Action Adapter Interface

This is a design-first phase. Implement tasks later in small steps and keep real
side effects disabled until a separate real-adapter change.

---

## Task 1 — Add adapter package scaffold

Create:

```text
integrations/
  __init__.py
  soar_adapters/
    __init__.py
    base.py
    registry.py
    config.py
```

Do not add real firewall/cloud/SaaS calls in this task.

Verification:

```bash
python3 -m py_compile integrations/*.py integrations/soar_adapters/*.py
```

---

## Task 2 — Define base adapter contract

In `integrations/soar_adapters/base.py`, define:

- `BaseSoarActionAdapter`
- `adapter_name`
- `supported_actions`
- `can_handle(action)`
- `execute(row, context=None)`
- `test_connection()`

The base `execute()` should raise `NotImplementedError`.

Also define shared validation helpers for safe IP-targeted actions if they can be
kept dependency-free.

No network calls.

---

## Task 3 — Define registry/factory

In `integrations/soar_adapters/registry.py`, define a registry that can:

- register adapter classes or instances
- select an adapter for a queue action
- reject unknown adapter names
- reject unsupported actions
- fail closed in real mode when no adapter is configured

Do not instantiate real cloud/firewall clients.

---

## Task 4 — Define configuration loader

In `integrations/soar_adapters/config.py`, define config parsing for:

- `SOAR_EXECUTION_MODE`, default `simulation`
- action-to-adapter mapping, e.g. `SOAR_ADAPTER_BLOCK_IP`
- global timeout, e.g. `SOAR_ACTION_TIMEOUT_SECONDS`
- adapter enabled flags

Do not read secrets into logs or result details.

---

## Task 5 — Add adapter-backed executor shell

In `engines/soar_executor.py`, add a future-compatible
`AdapterBackedExecutor` that:

- accepts a registry
- implements `__call__(row)`
- selects an adapter by `row["action"]`
- returns the adapter result unchanged
- lets `SkippedAction`, `RetryableActionError`, and terminal exceptions propagate

Do not change `SimulationExecutor` behavior.
Do not change `process_next_action()` public interface.

---

## Task 6 — Add fake adapters for tests only

Add test-local fake adapters covering:

- success
- skipped
- retryable failure
- terminal failure
- invalid result format
- timeout mapped to retryable failure

Do not add production real adapters in this change.

---

## Task 7 — Add tests

Add tests for:

- adapter base contract
- registry selection and fail-closed behavior
- config defaults to simulation
- adapter-backed executor integrates with worker
- failure classification maps to existing queue/log outcomes
- no real network/cloud imports are needed
- safety validation prevents private/reserved IP block attempts

Verification:

```bash
python3 -m pytest tests/test_soar_executor.py tests/test_response_action_queue.py -x --tb=short -v
```

Then:

```bash
python3 -m pytest tests/ -x --tb=short -v
```

---

## Task 8 — Document first real adapter candidate

Before implementing a real adapter, document a separate change for exactly one
adapter. Recommended first candidate:

- Linux firewall adapter in dry-run mode first

The follow-up spec must include:

- target platform
- exact command/API surface
- privilege requirements
- lockout prevention
- timeout behavior
- rollback/unblock strategy
- staging test plan

---

## Explicit Non-Tasks

Do not do these in this change:

- implement real firewall blocking
- add cloud credentials
- make network calls
- touch frontend
- add playbooks/incidents
- alter queue schema
- change worker audit logging
- change detection/correlation/ingest flow
- introduce distributed worker behavior

