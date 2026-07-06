# SIEM/SOAR CODEBASE MAP
Generated: 2026-05-18

---

## 1. EVENT INGESTION

### Flask Route Handlers — `routes/ingest_routes.py`
| Route | Function | Line |
|---|---|---|
| `POST /ingest` | `add_event()` | 81 |
| `POST /ingest/web-log` | `add_web_log_event()` | 190 |
| `POST /ingest/azure` | `add_azure_event()` | 301 |
| `POST /ingest/otlp` | `add_otel_event()` | 409 |

Raw payload received at line 91: `data = request.get_json()`
Required fields validated: `event_type`, `severity`, `source_ip`, `message`, `app_name`, `environment`

### Normalization / Adapters
| File | Function | Line |
|---|---|---|
| `adapters/nginx_adapter.py` | `parse_nginx_access_log_line()` | 21 |
| `adapters/azure_insights_adapter.py` | `normalize_azure_identity_telemetry()` | 182 |
| `adapters/azure_insights_adapter.py` | `normalize_azure_insights_telemetry()` | 218 |
| `adapters/otel_adapter.py` | `normalize_otel_telemetry()` | 163 |

### Event Write to DB
- File: `engines/ingest_engine.py`
- Function: `ingest_normalized_event()` — line 15
- SQL INSERT into `events` table at lines 31–59

### `events` Table Schema
```sql
CREATE TABLE events (
    id               SERIAL PRIMARY KEY,
    event_type       TEXT NOT NULL,
    severity         TEXT NOT NULL,
    source_ip        INET NOT NULL,
    source           TEXT NOT NULL DEFAULT 'bank_app',
    source_type      TEXT NOT NULL DEFAULT 'custom',
    event_timestamp  TIMESTAMPTZ,
    message          TEXT NOT NULL,
    app_name         TEXT NOT NULL DEFAULT 'unknown_app',
    environment      TEXT NOT NULL DEFAULT 'dev',
    raw_payload      JSONB NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```
Source: `schema.sql` lines 3–16

---

## 2. DETECTION ENGINE

**File:** `engines/detection_engine.py`

### All Detection Rules
| Rule Name | Function | Line |
|---|---|---|
| Failed Login Threshold | `_generate_failed_login_alerts_core()` | 16 |
| HTTP Error Threshold | `_generate_http_error_alerts_core()` | 153 |
| Port Scan Threshold | `_generate_port_scan_alerts_core()` | 280 |
| Password Spraying | `_generate_password_spraying_alerts_core()` | 417 |
| Successful Login After Spray | `_generate_successful_login_after_spray_alerts_core()` | 565 |
| Application Exception | `_generate_application_exception_alerts_core()` | 729 |
| High Request Rate | `_generate_high_request_rate_alerts_core()` | 856 |

### Detection Config/Thresholds
- File: `engines/detection_config.py`
- Table: `detection_config` (stores per-rule overrides)
- `get_effective_detection_rule()` — line 141 (merges defaults + DB overrides)
- `get_all_effective_detection_rules()` — line 226

### Duplicate Alert Suppression
- File: `engines/detection_engine.py`
- Location: Inside each `_generate_*_core()` function (example: lines 81–92 of failed login rule)
- Query pattern:
```sql
SELECT 1 FROM alerts
WHERE source_ip = %s
  AND alert_type = %s
  AND status = 'open'
```
If a row is found, no new alert is inserted.

---

## 3. ALERT CREATION

### Insert Location
- File: `engines/detection_engine.py`
- Each `_generate_*_core()` function runs its own `cursor.execute()` INSERT
- Example insert columns (failed login rule, lines 93–135):
```sql
INSERT INTO alerts (
    source_ip, alert_type, severity, source, source_type, message,
    status, response_action, response_status,
    country, city, latitude, longitude,
    reputation_score, reputation_label, reputation_source, reputation_summary
) VALUES (...)
```

### `alerts` Table Schema
```sql
CREATE TABLE alerts (
    id               SERIAL PRIMARY KEY,
    alert_type       TEXT NOT NULL,
    severity         TEXT NOT NULL,
    source_ip        INET NOT NULL,
    source           TEXT,
    source_type      TEXT,
    message          TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'open',
    country          TEXT,
    city             TEXT,
    latitude         DOUBLE PRECISION,
    longitude        DOUBLE PRECISION,
    reputation_score INTEGER,
    reputation_label TEXT,
    reputation_source TEXT,
    reputation_summary TEXT,
    response_action  TEXT,
    response_status  TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```
Source: `schema.sql` lines 18–38

### SIEM → SOAR Handoff Point
- File: `routes/ingest_routes.py`
- Function: `add_event()` — line 81
- Line 151–152: After `conn.commit()`, calls `enqueue_committed_alerts(alerts_created, conn)`
- **SOAR begins at:** `engines/soar_enqueue_orchestrator.py::enqueue_committed_alerts()` — line 9

---

## 4. SOAR PIPELINE

### Stage 1 — Enqueue Orchestrator
- **File:** `engines/soar_enqueue_orchestrator.py`
- **Function:** `enqueue_committed_alerts()` — line 9
- **Triggered by:** `ingest_routes.py` line 151, after `conn.commit()`
- **Decision:** Validates `alert_id`, `source_ip`, `response_action`; deduplicates — returns `queue_id=None` if already enqueued for same alert+IP combination
- **Output:** Inserts row into `response_actions_queue`

### Stage 2 — Playbook Orchestrator
- **File:** `engines/soar_playbook_orchestrator.py`
- **Function:** `create_pending_executions_for_committed_alerts()` — line 19
- **Triggered by:** `ingest_routes.py` line 69, after alert commitment
- **Decision:** Calls `match_playbooks()` on each alert; matches on `alert_type` + `trigger_config`
- **Output:** Creates rows in `playbook_executions` with `status='pending'`

### Stage 3 — Action Worker
- **File:** `engines/soar_action_worker.py`
- **Functions:**

| Function | Line | Purpose |
|---|---|---|
| `process_next_action()` | 27 | Claims and processes one queued action |
| `process_batch()` | 151 | Processes up to N actions in sequence |
| `action_requires_approval()` | 161 | Checks if action needs approval gate |
| `_handle_approval_gate()` | 165 | Creates `approval_request` if required |

- **Approval gate:** `APPROVAL_REQUIRED_ACTIONS = frozenset({"block_ip"})` — line 24
- **Decision path:** Is action in `APPROVAL_REQUIRED_ACTIONS`? → Check if approval exists and is approved → If pending, mark action `awaiting_approval`
- **Triggered by:** `POST /admin/soar/worker/run-once` or background worker process

### Stage 4 — Executor
- **File:** `engines/soar_executor.py`
- **Classes:**
  - `SimulationExecutor` — line 23 (default; all execution is simulated)
  - `AdapterBackedExecutor` — line 12 (routes through integration adapters)
- **Triggered by:** `soar_action_worker.py::process_next_action()` — line 63

### Stage 5 — Playbook Step Executor
- **File:** `engines/playbook_step_executor.py`
- **Functions:**

| Function | Line | Purpose |
|---|---|---|
| `process_next_pending_playbook_execution()` | 197 | Claims lease; processes one execution |
| `process_playbook_execution()` | 224 | Main execution orchestrator |
| `process_playbook_execution_batch()` | 353 | Batch processor |
| `_process_running_execution()` | 404 | Handles already-running state |
| `_process_awaiting_approval_execution()` | 492 | Handles approval gate state |
| `_process_steps()` | 674 | Main step loop |

- **Decision points:** Lease validation; step status (pending/success/failed/awaiting_approval); approval gate outcome; retry logic

### Stage 6 — Log Writer
- **File:** `engines/soar_log_writer.py`
- **Function:** `log_response_action()` — line 4
- **Writes to:** `response_actions_log`
- **Triggered by:** `soar_action_worker.py` after each action execution

### Stage 7 — Playbook Worker Daemon
- **File:** `engines/soar_playbook_worker.py`
- **Function:** `run_playbook_worker()` — line 79
- **Entry point script:** `scripts/soar_playbook_worker_daemon.py`
- **Behavior:** Continuous polling loop; calls `process_playbook_execution_batch()`; handles graceful SIGINT/SIGTERM; implements stale execution recovery
- **Status:** Implemented; NOT deployed as systemd service

---

## 5. SOAR UI TABS

### SOAR Queue
- **Frontend:** `frontend/src/components/SoarQueuePanel.js`
- **Backend routes** (all in `routes/admin_routes.py`):

| Endpoint | Line | Purpose |
|---|---|---|
| `GET /admin/soar/queue/status` | 572 | Count by status |
| `GET /admin/soar/queue/recent` | 601 | Recent items |
| `GET /admin/soar/queue/<queue_id>` | 645 | Single item detail |
| `POST /admin/soar/worker/run-once` | 676 | Run batch (max 25) |

- **Displays:** Queue counts by status; recent items (alert_id, source_ip, action, status, timestamps); linked approval if exists
- **User actions:** Refresh; run batch; view item detail; filter by status; adjust limit (10/25/50/100)
- **Role gate:** `super_admin` only

---

### SOAR Incidents
- **Frontend:** `frontend/src/components/IncidentsPanel.js`
- **Backend routes** (all in `routes/incident_routes.py`):

| Endpoint | Line | Purpose |
|---|---|---|
| `GET /incidents` | 634 | List with filters |
| `GET /incidents/<id>` | 685 | Single incident detail |
| `GET /incidents/<id>/timeline` | 704 | Chronological activity timeline |
| `POST /incidents/<id>/status` | 723 | Update lifecycle status |

- **Displays:** Incident list (severity, status, priority, created_at); detail (description, source_ip, assigned_to, related alerts); timeline joining 6 event sources; associated notification deliveries
- **User actions:** Filter by status/severity; update status; view timeline; view delivery attempts
- **Role gate:** `analyst` or `super_admin`

---

### SOAR Approvals
- **Frontend:** `frontend/src/components/ApprovalsPanel.js`
- **Backend routes:**

| Endpoint | File | Line | Purpose |
|---|---|---|---|
| `GET /approvals` | `approval_routes.py` | 40 | List approval requests |
| `GET /approvals/<id>` | `approval_routes.py` | 95 | Single approval detail |
| `POST /approvals/<id>/decision` | `approval_routes.py` | 114 | Submit approve/deny |
| `POST /admin/soar/approvals/expire-pending` | `admin_routes.py` | 738 | Expire overdue approvals |

- **Displays:** Request list (status, action, risk_level, requested_by, expires_at); linked resource context; decision history; delivery attempts
- **User actions:** Filter by status/risk level; approve/deny with comment; expire overdue; view delivery history
- **Role gate:** `analyst` or `super_admin` (mutations: `super_admin` only)

---

### SOAR Playbooks
- **Frontend:** `frontend/src/components/PlaybooksPanel.js`
- **Backend routes** (all in `routes/playbook_routes.py`):

| Endpoint | Line | Purpose |
|---|---|---|
| `GET /playbooks` | 368 | List definitions |
| `POST /playbooks` | 408 | Create new playbook |
| `GET /playbooks/<id>` | 471 | Definition detail |
| `PUT /playbooks/<id>` | 490 | Update definition |
| `PATCH /playbooks/<id>/enabled` | 550 | Toggle enabled flag |
| `GET /playbook-executions` | 581 | List execution instances |
| `GET /playbook-executions/<id>` | 635 | Single execution detail |
| `POST /playbook-executions/<id>/retry` | 654 | Retry failed execution |

- **Displays:** Definitions (name, description, enabled, trigger_config, steps); executions (status, timestamps, last_completed_step); step log (step_index, status, adapter result, approval outcome)
- **User actions:** Create/edit/disable playbooks; view/retry executions; view step logs and delivery attempts
- **Role gate:** `analyst` or `super_admin`

---

### SOAR Metrics
- **Frontend:** `frontend/src/components/SoarMetricsDashboard.js`
- **Backend routes:**

| Endpoint | File | Purpose |
|---|---|---|
| `GET /metrics/playbooks` | `metrics_routes.py:230` | Execution counts/rates/durations |
| `GET /metrics/playbook-worker` | `metrics_routes.py:351` | Worker heartbeat/recovery |
| `GET /metrics/notifications` | `metrics_routes.py:370` | Delivery success rates by adapter |
| `GET /metrics/approvals` | `metrics_routes.py:566` | Pending count, avg decision time |
| `GET /metrics/dead-letters` | `dead_letter_routes.py:214` | Dead letter counts |

- **Displays:** 7 sections — Playbook Execution Health, Dead Letter Health, Notification Delivery, Incident Metrics, Approval Metrics, Worker Operations, SOAR Queue Health
- **Auto-refresh:** every 60 seconds
- **Role gate:** `analyst`+; Queue Health section is `super_admin` only

---

### SOAR Integrations
- **Frontend:** `frontend/src/components/IntegrationStatusPanel.js`
- **Backend routes** (all in `routes/integration_routes.py`):

| Endpoint | Line | Purpose |
|---|---|---|
| `GET /integrations/status` | 87 | All adapter statuses |
| `POST /integrations/<adapter>/circuit-breaker/reset` | 98 | Reset circuit breaker |
| `POST /integrations/<adapter>/circuit-breaker/force-open` | 127 | Manually open circuit |

- **Displays:** Adapter list (slack, teams, email, webhook, firewall); circuit breaker state (closed/open/half_open); consecutive failures; rate limit status; email/webhook readiness fields
- **User actions:** View status (analyst); reset/force-open circuit breaker (super_admin only, requires reason field)
- **Role gate:** `analyst` read-only; mutations `super_admin` only (audit-logged)

---

### SOAR Operations (Dead Letters)
- **Frontend:** `frontend/src/components/DeadLettersPanel.js`
- **Backend routes** (all in `routes/dead_letter_routes.py`):

| Endpoint | Line | Purpose |
|---|---|---|
| `GET /dead-letters` | 143 | List failed executions |
| `GET /dead-letters/<id>` | 195 | Single dead letter detail |
| `POST /dead-letters/<id>/dismiss` | 230 | Dismiss |
| `POST /dead-letters/<id>/retry-request` | 291 | Retry via request |
| `POST /dead-letters/<id>/retry-execute` | 345 | Retry execution |
| `GET /metrics/dead-letters` | 214 | Dead letter metrics |

- **Displays:** Failed playbook executions; failure reason; failure_classification; retryable flag; step that failed; timestamp
- **User actions:** View detail; dismiss; retry-execute (creates new `pending` playbook_execution row — does NOT invoke executor directly)
- **Role gate:** `analyst` or `super_admin` (read); mutations `super_admin` only

---

### Tab Wiring in `frontend/src/App.js`
| Tab | Condition | Approx. Line |
|---|---|---|
| Dashboard | All authenticated | 610 |
| SOC Command Center | `canTakeAlertActions` | 675 |
| Blocklist | `canTakeAlertActions` | 684 |
| Threat Hunt | `canTakeAlertActions` | 663 |
| Administration | `isSuperAdmin` | 695 |
| SOAR Queue | `isSuperAdmin` | 720 |
| SOAR Incidents | `canTakeAlertActions` | 731 |
| SOAR Approvals | `canTakeAlertActions` | 743 |
| SOAR Playbooks | `canTakeAlertActions` | 755 |
| SOAR Integrations | `canTakeAlertActions` | 768 |
| SOAR Metrics | `canTakeAlertActions` | 777 |
| SOAR Operations | `canTakeAlertActions` | 787 |

`canTakeAlertActions = isSuperAdmin || isAnalyst`

---

## 6. RBAC & AUDIT

### Role Enforcement — `core/auth.py`
| Decorator | Line | Grants Access To |
|---|---|---|
| `@super_admin_required` | 98 | `super_admin` only |
| `@analyst_or_super_admin_required` | 113 | `analyst` or `super_admin` |
| `@admin_required` | 83 | `admin` or `super_admin` (legacy) |

### Roles
| Role | Access Level |
|---|---|
| `super_admin` | Full access; user management; circuit breaker mutations; worker run; detection rule edits |
| `analyst` | SOAR tabs (read + decisions); alert actions; approvals |
| `viewer` | Read-only; alerts only; displayed as "Auditor" in UI |

### Audit Logging
- File: `core/audit_helpers.py`
- Function: `log_audit_event()` — line 7

### `audit_log` Table Schema
```sql
CREATE TABLE audit_log (
    id              SERIAL PRIMARY KEY,
    event_type      TEXT NOT NULL,
    actor_username  TEXT,
    actor_role      TEXT,
    target_username TEXT,
    target_alert_id INTEGER,
    http_method     TEXT,
    request_path    TEXT,
    source_ip       INET,
    details         JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```
Source: `schema.sql` lines 96–108

---

## 7. FRONTEND → BACKEND CONNECTION

### All Service Files in `frontend/src/services/`
| File | Endpoints Called |
|---|---|
| `alertsService.js` | `GET /alerts` |
| `alertStatusService.js` | `PATCH /alerts/<id>` |
| `alertResponseService.js` | `POST /response-actions` (deprecated) |
| `incidentService.js` | `GET /incidents`, `GET /incidents/<id>`, `GET /incidents/<id>/timeline`, `POST /incidents/<id>/status` |
| `approvalService.js` | `GET /approvals`, `GET /approvals/<id>`, `POST /approvals/<id>/decision`, `POST /admin/soar/approvals/expire-pending` |
| `playbookService.js` | `GET /playbooks`, `POST /playbooks`, `PUT /playbooks/<id>`, `PATCH /playbooks/<id>/enabled`, `GET /playbook-executions`, `GET /playbook-executions/<id>`, `POST /playbook-executions/<id>/retry` |
| `soarQueueService.js` | `GET /admin/soar/queue/status`, `GET /admin/soar/queue/recent`, `GET /admin/soar/queue/<id>`, `POST /admin/soar/worker/run-once` |
| `integrationService.js` | `GET /integrations/status`, `POST /integrations/<adapter>/circuit-breaker/reset`, `POST /integrations/<adapter>/circuit-breaker/force-open` |
| `deadLetterService.js` | `GET /dead-letters`, `GET /dead-letters/<id>`, `POST /dead-letters/<id>/dismiss`, `POST /dead-letters/<id>/retry-request`, `POST /dead-letters/<id>/retry-execute` |
| `notificationDeliveryService.js` | `GET /notification-deliveries`, `GET /notification-deliveries/<id>` |
| `metricsService.js` | `GET /metrics`, `/metrics/playbooks`, `/metrics/notifications`, `/metrics/approvals` |
| `detectionRulesService.js` | `GET /admin/detection-rules`, `PUT /admin/detection-rules/<rule_id>` |
| `blocklistService.js` | `GET /blocklist`, `POST /blocklist`, `DELETE /blocklist/<id>` |
| `threatHuntService.js` | Event search with filters |
| `auditLogService.js` | `GET /audit-log` |
| `adminUsersService.js` | `POST /admin/users`, `GET /admin/users` |
| `authService.js` | `POST /login`, `GET /current-session`, `POST /logout` |

### Main Dashboard Data Loading — `frontend/src/App.js`
- Function: `fetchAlerts()` — line 110
- Calls: `loadAlerts()` from `alertsService.js`
- Refresh interval: 5000ms (line 164–166)

### Alert Data Processing — `frontend/src/utils/alertDashboardData.js`
| Function | Purpose |
|---|---|
| `filterAlerts()` | Search term, severity, status, source filters |
| `sortAlerts()` | Sort by newest/oldest/severity |
| `buildAlertMetrics()` | Summary statistics |
| `buildTopIPChartData()` | IP distribution chart |
| `buildAlertTimelineData()` | Alert creation timeline |

### Role-Based Display
- `userRole` prop drives `isSuperAdmin` and `isAnalyst` booleans
- Conditional rendering gates each tab section in `App.js`

---

## 8. HISTORICAL DATA & INVESTIGATION

### Storage
- Table: `alerts` (full schema in Section 3)

### Investigation UI Components
- `AlertDetailsPanel.js`
- `AlertSidePanel.js`
- `AlertsTable.js`
- Features: search by source IP, alert type, severity; filter by status/source; sort by date or severity

### Available Filter/Pivot Fields
- `source_ip`
- `alert_type`
- `severity` (low / medium / high / critical)
- `status` (open / closed / resolved / pending)
- `created_at` (timestamp range)
- `country`, `city`
- `reputation_score`, `reputation_label`

### Correlation Data Preservation
- File: `engines/correlation_engine.py`
- Functions: `generate_correlated_activity_alerts()`, `generate_targeted_correlation_alerts()`
- Correlation context preserved in `raw_payload JSONB` column on the alert row
- `helpers/enrichment_helpers.py::enrich_alert_with_correlation_context()` appends correlation signals to alert response

---

## 9. UNEXPECTED / INCOMPLETE / STUBS

### No TODO/STUB markers found
- grep returned 0 matches across the codebase

### Legacy Code Still Present
- `core/ip_helpers.py` still contains `execute_response_action()` — original synchronous response path
- Handoff doc flags: confirm it is not invoked before any real blocking path is introduced

### Backend Features With No Corresponding Frontend (Deferred)
- `notification_delivery` retry-execute — permanently deferred
- `response_action` and `approval` dead-letter retry-execute — permanently deferred
- `playbook_schedules` table — intentionally inert legacy schema; no scheduler, route, store helper, or management UI remains
- CI migration validation (blank DB apply + prohibited keyword grep) — defined in OpenSpec tasks but not yet implemented

### Implemented But Not Deployed
- `engines/soar_playbook_worker.py` + `scripts/soar_playbook_worker_daemon.py` — fully implemented; no systemd service installed on VM; no daemon running

### Replaced But Preserved
- `frontend/src/components/PlaybookMetricsPanel.js` — still in codebase; no longer imported in `App.js` (replaced by `SoarMetricsDashboard.js`)

### State That Resets On Restart (In-Process Only)
- Circuit breaker state (`integrations/circuit_breaker.py`) — in-memory; resets on process restart
- Rate limiter counters (`integrations/adapter_rate_limiter.py`) — in-process; resets on restart
- Notification dedup cache — in-process; resets on restart

### Correlation Gap
- Correlation-generated alerts are SOAR-invisible: not enqueued into `response_actions_queue` and not incident-linked

---

## INTEGRATIONS PACKAGE

| File | Class | Line | Notes |
|---|---|---|---|
| `integrations/slack_adapter.py` | `SlackSimulationAdapter` | 132 | Four-guard real-mode path; smoke test completed 2026-05-15 |
| `integrations/teams_adapter.py` | `TeamsSimulationAdapter` | 146 | Four-guard real-mode path; smoke test env-blocked |
| `integrations/email_adapter.py` | `EmailSimulationAdapter` | 180 | Four-guard real-mode path; smoke test not yet executed |
| `integrations/webhook_adapter.py` | `WebhookSimulationAdapter` | 301 | Four-guard real-mode path; lower priority |
| `integrations/firewall_adapter.py` | `FirewallSimulationAdapter` | 9 | Permanently simulation-only; SPEC-INTEG-005 boundary |
| `integrations/base_integration.py` | `BaseIntegration` | 525 | `_validate_real_mode_guards()` canonical helper |
| `integrations/base_integration.py` | `IntegrationResult` | 50 | |
| `integrations/integration_registry.py` | `IntegrationRegistry` | 11 | Startup circuit breaker reset events |
| `integrations/adapter_rate_limiter.py` | — | — | Per-adapter sliding-window rate limiter |
| `integrations/soar_adapters/base.py` | `BaseSoarActionAdapter` | 25 | |
| `integrations/soar_adapters/base.py` | `AdapterExecutionResult` | 9 | |
| `integrations/soar_adapters/linux_firewall.py` | `LinuxFirewallDryRunAdapter` | 21 | Dry-run only; no subprocess |
| `integrations/soar_adapters/registry.py` | `SoarAdapterRegistry` | 8 | |
| `integrations/soar_adapters/config.py` | `SoarAdapterConfig` | 11 | |

---

## MIGRATIONS DIRECTORY

| File | Description |
|---|---|
| `0001_schema_migrations.sql` | Create `schema_migrations` tracking table |
| `0002_base_siem_core.sql` | Core SIEM tables: `events`, `alerts`, `response_actions_log`, `response_actions_queue` |
| `0003_auth_rbac_and_metadata.sql` | `users`, `audit_log`, `alert_notes`, `detection_config`, `blocked_ips` |
| `0004_soar_incidents.sql` | `incidents`, `incident_alerts` |
| `0005_soar_approvals.sql` | `approval_requests`, `approval_request_events` |
| `0006_soar_playbooks.sql` | `playbook_definitions`, `playbook_executions`, `playbook_schedules` (inert legacy table) |
| `0007_soar_approval_playbook_wiring.sql` | Add `playbook_execution_id`, `playbook_step_index` to `approval_requests` |
| `0008_soar_notification_delivery.sql` | `notification_delivery_attempts` table |
| `0009_soar_execution_leases.sql` | Add `lease_owner`, `lease_acquired_at`, `lease_heartbeat_at`, `lease_expires_at`, `recovery_count` to `playbook_executions` |
| `0010_soar_dead_letters.sql` | `soar_dead_letters` table |

---

## SCRIPTS DIRECTORY

| File | Purpose |
|---|---|
| `scripts/deploy_backend_vm.sh` | Migration-aware VM backend deploy: dry-run → apply → restart service → health-check |
| `scripts/migrate.py` | Authoritative schema migration runner; `--dry-run`, `--target N`, checksum recording |
| `scripts/ingest_log_files.py` | Utility to ingest log files into SIEM |
| `scripts/soar_worker_run.py` | Manually run SOAR action worker once |
| `scripts/run_playbook_executor_once.py` | Manually run playbook step executor; `--recover-stale`, `--stale-limit`, `--dry-run-recovery` flags |
| `scripts/soar_playbook_worker_daemon.py` | Daemon wrapper entry point for playbook worker |
| `scripts/validate_schema_snapshot.py` | Validates live schema matches `schema.sql` snapshot |

---

## TESTS DIRECTORY (54 files)

### Detection
- `test_failed_login_detection.py`
- `test_port_scan_detection.py`
- `test_password_spraying_detection.py`
- `test_successful_login_after_spray_detection.py`
- `test_application_exception_detection.py`
- `test_high_request_rate_detection.py`
- `test_http_error_detection.py`

### SOAR Pipeline
- `test_soar_enqueue_orchestrator.py`
- `test_soar_playbook_orchestrator.py`
- `test_soar_action_worker.py`
- `test_soar_executor.py`
- `test_soar_log_writer.py`
- `test_soar_playbook_worker.py`
- `test_playbook_step_executor.py`
- `test_soar_worker_runner.py`
- `test_soar_worker_admin_run_control.py`

### Data Stores
- `test_incident_store.py`
- `test_approval_store.py`
- `test_response_action_queue.py`
- `test_dead_letter_store.py`
- `test_playbook_store.py`
- `test_notification_delivery_store.py`

### Routes
- `test_incident_routes.py`
- `test_approval_routes.py`
- `test_dead_letter_routes.py`
- `test_playbook_routes.py`
- `test_integration_routes.py`
- `test_notification_delivery_routes.py`

### API Contracts
- `test_alerts_api_contracts.py`
- `test_ingest_api_contracts.py`
- `test_admin_api_contracts.py`
- `test_blocklist_api_contracts.py`
- `test_reporting_api_contracts.py`
- `test_metrics_routes.py`
- `test_notification_delivery_metrics_routes.py`
- `test_playbook_metrics_routes.py`
- `test_alert_mutation_api_contracts.py`
- `test_backfill_reputation_api_contracts.py`
- `test_events_search_api_contracts.py`

### Correlation & Integrations
- `test_correlated_activity.py`
- `test_targeted_correlation.py`
- `test_integration_adapters.py`
- `test_soar_adapter_interface.py`

### Infrastructure
- `test_auth_rbac.py`
- `test_schema_migrations.py`
- `test_playbook_registry.py`
- `test_playbook_execution_leases.py`
- `test_soar_protected_targets.py`
- `test_wire_soar_enqueue_post_commit.py`
- `test_soar_queue_visibility_api.py`
- `test_run_playbook_executor_once.py`
- `test_deploy_backend_vm_script.py`

### Ingest
- `test_ingest_normalized_event.py`
