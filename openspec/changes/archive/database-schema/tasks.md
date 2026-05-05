# SIEM Database Schema Tasks

## events Table

- [ ] Create `events` table
- [ ] Add fields:
  - `id`
  - `event_type`
  - `severity`
  - `source_ip`
  - `message`
  - `app_name`
  - `environment`
  - `raw_payload`
  - `created_at`

- [ ] Set defaults for:
  - `app_name`
  - `environment`
  - `created_at`

- [ ] Mark required fields as `NOT NULL`

---

## alerts Table

- [ ] Create `alerts` table
- [ ] Add fields:
  - `id`
  - `alert_type`
  - `severity`
  - `source_ip`
  - `message`
  - `status`
  - `created_at`

- [ ] Set defaults for:
  - `status`
  - `created_at`

- [ ] Mark required fields as `NOT NULL`

---

## Indexes

- [ ] Add index on `events.source_ip`
- [ ] Add index on `events.created_at`
- [ ] Add index on `events.event_type`

- [ ] Add index on `alerts.source_ip`
- [ ] Add index on `alerts.created_at`
- [ ] Add index on `alerts.alert_type`
- [ ] Add index on `alerts.status`

---

## Constraints

- [ ] Ensure required fields use `NOT NULL`
- [ ] Ensure primary keys exist
- [ ] Optionally add CHECK constraints for:
  - alert status
  - severity
  - event_type

---

## Validation

- [ ] Confirm schema supports ingestion route
- [ ] Confirm schema supports failed login detection queries
- [ ] Confirm schema supports port scan detection queries
- [ ] Confirm schema supports dashboard retrieval and alert resolution

---

## Testing

- [ ] Insert sample event rows
- [ ] Insert sample alert rows
- [ ] Verify indexes exist
- [ ] Verify time-based event queries work correctly
- [ ] Verify alert retrieval and update operations work correctly