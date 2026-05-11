# Design: SOAR Playbook Engine Foundation

## Current State

Detection alerts are committed to the `alerts` table and then enqueued into
`response_actions_queue` post-commit. The queue worker executes one flat action per row
(block_ip, monitor, or flag_high_priority) via the simulation or adapter-backed executor.

There is no facility to declare conditional, named response sequences tied to alert patterns.
When a password-spraying alert fires, the response action is determined at detection time by
`determine_response_action()` based on reputation score alone. There is no per-playbook
execution record, no trigger condition registry, and no way to associate a committed alert
with a defined response policy beyond what was decided inside the detection transaction.

This change adds the structural foundation for playbook-driven response without touching any
part of the detection, correlation, or ingest pipeline.

---

## Schema: playbook_definitions

Proposed SQL (to be added to `schema.sql`):

```sql
CREATE TABLE IF NOT EXISTS playbook_definitions (
    id VARCHAR(64) PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    trigger_config JSONB NOT NULL DEFAULT '{}',
    steps JSONB NOT NULL DEFAULT '[]',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_playbook_definitions_enabled
    ON playbook_definitions (enabled);
```

### Column semantics

**`id`** — human-readable slug chosen by whoever creates the definition. Must be URL-safe and
stable (e.g., `block_and_notify_high_rep`). Serves as a stable FK reference from
`playbook_executions`. Do not use auto-increment here — operator-chosen IDs make playbook
definitions readable in audit logs and test fixtures.

**`trigger_config`** — JSONB document evaluated by the engine at match time. All fields are
optional. An empty object `{}` matches every alert.

Expected shape:
```json
{
  "alert_type": "password_spraying",
  "min_severity": "HIGH",
  "source": "bank_app",
  "correlation_flag": true,
  "reputation_score_min": 75
}
```

Fields and their semantics are defined under "Trigger Field Evaluation" below.

**`steps`** — JSONB array of step definitions. Not processed in this change. Stored for
operator configuration and for Phase 2D step execution. The registry validates that action
names in this array are recognized before a definition is accepted.

Expected shape per step:
```json
{
  "action": "block_ip",
  "params": {},
  "on_failure": "abort",
  "max_retries": 2
}
```

Supported `on_failure` values: `"abort"` (stop the playbook on failure) or `"continue"`
(skip the failed step and continue to the next). Default if absent: `"abort"`.

**`enabled`** — only enabled definitions are evaluated during trigger matching. Disabling a
definition has no effect on in-flight executions.

---

## Schema: playbook_executions

Proposed SQL (to be added to `schema.sql`):

```sql
CREATE TABLE IF NOT EXISTS playbook_executions (
    id SERIAL PRIMARY KEY,
    playbook_id VARCHAR(64) NOT NULL REFERENCES playbook_definitions(id),
    alert_id INTEGER REFERENCES alerts(id) ON DELETE SET NULL,
    incident_id INTEGER REFERENCES incidents(id) ON DELETE SET NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'pending',
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    last_completed_step INTEGER,
    steps_log JSONB NOT NULL DEFAULT '[]',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_playbook_executions_playbook_id
    ON playbook_executions (playbook_id);
CREATE INDEX IF NOT EXISTS idx_playbook_executions_alert_id
    ON playbook_executions (alert_id);
CREATE INDEX IF NOT EXISTS idx_playbook_executions_status
    ON playbook_executions (status);
CREATE INDEX IF NOT EXISTS idx_playbook_executions_created_at
    ON playbook_executions (created_at DESC);
```

### Status values

| Status | Meaning |
|---|---|
| `pending` | Matched and created, not yet picked up by the executor. |
| `running` | Executor has started processing steps. |
| `success` | All steps reached a terminal successful state. |
| `failed` | One or more steps failed and `on_failure: abort` halted the playbook. |
| `abandoned` | Created but never processed, e.g., after a config change. |

Terminal states: `success`, `failed`, `abandoned`. `pending` and `running` are non-terminal.

### Checkpoint columns

**`last_completed_step`** — integer index (0-based) of the last step that successfully
completed. NULL when no steps have completed. Written by Phase 2D after each successful
step. Allows the executor to resume mid-playbook after a worker crash without re-running
already-completed steps. Scaffolded now so Phase 2D has no schema migration to perform.

**`steps_log`** — JSONB array, one element per step execution attempt. Written by Phase 2D.
Each element carries: `step_index`, `action`, `status`, `started_at`, `completed_at`,
`error`, `step_idempotency_key`. Empty array in this phase.

### alert_id and incident_id linkage

`alert_id` references the detection or correlation alert that triggered the playbook match.
`ON DELETE SET NULL` preserves the execution history if the alert is later deleted.

`incident_id` is optional. If the triggering alert has an associated incident (via
`incident_alerts`), the caller may look it up and set this FK. If no incident exists, NULL
is stored. The incident link enables future timeline joins.

---

## Store Helper Design: core/playbook_store.py

A new module with no Flask dependency. All functions accept `conn` as their first argument.
None of these functions commit — callers are responsible for transaction management.

### Proposed public functions

```python
def list_enabled_playbook_definitions(conn) -> list[dict]:
    """
    Returns all definitions with enabled=True, ordered by id ASC.
    Each dict includes all columns. trigger_config and steps are returned
    as parsed Python dicts/lists, not raw JSON strings.
    """

def get_playbook_definition(conn, playbook_id: str) -> dict | None:
    """
    Returns a single definition by id, or None if not found.
    """

def create_playbook_execution(
    conn,
    playbook_id: str,
    alert_id: int | None,
    incident_id: int | None = None,
) -> int:
    """
    Inserts a new execution row with status='pending'.
    Returns the new execution id (SERIAL).
    """

def get_playbook_execution(conn, execution_id: int) -> dict | None:
    """
    Returns a single execution row by id, or None if not found.
    """

def update_execution_status(
    conn,
    execution_id: int,
    status: str,
    now=None,
) -> None:
    """
    Transitions the execution to the given status.
    Sets started_at when transitioning to 'running' (if not already set).
    Sets completed_at when transitioning to a terminal status.
    Raises ValueError for unrecognized status values.
    """

def list_playbook_executions(
    conn,
    playbook_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """
    Returns executions ordered by created_at DESC.
    Filters by playbook_id and/or status when provided.
    """
```

Valid status values for `update_execution_status`:
`pending`, `running`, `success`, `failed`, `abandoned`.

---

## Registry Scaffold: engines/playbook_registry.py

A minimal scaffold that defines recognized action names. Does not wire any handlers — handler
registration is Phase 2D.

```python
SUPPORTED_ACTIONS: frozenset[str] = frozenset({
    "block_ip",
    "monitor",
    "flag_high_priority",
})

def validate_playbook_steps(steps: list[dict]) -> list[str]:
    """
    Returns a list of validation error strings.
    An empty list means the steps are valid.
    Checks:
    - Each step is a dict.
    - Each step has an "action" key.
    - Each action name is in SUPPORTED_ACTIONS.
    - Each step has a valid "on_failure" value ("abort" or "continue") if present.
    Does not validate params — param shapes are action-specific and validated at
    execution time in Phase 2D.
    """
```

`SUPPORTED_ACTIONS` must grow as new action types are implemented. It is intentionally
conservative: unknown action names in step definitions are rejected at definition-load time
rather than silently ignored at execution time.

---

## Trigger Matching Engine: engines/playbook_engine.py

### Module-level constants

```python
CORRELATED_ALERT_TYPES: frozenset[str] = frozenset({
    "correlated_activity",
    "web_to_app_attack_pattern",
    "spray_then_success_pattern",
    "cloud_app_error_pattern",
})

SEVERITY_RANK: dict[str, int] = {
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}
```

`CORRELATED_ALERT_TYPES` must be kept in sync with the `alert_type` values inserted by
`engines/correlation_engine.py`. If the correlation engine adds a new alert type, this set
must be updated. Do not import from `correlation_engine.py` — that would create a dependency
on a "do not touch" module. Maintain the constant here.

### Public interface

```python
def match_playbooks(conn, alert_id: int) -> list[dict]:
    """
    Fetches the committed alert row and all enabled definitions.
    Returns the subset of definitions whose trigger_config matches the alert.

    Safe to call only after the alert row is committed to the database.
    Returns an empty list if the alert is not found or no definitions match.
    Does not create execution records — the caller decides what to do with matches.
    Does not raise on match failure; logs a warning and returns [].
    """

def _fetch_alert(conn, alert_id: int) -> dict | None:
    """
    Reads the committed alert row by id.
    Returns a dict of all alert columns, or None if not found.
    """

def _evaluate_trigger(trigger_config: dict, alert: dict) -> bool:
    """
    Pure function — no DB access, no side effects.
    Returns True if every field specified in trigger_config matches the alert.
    Fields absent from trigger_config are treated as match-all.
    """
```

### Trigger field evaluation

All conditions use AND logic: every specified field in `trigger_config` must match.

**`alert_type`**
- Trigger present: `alert["alert_type"].lower() == trigger_config["alert_type"].lower()`
- Alert field `None` or missing: does not match.

**`min_severity`**
- Trigger present: `SEVERITY_RANK.get(alert_severity_lower, 0) >= SEVERITY_RANK.get(trigger_severity_lower, 0)`
- Alert severity `None` or not in `SEVERITY_RANK`: does not match when trigger is set.
- Severity comparison is case-insensitive on both sides.

**`source`**
- Trigger present: `(alert.get("source") or "").lower() == trigger_config["source"].lower()`
- Alert `source` field `None`: an empty string comparison fails a non-empty trigger value,
  so the alert does not match. A trigger of `""` would match a null source — operators should
  not use an empty string trigger value.

**`correlation_flag`**
- Trigger `True`: `alert["alert_type"] in CORRELATED_ALERT_TYPES`
- Trigger `False`: `alert["alert_type"] not in CORRELATED_ALERT_TYPES`
- Alert `alert_type` `None`: does not match either flag value.

**`reputation_score_min`**
- Trigger present: `(alert.get("reputation_score") or 0) >= trigger_config["reputation_score_min"]`
- Alert `reputation_score` `None`: treated as 0. A trigger of `reputation_score_min: 0`
  matches all alerts including those with no score. A trigger of `reputation_score_min: 1`
  or higher does not match alerts with no score.

### Call site pattern (not wired in this change)

When a future change wires trigger matching into the post-commit path, the correct pattern is:

```python
# In ingest routes, strictly after conn.commit():
for alert in alerts_created:
    alert_id = alert.get("alert_id")
    if not alert_id:
        continue
    try:
        matched = match_playbooks(conn, alert_id)
        for definition in matched:
            create_playbook_execution(conn, definition["id"], alert_id)
        if matched:
            conn.commit()
    except Exception as playbook_error:
        current_app.logger.error(
            "[SOAR PLAYBOOK MATCH FAILED] alert_id=%s error=%s",
            alert_id,
            playbook_error,
        )
        # Does not re-raise — ingest success is not contingent on playbook matching
```

This pattern mirrors the existing enqueue and incident-creation post-commit blocks. Playbook
matching failure must not propagate to the ingest response.

**The call site is out of scope for this change.** It requires a separate spec that covers
regression testing against the six ingest regression tests.

---

## Test Strategy

### tests/test_playbook_store.py

All tests use the real test database (same pattern as `tests/test_soar_queue_visibility_api.py`).

- Create a definition with valid trigger_config — assert row is readable back with correct fields.
- List enabled definitions — assert only enabled rows returned.
- Create a disabled definition — assert it is excluded from list_enabled results.
- get_playbook_definition — returns correct row, returns None for unknown id.
- create_playbook_execution — returns integer id, row exists with status='pending'.
- create_playbook_execution with alert_id=None — row created with null alert_id.
- get_playbook_execution — returns correct row, returns None for unknown id.
- update_execution_status to 'running' — sets started_at, not completed_at.
- update_execution_status to 'success' — sets completed_at.
- update_execution_status to 'failed' — sets completed_at.
- update_execution_status with invalid status — raises ValueError.
- list_playbook_executions — returns all rows ordered by created_at DESC.
- list_playbook_executions filtered by playbook_id — returns only matching rows.
- list_playbook_executions filtered by status — returns only matching rows.
- list_playbook_executions limit — returns at most limit rows.

### tests/test_playbook_engine.py

All trigger matching tests call `_evaluate_trigger` directly — no DB required. The `match_playbooks`
function is tested with a minimal DB fixture (one definition, one alert row).

**alert_type trigger:**
- Alert with matching alert_type → True.
- Alert with non-matching alert_type → False.
- Trigger absent → True regardless of alert_type.
- Alert alert_type None → False when trigger is set.
- Case-insensitive: trigger `"PASSWORD_SPRAYING"` matches alert `"password_spraying"`.

**min_severity trigger:**
- Alert severity equals min_severity → True.
- Alert severity above min_severity → True.
- Alert severity below min_severity → False.
- Trigger absent → True regardless of severity.
- Alert severity None → False when trigger is set.
- Case-insensitive: trigger `"high"` matches alert `"HIGH"`.

**source trigger:**
- Alert source matches trigger exactly → True.
- Alert source does not match → False.
- Alert source None → False when trigger is set.
- Trigger absent → True regardless of source.

**correlation_flag trigger:**
- `correlation_flag: true` with correlated alert_type → True.
- `correlation_flag: true` with detection alert_type → False.
- `correlation_flag: false` with detection alert_type → True.
- `correlation_flag: false` with correlated alert_type → False.
- Trigger absent → True regardless of alert_type.

**reputation_score_min trigger:**
- Alert score equals threshold → True.
- Alert score above threshold → True.
- Alert score below threshold → False.
- Alert score None → False when threshold > 0.
- Alert score None with threshold = 0 → True.
- Trigger absent → True regardless of score.

**Multi-field AND logic:**
- All fields match → True.
- One field does not match → False.
- Empty trigger_config {} → True for any alert.

**match_playbooks (DB-backed):**
- No enabled definitions → returns [].
- One definition, trigger matches → returns that definition.
- One definition, trigger does not match → returns [].
- Multiple definitions, partial match → returns only matching subset.
- Disabled definition is excluded even if trigger would match.
- alert_id not found in DB → returns [].

### tests/test_playbook_registry.py

- Valid steps with supported action names → validation returns [].
- Step with unsupported action name → validation returns non-empty error list.
- Step missing "action" key → validation returns non-empty error list.
- Step with invalid on_failure value → validation returns non-empty error list.
- Empty steps list → validation returns [].

---

## Safety Boundaries

- No step execution. `playbook_engine.py` does not call any executor, adapter, or queue worker.
- No autonomous action. Matched definitions are returned as data — no side effects.
- No ingest, detection, or correlation imports. `playbook_engine.py` must not import from
  `engines/detection_engine.py`, `engines/correlation_engine.py`, `engines/ingest_engine.py`,
  or `routes/ingest_routes.py`.
- No real firewall execution. Not introduced by this change.
- No Slack, email, or PagerDuty. Not introduced by this change.
- No call site in ingest routes. Trigger matching is not wired to any ingest handler.
- No changes to `response_actions_queue`, `response_actions_log`, or any existing store.
- No frontend changes.
- No daemon, background thread, or scheduler.
- Execution records created in this phase have status `pending` and contain no step results.
  They are inert until Phase 2D provides an executor that processes them.

---

## Risks

**`CORRELATED_ALERT_TYPES` drift:** If the correlation engine adds a new correlated alert
type without updating the constant in `playbook_engine.py`, playbooks with
`correlation_flag: true` will silently fail to match the new type. Mitigation: comment the
constant with the source of truth and add a test that asserts the expected set of known
correlated types, making divergence visible.

**Disconnected execution records:** `create_playbook_execution` produces `pending` rows that
nothing processes until Phase 2D. If this phase is deployed and trigger-matching call sites
are later added before Phase 2D is complete, `pending` rows will accumulate without being
consumed. Mitigation: the call site wiring is a separate spec — do not wire call sites in
this change.

**Schema migration required for existing databases:** This change adds two new tables. Any
running environment must apply the schema additions before deploying code that imports
`core/playbook_store`. Mitigation: the two `CREATE TABLE IF NOT EXISTS` statements are
additive and do not alter existing tables, so applying them to a running production database
is low-risk.

**`steps` JSONB content is not validated by the DB:** The `steps` column accepts any JSONB.
Malformed step definitions will not surface until execution time (Phase 2D). Mitigation:
the registry's `validate_playbook_steps` function provides application-layer validation at
definition load time. Tests should assert that loading a definition with invalid steps raises
an error from the store helper.
