# SIEM → SOAR Upgrade Roadmap

---

## 1. CLEAR DEFINITION

### What You Have (SIEM)
Your system does detection, enrichment, correlation, and initiates response actions — further than most SIEMs. But those response actions are:
- Synchronous (blocking your ingest transaction)
- Single-step (one action per alert, no sequences)
- Reputation-score-only triggered (no conditional logic)
- Simulated (`block_ip` doesn't call a real firewall API)
- No outbound human notification (no Slack/email)

### What SOAR Adds That You're Missing

| Capability | SOAR Definition | Your Current State |
|---|---|---|
| **Playbooks** | Multi-step, conditional, automated response workflows | None — only `execute_response_action()` single-step |
| **Incident Management** | Case lifecycle grouping multiple alerts | Alerts exist but no incident/case layer |
| **Async Execution** | Response actions run outside ingest transaction | Response runs synchronously inside ingest |
| **Notification** | Alert humans via Slack, email, PagerDuty | No outbound notifications |
| **External Integrations** | Call real firewall APIs, ticketing, threat intel | AbuseIPDB only; block_ip is simulated |
| **Idempotency + Retry** | Safe to re-run actions; retries on failure | No retry logic, no dedup on actions |
| **Human-in-the-Loop** | Approve high-risk actions before execution | None — all actions run immediately |
| **Playbook Audit Trail** | Full step-by-step execution log | `response_actions_log` exists but is flat |

### The Core Difference
Your SIEM *suggests and logs* a response. A SOAR *orchestrates and executes* a full workflow — with branching, retries, notifications, approvals, and real integrations.

---

## CRITICAL CONSTRAINTS: Do Not Touch During SOAR Upgrade

The following areas must **not** be modified during any phase of the SOAR upgrade. They are load-bearing for your existing detection/correlation behavior and test suite.

| Area | Why It's Off-Limits |
|---|---|
| `backend_detection_engine.py` internals | Detection runs inside the ingest transaction and relies on reading its own uncommitted writes via the same cursor. Any refactor risks breaking this visibility guarantee silently — tests may still pass while production behavior changes. |
| `backend_correlation_engine.py` internals | Correlation reads uncommitted alert rows written by detection in the same transaction. It is tightly coupled to exact alert schema and insert timing. |
| `backend_ingest_engine.py` routing logic | The `event_type` routing map is the central dispatch for all sources. A change here breaks every adapter and every ingest test simultaneously. |
| `ingest_routes.py` transaction flow | `conn`/`cur` is passed through the entire ingest → detection → correlation call chain. Inserting async work at the wrong point in this chain will silently break atomicity. |
| pytest patch target paths (e.g. `patch("backend_detection_engine.lookup_ip_reputation")`) | Tests mock functions by their fully-qualified module path. If you rename or move a module, existing patches stop applying — tests pass but the real function runs, producing false confidence. Any module rename requires updating **all** patch targets in **all** test files simultaneously. |
| `SERIAL` / `currval` sequence behavior | Correlation and detection use `currval()` to read recently inserted alert IDs within the transaction. Do not change alert insert patterns in a way that disrupts sequence cursor behavior. |

> **Rule:** If a proposed change requires touching any of these as a prerequisite, stop and reconsider the approach. Build around them, not through them.

---

## 2. PHASED ROADMAP

---

### Phase 1 — Foundation: Decouple Response from Ingest + Incident Layer
**Goal:** Make your existing response system safe to build on. Nothing new executes yet — laying the ground floor.

**Risk level:** Very low. You're adding, not modifying.

**Why first:** Everything in Phases 2–5 depends on async execution and incident grouping.

#### Features

**1A. Async Action Queue**

> **⚠ CRITICAL — TRANSACTION BOUNDARY:** Your ingest → detection → correlation pipeline runs inside a SINGLE PostgreSQL transaction. Detection reads its own uncommitted writes via the same cursor; correlation does the same. Enqueueing must happen **strictly after** `conn.commit()` closes the transaction — never inside it. Enqueuing mid-transaction risks executing the worker before alert rows are visible, causing silent failures in response logic.

- Add a lightweight in-process queue (Python `queue.Queue` or DB-backed task table) so response actions are no longer called inside the ingest transaction
- `execute_response_action()` in `core/ip_helpers.py` currently runs synchronously during detection — move to post-commit execution only
- A background worker thread (or APScheduler job) drains the queue and executes actions
- This is the single most important architectural change in the entire roadmap
- Worker thread must open its own DB connection — never reuse the ingest `conn`/`cur`

**Safe call site pattern** — in `ingest_routes.py`, after the ingest transaction:
- `conn.commit()` closes the transaction first
- `async_queue.enqueue(action_type, alert_id)` runs only after — alert row is now visible to the worker

**Recommended alternative: DB-backed `pending_actions` table**
- Insert a row into `pending_actions` inside the same alert transaction (committed atomically with the alert)
- Polling worker queries `WHERE status = 'pending'` — executes only after commit, never mid-transaction
- Survives process restarts; no in-memory state lost on crash
- Clean upgrade path to Redis/RQ in Phase 5 without changing worker logic

**1B. Idempotency + Retry on `response_actions_log`**
- Add `idempotency_key` column (e.g. `sha256(action_type + target_ip + alert_id)`)
- Add `attempt_count`, `last_attempted_at`, `error_message` columns
- Add `max_retries` config constant
- Before executing any action, check if it already ran successfully via idempotency key
- Does NOT change what actions do — only adds safety around them

**1C. Incident Management Table**
- New table: `incidents` — groups one or more alerts into a case
- Columns: `id`, `title`, `severity`, `priority` (P1–P4 — distinct from severity), `status` (open/investigating/resolved/closed), `created_at`, `resolved_at`, `assigned_to` (FK to users)
- **Do NOT add a `source_alert_ids` column** — use the `incident_alerts` join table as the authoritative link. Storing IDs in an array column creates update anomalies and breaks dedup logic. The join table is already in the schema — use it.
- Auto-create an incident when a HIGH or CRITICAL alert is created
- Does NOT change alerts — incidents are a layer on top
- **Deduplication rule:** before creating a new incident, check `incident_alerts` for any open incident linked to the same `source_ip` within a configurable window (default 1 hour) — if found, link the alert to the existing incident instead of creating a new one
- **Priority vs. severity distinction:** severity describes the threat level of the triggering alert; priority describes how urgently the incident needs analyst attention (factors in: business hours, asset criticality, repeated IPs). They should not always match.

**1D. Incident Routes**
- `GET /incidents` — list with filtering
- `GET /incidents/<id>` — detail with linked alerts
- `POST /incidents/<id>/status` — update lifecycle
- `POST /incidents/<id>/assign` — assign to analyst

**1E. Early Observability (Do Not Skip)**

> **⚠ WARNING:** Deferring all observability to Phase 5 is risky. If the async worker silently fails in Phase 1, you will not know until alerts stop generating responses — with no logs to debug. Add minimal observability at the start.

- Add structured logging to `core/async_queue.py`: log every enqueue and every execution attempt with `alert_id`, `action_type`, `timestamp`, `status`, `error`
- Log worker thread start/stop/crash events (use Python `logging` module, not `print`)
- Add a `GET /health/worker` endpoint that returns queue depth and last execution timestamp — lets you verify the worker is alive without querying logs
- Queue depth monitoring: if queue depth exceeds a configurable threshold (e.g. 50 items), log a `WARNING` — early signal that the worker is falling behind

#### Where It Lives
```
core/
  async_queue.py           ← NEW: queue + worker thread
  ip_helpers.py            ← MODIFY: decouple execute_response_action from ingest flow
schema.sql                 ← ADD: incidents table, new columns on response_actions_log
routes/
  incident_routes.py       ← NEW
  health_routes.py         ← NEW: GET /health/worker
```

#### Dependencies
None — this is the base.

---

### Phase 2 — Playbook Engine: Definition + Triggered Execution
**Goal:** Define playbooks as structured multi-step sequences. Wire them to alert conditions. Execute through the async queue.

**Risk level:** Low-medium. New engine, not touching existing engines.

#### Features

**2A. Playbook Definitions**
- Playbooks defined as Python dicts or JSON config (not code)
- Schema per playbook:
  ```
  {
    "id": "block_and_notify",
    "trigger": { "alert_type": "password_spraying", "min_severity": "HIGH" },
    "steps": [
      { "action": "block_ip", "params": {} },
      { "action": "notify_slack", "params": { "channel": "#soc-alerts" } },
      { "action": "create_incident", "params": { "severity": "HIGH" } }
    ],
    "on_failure": "continue"  // or "abort"
  }
  ```
- Store playbook definitions in `playbook_definitions` table (so admins can enable/disable without deploys)

**2B. Playbook Trigger Matching**
- After alerts are written to DB (post-detection, post-correlation), run `match_playbooks(alert)` in `engines/playbook_engine.py`
- Match on: `alert_type`, `severity`, `source`, reputation score range, correlation flag
- Return list of matching playbook definitions

**2C. Playbook Execution Records**
- New table: `playbook_executions` — one row per playbook run
- Columns: `id`, `playbook_id`, `alert_id`, `incident_id`, `status`, `started_at`, `completed_at`, `last_completed_step` (INTEGER — checkpoint index for crash resumption), `steps_log` (JSONB — per-step result, timestamp, output, error)
- Each step in `steps_log` must carry explicit state: `pending` → `running` → `success` | `failed` | `skipped`
- **Step-level idempotency:** each step entry includes a `step_idempotency_key` (e.g. `sha256(execution_id + step_index + action_name)`). Before executing a step, check if it already has `status: success` — if so, skip it. This is required for safe retry and crash resumption.
- `last_completed_step` is updated atomically after each successful step and is used to resume mid-playbook after a worker crash without re-running already-completed steps

**2D. Step Executor**
- `engines/playbook_engine.py` → `execute_playbook(playbook_def, alert, conn)`
- Iterates steps, calls action handlers from a registry dict
- Respects `on_failure` per-step (`continue` or `abort`)
- All execution goes through the Phase 1 async queue — **never blocks the request/response cycle**
- Playbooks must never be called synchronously from a Flask route handler or from inside the ingest transaction

**Per-step retry strategy** (add to step definition schema):
- `"max_retries": 3` — per-step override; falls back to global default if not set
- `"retry_delay_seconds": 10` — backoff between attempts
- `"retry_on": ["timeout", "connection_error"]` — only retry transient errors; do not retry `permission_denied` or `already_blocked`
- Steps that exhaust retries mark as `failed` and respect the `on_failure` policy

**2E. Failure + Safety Design**

> **⚠ Critical:** A `queue.Queue`-based worker can crash mid-playbook and lose all in-flight state. Design for this from day one or you will rebuild this later under pressure.

- **Worker crash mid-playbook:** On restart, the worker must query `playbook_executions WHERE status = 'running'` and attempt to resume from `last_completed_step`. Steps with `status: success` in `steps_log` are skipped; steps with `status: running` are treated as unknown — re-execute with idempotency key protection.
- **Partial action execution:** If a step starts (e.g. Slack message sent) but the DB write confirming success fails, the step will re-run on resume. This is why step-level idempotency keys (2C) are non-negotiable — external actions must be safe to call twice.
- **Resumable execution:** `execute_playbook()` must accept a `resume_from_step` parameter. When called on the crash-recovery path, it skips to the correct step index and checks the idempotency key before calling the action handler.
- **Atomic step checkpoint:** After each step completes, update `last_completed_step` and `steps_log` in a single DB write before advancing. If this write fails, the step is safe to retry.

#### Where It Lives
```
engines/
  playbook_engine.py       ← NEW: trigger matching + step execution
  playbook_registry.py     ← NEW: maps action names to handler functions
schema.sql                 ← ADD: playbook_definitions, playbook_executions tables
routes/
  playbook_routes.py       ← NEW: GET /playbooks, GET /playbooks/<id>/executions
```

#### Dependencies
Phase 1 (async queue, idempotency).

---

### Phase 3 — Real Integrations: Notifications + External Actions
**Goal:** Replace simulated actions with real ones. Wire up Slack, email, and firewall adapter.

**Risk level:** Medium. Outbound network calls — safe to add, but test in staging first.

#### Features

**3A. Integration Adapter Pattern**
- New package: `integrations/`
- Each adapter implements a common interface:
  ```python
  class BaseIntegration:
      def execute(self, action: str, params: dict) -> dict: ...
      def test_connection(self) -> bool: ...
  ```
- Adapters: `slack_adapter.py`, `email_adapter.py`, `firewall_adapter.py`, `pagerduty_adapter.py`
- Config for each adapter stored in env vars or a `integration_config` table

**3B. Slack Adapter**
- Posts formatted alert summaries to a configurable webhook URL
- Payload includes: alert type, severity, source IP, MITRE technique, playbook name, incident link
- Uses Slack Block Kit for rich formatting
- Action: `notify_slack`

**3C. Email Adapter**
- SMTP-based (or SendGrid) for alert digests and critical escalations
- Templated HTML emails
- Action: `notify_email`

**3D. Firewall Adapter (Real block_ip)**
- Abstract firewall interface with concrete implementations per vendor
- Initial implementation: write to a file/API that your firewall can consume
- Replaces the "Simulated IP block" log in `core/ip_helpers.py`
- Action: `block_ip` (now real)

**3E. Threat Intel Adapter**
- Extend beyond AbuseIPDB — add VirusTotal or Shodan for deeper enrichment
- Called during enrichment phase, result stored in alert `raw_payload` or new `enrichment` column
- Action: `enrich_ip`

**3F. Circuit Breaker Pattern per Integration**
- Each adapter must implement a circuit breaker: after N consecutive failures, the adapter enters `OPEN` state and skips all calls for a cooldown window (e.g. 5 minutes), then enters `HALF-OPEN` to probe recovery
- Prevents a flapping Slack webhook or downed firewall API from filling your dead letter queue with thousands of failed retries during an outage
- State tracked per-adapter in memory (reset on worker restart is acceptable for now) or in a lightweight `integration_circuit_state` table
- `circuit_state` is checked before every `execute()` call in the base class — adapters do not need to implement it themselves

**3G. Timeout + Retry per Adapter**
- Every `execute()` call must have an explicit timeout (default: 5s, configurable per adapter)
- Timeout failures are classified as transient — eligible for retry per the step's `retry_on` policy
- Do not retry non-transient errors (HTTP 401, 404, malformed payload)
- Adapter-level `max_retries` and `retry_delay_seconds` override playbook step defaults when set

**3H. Simulation Mode vs. Real Execution Mode**
- Add `INTEGRATION_MODE` env var with values `simulation` and `real`
- In `simulation` mode (default for dev/test): every adapter's `execute()` logs the action with `[SIMULATED]` prefix and returns `{"success": True, "simulated": True}` without making any network call
- In `real` mode: adapters make actual outbound calls
- This replaces the current `"Simulated IP block"` pattern in `core/ip_helpers.py` with a consistent, system-wide mechanism
- All pytest runs must use `INTEGRATION_MODE=simulation` — no network calls in tests, ever

#### Where It Lives
```
integrations/
  base_integration.py      ← NEW: abstract interface
  slack_adapter.py         ← NEW
  email_adapter.py         ← NEW
  firewall_adapter.py      ← NEW
  threat_intel_adapter.py  ← NEW
  integration_registry.py  ← NEW: maps adapter names to instances
```

#### Dependencies
Phase 2 (playbook step executor calls integration adapters by name).

---

### Phase 4 — Human-in-the-Loop: Approvals + Case Management
**Goal:** Add approval gates for high-risk actions. Expand incident management into a full case workflow.

**Risk level:** Low. Purely additive — adds wait states before existing actions.

#### Features

**4A. Approval Gates in Playbooks**
- New step type: `{ "action": "require_approval", "params": { "role": "super_admin", "timeout_hours": 4 } }`
- Execution pauses and creates an `approval_requests` table entry
- Analyst approves/denies via new endpoint: `POST /approvals/<id>/decision`
- On approval: playbook resumes from next step
- On denial or timeout: playbook marks step as skipped or aborts

**4B. Approval Notification**
- When an approval is created, automatically trigger a Slack/email notification to the required role
- Notification includes: what action is waiting, the triggering alert, a deep link to approve

**4C. Case Timeline**
- Expand incident detail endpoint to return a full chronological timeline:
  - When each alert was added
  - When the incident was created
  - When playbooks ran and what each step did
  - When an analyst made a note or changed status
  - When approvals were requested and granted
- Sourced from joining `alerts`, `playbook_executions`, `alert_notes`, `audit_log`, `approval_requests`

**4D. Alert → Incident Auto-Linking**
- When a new HIGH/CRITICAL alert shares an IP with an existing open incident, auto-link it rather than creating a new incident
- Configurable dedup window (e.g. 1 hour)

#### Where It Lives
```
schema.sql                 ← ADD: approval_requests table
routes/
  approval_routes.py       ← NEW: GET /approvals, POST /approvals/<id>/decision
  incident_routes.py       ← EXTEND: add timeline endpoint
core/
  approval_helpers.py      ← NEW: approval creation, timeout checking, notification trigger
```

#### Dependencies
Phase 2 (playbook execution model), Phase 3 (notifications).

---

### Phase 5 — Operational Hardening + Metrics
**Goal:** Make the SOAR production-grade. Add observability, tuning, and reliability.

**Risk level:** Very low. Purely additive.

#### Features

**5A. Playbook Metrics**
- Track: execution count, success rate, mean execution time, most common failure step
- Store aggregates in `playbook_metrics` table or compute on-the-fly from `playbook_executions`
- Expose via `GET /metrics/playbooks`

**5B. Alert Fatigue Tracking**
- Count how many alerts per rule close as false-positive / no-action
- Surface in admin detection rule config so analysts can see which rules generate noise
- Feed into detection rule tuning recommendations

**5C. Scheduled Playbooks (Future Spec Only)**
- Time-based playbooks are not part of the current SOAR implementation.
- The legacy `playbook_schedules` table is intentionally inert after `playbook-schedules-resolution`.
- Any future scheduler must be designed in a separate approved spec with explicit requirements.

**5D. Dead Letter Queue**
- Actions that fail all retries go to a `failed_actions` table (dead letter queue)
- Admin endpoint to review, retry, or dismiss failed actions
- Alert on dead letter queue depth > threshold

**5E. Rate Limiting on Integrations**
- Per-integration rate limiter to avoid hammering Slack/email on alert floods
- Configurable per adapter: `max_per_minute`, `burst_limit`
- Dedup notifications for same incident within window

#### Where It Lives
```
core/
  async_queue.py           ← EXTEND: dead letter queue, rate limiting
routes/
  metrics_routes.py        ← NEW: playbook + detection metrics
schema.sql                 ← ADD: failed_actions, playbook_metrics tables
```

#### Dependencies
Phases 1–4 (hardening everything built so far).

---

## 3. ARCHITECTURE CHANGES

### New Modules/Packages

```
siem-security-dashboard-public/
├── core/
│   ├── async_queue.py           ← Phase 1: async action worker
│   ├── approval_helpers.py      ← Phase 4: approval gate logic
│   └── ip_helpers.py            ← MODIFY Phase 1: decouple from ingest
├── engines/
│   ├── playbook_engine.py       ← Phase 2: trigger matching + execution
│   └── playbook_registry.py     ← Phase 2: action name → handler map
├── integrations/                ← Phase 3: NEW package
│   ├── base_integration.py
│   ├── slack_adapter.py
│   ├── email_adapter.py
│   ├── firewall_adapter.py
│   ├── threat_intel_adapter.py
│   └── integration_registry.py
└── routes/
    ├── incident_routes.py       ← Phase 1
    ├── playbook_routes.py       ← Phase 2
    ├── approval_routes.py       ← Phase 4
    └── metrics_routes.py        ← Phase 5
```

### How New Modules Interact With Existing Pipeline

```
[ingest] → [detection] → [correlation]
                ↓
         [alerts written to DB]
                ↓
    [playbook_engine.match_playbooks(alert)]   ← NEW, post-commit
                ↓
    [async_queue.enqueue(playbook_execution)]  ← NEW, non-blocking
                ↓
    [playbook_engine.execute_playbook()]       ← NEW, background thread
         ↓              ↓             ↓
  [block_ip real]  [notify_slack]  [create_incident]
  [firewall adapter] [slack adapter] [incidents table]
```

The key: ingest/detection/correlation are **not touched**. The SOAR layer starts *after* alerts are committed.

### Required Schema Changes

**Phase 1:**
```sql
ALTER TABLE response_actions_log
  ADD COLUMN idempotency_key VARCHAR(64) UNIQUE,
  ADD COLUMN attempt_count INTEGER DEFAULT 0,
  ADD COLUMN last_attempted_at TIMESTAMPTZ,
  ADD COLUMN error_message TEXT;

CREATE TABLE incidents (
  id SERIAL PRIMARY KEY,
  title TEXT NOT NULL,
  severity VARCHAR(20),
  status VARCHAR(30) DEFAULT 'open',
  assigned_to INTEGER REFERENCES users(id),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  resolved_at TIMESTAMPTZ
);

CREATE TABLE incident_alerts (
  incident_id INTEGER REFERENCES incidents(id),
  alert_id INTEGER REFERENCES alerts(id),
  PRIMARY KEY (incident_id, alert_id)
);
```

**Phase 2:**
```sql
CREATE TABLE playbook_definitions (
  id VARCHAR(64) PRIMARY KEY,
  name TEXT,
  trigger_config JSONB,
  steps JSONB,
  enabled BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE playbook_executions (
  id SERIAL PRIMARY KEY,
  playbook_id VARCHAR(64) REFERENCES playbook_definitions(id),
  alert_id INTEGER REFERENCES alerts(id),
  incident_id INTEGER REFERENCES incidents(id),
  status VARCHAR(30),
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  steps_log JSONB DEFAULT '[]'
);
```

**Phase 4:**
```sql
CREATE TABLE approval_requests (
  id SERIAL PRIMARY KEY,
  playbook_execution_id INTEGER REFERENCES playbook_executions(id),
  step_index INTEGER,
  required_role VARCHAR(30),
  status VARCHAR(20) DEFAULT 'pending',
  decided_by INTEGER REFERENCES users(id),
  decided_at TIMESTAMPTZ,
  expires_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 4. AUTOMATION / PLAYBOOK DESIGN

### How Playbooks Work

- Defined as structured data (JSON/dict), not executable code
- Stored in `playbook_definitions` table — admins can enable/disable/edit without deploys
- Each playbook has a `trigger` block and a `steps` array
- Steps are named actions resolved via `playbook_registry.py` at runtime

### Trigger Mechanism

```
After alert committed to DB:
  playbook_engine.match_playbooks(alert) →
    for each enabled playbook:
      if trigger.alert_type matches AND trigger.min_severity matches:
        enqueue execution
```

Trigger matching supports:
- `alert_type` (exact match or wildcard)
- `min_severity` (CRITICAL > HIGH > MEDIUM > LOW)
- `source` (bank_app, nginx, azure_insights)
- `correlation_flag` (only trigger on correlated alerts)
- `reputation_score_min`

### How Steps Execute Actions

Each step maps to a registered handler:
```python
PLAYBOOK_REGISTRY = {
    "block_ip":        block_ip_handler,
    "notify_slack":    slack_adapter.execute,
    "notify_email":    email_adapter.execute,
    "enrich_ip":       threat_intel_adapter.execute,
    "create_incident": incident_handler,
    "require_approval": approval_gate_handler,
    "add_to_blocklist": blocklist_handler,
}
```

All handlers receive `(params, context)` where `context` carries alert, incident, prior step outputs.

### Rule-Based vs Workflow-Based

**Recommendation: Rule-based (for now), workflow-capable later.**

Your existing system is rule-based (thresholds → actions). Keep that pattern for playbooks. Steps execute sequentially; branching is handled by `on_failure: abort|continue` and `require_approval` gates. Full workflow/DAG engines (like Airflow or Temporal) are overkill until you have 20+ playbooks with complex branching.

---

## 5. RESPONSE ENGINE DESIGN

### Evolving `execute_response_action()` Without Breaking It

Current flow (DO NOT BREAK):
```
ingest_normalized_event()
  → detection_engine creates alert
  → execute_response_action() called inline
  → response_actions_log row inserted
```

Target flow (Phase 1 change):
```
ingest_normalized_event()
  → detection_engine creates alert
  → alert committed to DB
  → async_queue.enqueue(action_type, alert_id)  ← replaces inline call
  [transaction closes]
  [background worker]
  → execute_response_action() called
  → response_actions_log row inserted
```

**The function signature doesn't change.** Only the call site moves from inside the transaction to after it.

### Preserving `response_actions_log`

- Keep the table and all existing columns — don't rename or remove
- Add new columns (idempotency_key, attempt_count, etc.) as `ALTER TABLE` — non-breaking
- Playbook step execution also writes to this table (action_type = step name, alert_id = triggering alert)
- So `response_actions_log` becomes the universal action audit trail for both old single-step and new playbook-step actions

### Safety Guarantees

| Guarantee | Implementation |
|---|---|
| **Idempotency** | `idempotency_key` unique constraint — duplicate actions silently skip |
| **Retries** | Worker retries up to `max_retries` on transient errors (network, timeout) |
| **Audit log** | Every attempt logged with timestamp and error message |
| **Dead letter** | Exhausted retries → `failed_actions` table (Phase 5) |
| **No double-block** | `blocked_ips` table check before inserting — already exists, keep it |

---

## 6. INTEGRATIONS

### What a Real SOAR Should Support

| Integration | Purpose | Priority |
|---|---|---|
| **Slack** | Alert notifications, approval requests, incident updates | High |
| **Email (SMTP/SendGrid)** | Critical escalations, daily digests | High |
| **Firewall API** | Real IP block/unblock (pfSense, Palo Alto, AWS WAF, etc.) | High |
| **PagerDuty** | On-call escalation for CRITICAL incidents | Medium |
| **JIRA / Linear** | Auto-create tickets for incidents | Medium |
| **VirusTotal / Shodan** | Deeper IP/domain threat intel | Medium |
| **TheHive / MISP** | Open-source case management / threat sharing | Low |
| **Webhook** | Generic outbound to any system | High (easy to add) |

### Adapter Structure in Your Project

```python
# integrations/base_integration.py
class BaseIntegration:
    def __init__(self, config: dict): ...
    def execute(self, action: str, params: dict, context: dict) -> dict:
        # Returns: { "success": bool, "output": any, "error": str|None }
        raise NotImplementedError
    def test_connection(self) -> bool: ...
```

```python
# integrations/slack_adapter.py
class SlackIntegration(BaseIntegration):
    def execute(self, action, params, context):
        if action == "notify_slack":
            # POST to webhook_url with formatted block kit payload
            ...
```

```python
# integrations/integration_registry.py
INTEGRATION_REGISTRY = {
    "slack":      SlackIntegration(config["slack"]),
    "email":      EmailIntegration(config["email"]),
    "firewall":   FirewallIntegration(config["firewall"]),
}
```

Config loaded from env vars or a `integration_config` DB table (same pattern as `detection_config`).

---

## 7. RISK + ORDERING

### Most Risky Areas — Touch Last or Never

| Area | Risk | Why |
|---|---|---|
| `backend_detection_engine.py` | **CRITICAL** | Core business logic, heavy test coverage, synchronous ingest contract — any change here breaks the detection transaction and all detection tests |
| `backend_ingest_engine.py` | **CRITICAL** | Central ingest routing — event_type routing map change breaks all sources |
| `backend_correlation_engine.py` | **HIGH** | Correlation logic is tested but fragile — relies on precise alert state |
| DB transaction flow in `ingest_routes.py` | **HIGH** | conn/cur passed through the entire pipeline — inserting async in wrong place breaks atomicity |
| `core/db.py` connection management | **MEDIUM** | Shared connection pattern — a new async thread needs its own connection, not the shared one |

### Safe to Modify Early

- `core/ip_helpers.py` — only change is *when* `execute_response_action()` is called, not what it does
- `schema.sql` — adding columns and new tables is always safe; never drop or rename
- `routes/` — adding new route files is zero-risk
- `helpers/enrichment_helpers.py` — extend, don't change existing functions

### Ordering Rules

1. **Never touch detection/correlation internals** until Phase 1–3 are stable and tested
2. **Phase 1 must be complete** before any playbook work (Phases 2+) — async queue is the foundation
3. **Phase 3 integrations must be behind feature flags or env-var toggles** so real actions can be disabled in test
4. **Each phase must have full pytest coverage** before starting the next — use the same mock pattern already in `conftest.py`
5. **Schema changes** always use `ALTER TABLE` (additive) — never `DROP` or `RENAME` a column that existing code reads

---

## 8. OPTIONAL IMPROVEMENTS

### Architectural Suggestions (Non-Breaking)

**Move flat engine files into the `engines/` package**
- `backend_detection_engine.py` → `engines/detection_engine.py`
- `backend_correlation_engine.py` → `engines/correlation_engine.py`
- `backend_ingest_engine.py` → `engines/ingest_engine.py`
- Keep function signatures identical — only change imports in `ingest_routes.py` and tests
- Improves discoverability and makes `engines/` the canonical home for all engine logic
- **Do this as a standalone refactor PR, not bundled with any feature work**

**Replace in-process queue with Redis + RQ (long-term)**
- `queue.Queue` works for single-process but won't survive a server restart or multi-process deployment
- Redis + RQ (or Celery) gives persistence, worker monitoring, retries, and visibility
- Not needed until you're running playbooks in production — add in Phase 5+

**Playbook dry-run mode**
- Add `dry_run=True` flag to `execute_playbook()` — logs what would happen without executing
- Invaluable for testing new playbooks before enabling them in production

**Detection rule → playbook link**
- Add optional `playbook_id` column to `detection_config` table
- When a rule fires and has a linked playbook, auto-trigger it — tighter coupling between rule tuning and response

**Integration config UI**
- Extend the existing admin detection rule config UI pattern to integration config
- Analysts can toggle Slack notifications on/off without a deploy
- Same DB-backed config pattern already proven with `detection_config`

### Long-Term Scalability Notes
- The synchronous ingest pipeline will become a bottleneck under high load — consider separating ingest from detection into separate processes eventually (message queue between them)
- `steps_log JSONB` on `playbook_executions` is fine for low volume but index on `playbook_id` + `started_at` early
- Consider partitioning `events` and `alerts` tables by month once volumes grow — add `created_at` partition key
- All integration API keys must be in env vars, never in the DB or committed config

---

## 9. SAFE IMPLEMENTATION ORDER

Follow this checklist in exact order. Do not proceed to a step until all verification items for the previous step pass.

---

### Step 1 — Schema Migrations (Phase 1, no code changes)
- Run `ALTER TABLE response_actions_log` to add idempotency/retry columns
- Create `incidents` and `incident_alerts` tables
- **Verify:** `schema.sql` applies cleanly on a fresh DB; all existing tests pass unchanged

### Step 2 — Async Queue Scaffold (Phase 1)
- Implement `core/async_queue.py` with enqueue/worker — worker starts but executes nothing yet (no actions wired)
- Add `GET /health/worker` endpoint
- Add structured logging for enqueue and worker events
- **Verify:** All existing pytest suites pass. Worker starts. `/health/worker` responds. No changes to detection/correlation/ingest behavior.

### Step 3 — Decouple `execute_response_action` (Phase 1 — highest-risk step)
- Move `execute_response_action()` call from inside ingest transaction to after `conn.commit()` in `ingest_routes.py`
- Wire the worker to call `execute_response_action()` for dequeued items
- **Verify — must all pass:**
  - `pytest tests/test_failed_login_detection.py`
  - `pytest tests/test_password_spraying_detection.py`
  - `pytest tests/test_correlated_activity.py`
  - `pytest tests/test_targeted_correlation.py`
  - `pytest tests/test_ingest_api_contracts.py`
  - `pytest tests/test_alert_mutation_api_contracts.py`
  - Confirm `response_actions_log` rows are still being created
  - Confirm alert rows are committed and visible before response executes

### Step 4 — Incident Routes (Phase 1)
- Implement incidents read/write logic and `routes/incident_routes.py`
- Auto-create incidents on HIGH/CRITICAL alerts using the join table
- **Verify:** New incident routes respond correctly. All existing tests still pass. No regressions.

### Step 5 — Playbook Schema + Engine Scaffold (Phase 2)
- Create `playbook_definitions` and `playbook_executions` tables
- Implement `engines/playbook_engine.py` with trigger matching only — no step execution yet
- **Verify:** Trigger matching unit tests pass. No existing tests affected.

### Step 6 — Playbook Step Execution (Phase 2)
- Implement step executor with step states, idempotency keys, per-step retry
- Implement crash-recovery path (`resume_from_step`)
- Wire trigger matching → async queue → step executor
- **Verify:** Playbook integration tests pass. Simulate worker crash mid-playbook and confirm resume skips completed steps. Full existing test suite passes.

### Step 7 — Integration Adapters in Simulation Mode (Phase 3)
- Implement `integrations/` package with all adapters running under `INTEGRATION_MODE=simulation`
- Implement circuit breaker + timeout per adapter
- Wire playbook steps to integration registry
- **Verify:** All adapters callable from playbook steps. All return simulated success. No network calls made. Full test suite passes.

### Step 8 — Real Execution Mode (Phase 3, requires staging environment)
- Set `INTEGRATION_MODE=real` in staging
- Test each adapter individually with real credentials (Slack webhook, SMTP)
- Enable firewall adapter only after confirming idempotency and circuit breaker behavior
- **Verify:** Real Slack message sent. Real email received. No duplicate actions on retry. Circuit breaker opens after simulated consecutive failures.

### Step 9 — Approvals + Case Timeline (Phase 4)
- Implement `approval_requests` table and `require_approval` step type
- Implement case timeline endpoint on incident detail
- **Verify:** Playbook pauses on approval gate. Approval resumes; denial aborts. Timeline includes all event types in correct order.

### Step 10 — Hardening + Metrics (Phase 5)
- Implement dead letter queue, playbook metrics, and rate limiting
- Treat `playbook_schedules` as intentionally inert legacy schema unless a future approved scheduler spec reintroduces scheduled playbooks
- **Verify:** Dead letter queue receives exhausted-retry actions. Metrics endpoint returns accurate data. Rate limiter prevents notification floods.

---

**Run these six tests after every step. If any fail, revert before proceeding:**
- `pytest tests/test_failed_login_detection.py`
- `pytest tests/test_password_spraying_detection.py`
- `pytest tests/test_correlated_activity.py`
- `pytest tests/test_targeted_correlation.py`
- `pytest tests/test_ingest_api_contracts.py`
- `pytest tests/test_alert_mutation_api_contracts.py`

---

## Phase Summary

| Phase | Goal | Risk | Key Output |
|---|---|---|---|
| 1 | Async queue + incident management | Very Low | Non-blocking response, incident table |
| 2 | Playbook engine + execution | Low-Medium | Multi-step automated response |
| 3 | Real integrations | Medium | Slack, email, real firewall block |
| 4 | Approvals + case management | Low | Human-in-the-loop gates, case timeline |
| 5 | Hardening + metrics | Very Low | Production-grade reliability |
