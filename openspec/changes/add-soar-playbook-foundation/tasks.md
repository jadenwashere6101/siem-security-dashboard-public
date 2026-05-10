# Tasks: SOAR Playbook Engine Foundation

Run these six regression tests after every step. If any fail, revert the step before
continuing. These tests cover the ingest/detection/correlation pipeline and must remain
green throughout.

```
pytest tests/test_failed_login_detection.py
pytest tests/test_password_spraying_detection.py
pytest tests/test_correlated_activity.py
pytest tests/test_targeted_correlation.py
pytest tests/test_ingest_api_contracts.py
pytest tests/test_alert_mutation_api_contracts.py
```

Do not touch ingest, detection, correlation, frontend, scheduler, daemon, any existing
route, or any existing engine module.

---

## Step 1: Schema Additions

Read `schema.sql` before making any changes. Confirm the current table list so you do not
duplicate an existing table or conflict with an existing index name.

- [ ] Add `playbook_definitions` table to `schema.sql` using `CREATE TABLE IF NOT EXISTS`.
  Columns: `id VARCHAR(64) PRIMARY KEY`, `name TEXT NOT NULL`, `description TEXT`,
  `trigger_config JSONB NOT NULL DEFAULT '{}'`, `steps JSONB NOT NULL DEFAULT '[]'`,
  `enabled BOOLEAN NOT NULL DEFAULT TRUE`, `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`,
  `updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`.

- [ ] Add index `idx_playbook_definitions_enabled ON playbook_definitions (enabled)`.

- [ ] Add `playbook_executions` table to `schema.sql` using `CREATE TABLE IF NOT EXISTS`.
  Columns: `id SERIAL PRIMARY KEY`, `playbook_id VARCHAR(64) NOT NULL REFERENCES
  playbook_definitions(id)`, `alert_id INTEGER REFERENCES alerts(id) ON DELETE SET NULL`,
  `incident_id INTEGER REFERENCES incidents(id) ON DELETE SET NULL`,
  `status VARCHAR(30) NOT NULL DEFAULT 'pending'`, `started_at TIMESTAMPTZ`,
  `completed_at TIMESTAMPTZ`, `last_completed_step INTEGER`,
  `steps_log JSONB NOT NULL DEFAULT '[]'`, `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`.

- [ ] Add indexes: `idx_playbook_executions_playbook_id`, `idx_playbook_executions_alert_id`,
  `idx_playbook_executions_status`, `idx_playbook_executions_created_at` (on `created_at DESC`).

- [ ] Confirm `schema.sql` applies cleanly on a fresh DB:
  ```bash
  python3 -c "import psycopg2, os; conn = psycopg2.connect(os.environ['DATABASE_URL']); \
  cur = conn.cursor(); cur.execute(open('schema.sql').read()); conn.commit(); conn.close(); \
  print('schema OK')"
  ```
- [ ] Run regression suite — all six green.

---

## Step 2: Store Helper — core/playbook_store.py

Read `core/incident_store.py` before writing. Match its function structure, connection
pattern, and return type conventions. Read `core/response_action_queue_store.py` for the
status-transition pattern.

- [ ] Create `core/playbook_store.py`.

- [ ] Implement `list_enabled_playbook_definitions(conn) -> list[dict]`.
  - SELECT all columns WHERE enabled = TRUE ORDER BY id ASC.
  - Return list of dicts with all columns. `trigger_config` and `steps` are parsed
    Python objects (psycopg2 returns JSONB as Python dicts/lists automatically).

- [ ] Implement `get_playbook_definition(conn, playbook_id: str) -> dict | None`.
  - SELECT all columns WHERE id = %s. Return None if no row.

- [ ] Implement `create_playbook_execution(conn, playbook_id: str, alert_id: int | None, incident_id: int | None = None) -> int`.
  - INSERT with status='pending', RETURNING id.
  - Return the integer execution id.

- [ ] Implement `get_playbook_execution(conn, execution_id: int) -> dict | None`.
  - SELECT all columns WHERE id = %s. Return None if no row.

- [ ] Implement `update_execution_status(conn, execution_id: int, status: str, now=None) -> None`.
  - Validate status is one of: `pending`, `running`, `success`, `failed`, `abandoned`.
    Raise `ValueError` for any other value.
  - Set `started_at = now` when transitioning to `running`, if `started_at` is currently NULL.
  - Set `completed_at = now` when transitioning to `success`, `failed`, or `abandoned`.
  - Default `now` to `datetime.utcnow()` if not passed.

- [ ] Implement `list_playbook_executions(conn, playbook_id=None, status=None, limit=50) -> list[dict]`.
  - Build WHERE clause dynamically from provided filters.
  - ORDER BY created_at DESC. Apply LIMIT.

Verification:

- [ ] Run `python3 -m py_compile core/playbook_store.py`.
- [ ] Run regression suite — all six green.

---

## Step 3: Registry Scaffold — engines/playbook_registry.py

Read `engines/soar_errors.py` and `engines/soar_executor.py` for context on how other engine
modules are structured. The registry does not import from either — this is just for orientation.

- [ ] Create `engines/playbook_registry.py`.

- [ ] Define `SUPPORTED_ACTIONS: frozenset[str]` containing `"block_ip"`, `"monitor"`,
  `"flag_high_priority"`. These match the three action types currently handled by
  `SimulationExecutor` in `engines/soar_executor.py`.

- [ ] Implement `validate_playbook_steps(steps: list[dict]) -> list[str]`.
  - Returns a list of error strings. Empty list means valid.
  - Each step must be a dict → error if not.
  - Each step must have an `"action"` key → error if missing.
  - Each `"action"` value must be in `SUPPORTED_ACTIONS` → error if not.
  - If `"on_failure"` is present, it must be `"abort"` or `"continue"` → error if not.
  - Do not validate `"params"` — param shapes are action-specific and validated at execution
    time in Phase 2D.

Verification:

- [ ] Run `python3 -m py_compile engines/playbook_registry.py`.
- [ ] Run regression suite — all six green.

---

## Step 4: Trigger Matching Engine — engines/playbook_engine.py

Read `core/playbook_store.py` (just written) before implementing. Read
`engines/soar_enqueue_orchestrator.py` for the post-commit logging pattern.

- [ ] Create `engines/playbook_engine.py`.

- [ ] Define module-level constant `CORRELATED_ALERT_TYPES: frozenset[str]` containing
  `"correlated_activity"`, `"web_to_app_attack_pattern"`, `"spray_then_success_pattern"`,
  `"cloud_app_error_pattern"`. Add a comment citing `engines/correlation_engine.py` as the
  source of truth for these values.

- [ ] Define module-level constant `SEVERITY_RANK: dict[str, int]` mapping lowercase severity
  strings to integers: `"low": 1`, `"medium": 2`, `"high": 3`, `"critical": 4`.

- [ ] Implement `_fetch_alert(conn, alert_id: int) -> dict | None`.
  - SELECT all columns from `alerts` WHERE id = %s.
  - Return dict with all columns, or None if not found.
  - Cast `source_ip` to string (host()) to avoid inet type handling issues.

- [ ] Implement `_evaluate_trigger(trigger_config: dict, alert: dict) -> bool`.
  - Pure function — no DB calls, no imports from Flask or engines.
  - `alert_type`: if set in trigger_config, compare case-insensitively. None alert field → False.
  - `min_severity`: if set, use SEVERITY_RANK. Alert severity missing from SEVERITY_RANK → False.
    Trigger severity missing from SEVERITY_RANK → False.
  - `source`: if set, compare case-insensitively. Alert source None or empty → False when
    trigger value is non-empty.
  - `correlation_flag`: if True, `alert["alert_type"] in CORRELATED_ALERT_TYPES`.
    If False, `alert["alert_type"] not in CORRELATED_ALERT_TYPES`. Alert alert_type None → False.
  - `reputation_score_min`: if set, treat alert `reputation_score` None as 0.
    `(alert.get("reputation_score") or 0) >= trigger_config["reputation_score_min"]`.
  - Unrecognized keys in trigger_config must be silently ignored (forward-compatibility).
  - All evaluated conditions must be True to return True.

- [ ] Implement `match_playbooks(conn, alert_id: int) -> list[dict]`.
  - Call `_fetch_alert(conn, alert_id)`. If None, log a warning and return [].
  - Call `list_enabled_playbook_definitions(conn)` from `core.playbook_store`.
  - For each definition, call `_evaluate_trigger(definition["trigger_config"], alert)`.
  - Return the list of matching definitions (full definition dicts).
  - Wrap in try/except. On unexpected exception, log an error and return [].
  - Do NOT call `create_playbook_execution` — the caller decides what to do with matches.

- [ ] Confirm `engines/playbook_engine.py` does NOT import from:
  - `engines/detection_engine.py`
  - `engines/correlation_engine.py`
  - `engines/ingest_engine.py`
  - `routes/ingest_routes.py`
  - Flask `request` or `current_app` (logging via Python `logging` module is fine)

Verification:

- [ ] Run `python3 -m py_compile engines/playbook_engine.py`.
- [ ] Run regression suite — all six green.

---

## Step 5: Store Tests — tests/test_playbook_store.py

Read `tests/test_soar_queue_visibility_api.py` and `tests/test_soar_enqueue_orchestrator.py`
before writing. Use the same DB fixture pattern (real test database, not mocked). Do not mock
the DB in these tests.

- [ ] Create `tests/test_playbook_store.py`.

- [ ] Test `list_enabled_playbook_definitions`:
  - [ ] Returns empty list when no definitions exist.
  - [ ] Returns enabled definition after insertion.
  - [ ] Excludes disabled definitions.
  - [ ] Returns multiple enabled definitions in id ASC order.

- [ ] Test `get_playbook_definition`:
  - [ ] Returns correct row for known id.
  - [ ] Returns None for unknown id.
  - [ ] `trigger_config` is returned as a Python dict, not a JSON string.

- [ ] Test `create_playbook_execution`:
  - [ ] Returns an integer id.
  - [ ] Row exists with status='pending', started_at=None, completed_at=None.
  - [ ] `alert_id=None` is accepted without error.
  - [ ] `incident_id=None` is accepted without error.

- [ ] Test `get_playbook_execution`:
  - [ ] Returns correct row for known id.
  - [ ] Returns None for unknown id.

- [ ] Test `update_execution_status`:
  - [ ] Transition to 'running': started_at set, completed_at still None.
  - [ ] Transition to 'success': completed_at set.
  - [ ] Transition to 'failed': completed_at set.
  - [ ] Transition to 'abandoned': completed_at set.
  - [ ] Invalid status string raises ValueError.

- [ ] Test `list_playbook_executions`:
  - [ ] Returns all rows when no filters applied, ordered by created_at DESC.
  - [ ] Filter by playbook_id returns only rows for that definition.
  - [ ] Filter by status returns only matching rows.
  - [ ] Limit is respected.

- [ ] Run: `pytest tests/test_playbook_store.py -x --tb=short -v`
- [ ] Run regression suite — all six green.

---

## Step 6: Engine Tests — tests/test_playbook_engine.py

All `_evaluate_trigger` tests must be pure unit tests with no DB connection. The
`match_playbooks` tests use a minimal real-DB fixture.

Read `tests/test_soar_executor.py` for the pure-function test pattern.

- [ ] Create `tests/test_playbook_engine.py`.

**`_evaluate_trigger` — alert_type:**
- [ ] Matching alert_type → True.
- [ ] Non-matching alert_type → False.
- [ ] Trigger absent → True regardless of alert_type.
- [ ] Alert alert_type None, trigger set → False.
- [ ] Case-insensitive: trigger `"PASSWORD_SPRAYING"` matches alert `"password_spraying"`.

**`_evaluate_trigger` — min_severity:**
- [ ] Alert severity equal to min_severity → True.
- [ ] Alert severity above min_severity (HIGH vs LOW) → True.
- [ ] Alert severity below min_severity (LOW vs HIGH) → False.
- [ ] Trigger absent → True regardless of severity.
- [ ] Alert severity None, trigger set → False.
- [ ] Case-insensitive: trigger `"HIGH"` matches alert `"high"`.

**`_evaluate_trigger` — source:**
- [ ] Alert source matches trigger → True.
- [ ] Alert source does not match → False.
- [ ] Alert source None, trigger set to non-empty string → False.
- [ ] Trigger absent → True regardless of source.

**`_evaluate_trigger` — correlation_flag:**
- [ ] `correlation_flag: True` with correlated alert_type (`"correlated_activity"`) → True.
- [ ] `correlation_flag: True` with detection alert_type (`"password_spraying"`) → False.
- [ ] `correlation_flag: False` with detection alert_type → True.
- [ ] `correlation_flag: False` with correlated alert_type → False.
- [ ] Trigger absent → True regardless of alert_type.

**`_evaluate_trigger` — reputation_score_min:**
- [ ] Alert score equal to threshold → True.
- [ ] Alert score above threshold → True.
- [ ] Alert score below threshold → False.
- [ ] Alert score None, threshold > 0 → False (None treated as 0).
- [ ] Alert score None, threshold = 0 → True.
- [ ] Trigger absent → True regardless of score.

**`_evaluate_trigger` — multi-field AND logic:**
- [ ] All fields match → True.
- [ ] One field does not match → False.
- [ ] Empty trigger_config `{}` → True for any alert.
- [ ] Unrecognized key in trigger_config is ignored (no error, match continues).

**`match_playbooks` — DB-backed:**
- [ ] No enabled definitions → returns [].
- [ ] One definition, trigger matches alert → returns list with that definition.
- [ ] One definition, trigger does not match → returns [].
- [ ] Two definitions, one matches → returns only the matching one.
- [ ] Disabled definition excluded even if trigger_config would match.
- [ ] alert_id not found in DB → returns [] (no exception raised).

**Registry tests — tests/test_playbook_registry.py:**
- [ ] Create `tests/test_playbook_registry.py`.
- [ ] Valid steps list → `validate_playbook_steps` returns [].
- [ ] Step with unknown action name → returns non-empty error list.
- [ ] Step missing "action" key → returns non-empty error list.
- [ ] Step with invalid on_failure value → returns non-empty error list.
- [ ] Empty steps list → returns [].

- [ ] Run: `pytest tests/test_playbook_engine.py tests/test_playbook_registry.py -x --tb=short -v`
- [ ] Run regression suite — all six green.

---

## Step 7: Regression and Safety Audit

- [ ] Run full backend test suite: `pytest tests/ -x --tb=short -v`
- [ ] Assert all pre-existing tests pass without modification.
- [ ] Confirm `engines/playbook_engine.py` imports were not added to any existing module.
- [ ] Confirm no existing engine file was modified (`detection_engine.py`, `correlation_engine.py`,
  `ingest_engine.py`, `soar_action_worker.py`, `soar_executor.py`, `soar_errors.py`,
  `soar_enqueue_orchestrator.py`).
- [ ] Confirm `routes/ingest_routes.py` was not modified.
- [ ] Confirm `core/response_action_queue_store.py` was not modified.
- [ ] Confirm `schema.sql` has only additive changes (two new tables, four new indexes —
  no DROP, ALTER, or RENAME on existing tables).
- [ ] Confirm no frontend file was modified.
- [ ] Confirm no scheduler, daemon, cron, or background thread was introduced.
- [ ] Confirm `match_playbooks` does not call any executor or adapter.
- [ ] Confirm `create_playbook_execution` is not called from anywhere in this change
  (it is exposed for use by the future call-site wiring spec).
- [ ] Confirm `git status` shows only the files introduced by this change:
  - `schema.sql`
  - `core/playbook_store.py`
  - `engines/playbook_engine.py`
  - `engines/playbook_registry.py`
  - `tests/test_playbook_store.py`
  - `tests/test_playbook_engine.py`
  - `tests/test_playbook_registry.py`

---

## Suggested Verification Commands

```bash
python3 -m py_compile core/playbook_store.py engines/playbook_engine.py engines/playbook_registry.py

pytest tests/test_playbook_store.py tests/test_playbook_engine.py tests/test_playbook_registry.py \
  -x --tb=short -v

pytest tests/test_failed_login_detection.py tests/test_password_spraying_detection.py \
  tests/test_correlated_activity.py tests/test_targeted_correlation.py \
  tests/test_ingest_api_contracts.py tests/test_alert_mutation_api_contracts.py \
  -x --tb=short -v

pytest tests/ -x --tb=short -v

git diff --stat HEAD
git status --short
```
