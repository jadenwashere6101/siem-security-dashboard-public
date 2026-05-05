# Port Scan Detection Tasks

## Database

- [ ] Confirm `events` table stores:
  - `event_type`
  - `source_ip`
  - `created_at`

- [ ] Confirm `alerts` table supports:
  - `alert_type`
  - `severity`
  - `source_ip`
  - `message`
  - `status`

---

## Detection Logic

- [ ] Query events where `event_type = 'port_scan'`
- [ ] Group results by `source_ip`
- [ ] Count matching events per IP
- [ ] Trigger detection when count >= 2

---

## Alert Creation

- [ ] Create alert with:
  - `alert_type = port_scan_threshold`
  - `severity = medium`
  - `source_ip`
  - dynamic message
  - `status = open`

---

## Duplicate Prevention

- [ ] Check for existing open alert with same:
  - `source_ip`
  - `alert_type`

- [ ] Skip alert creation if duplicate exists

---

## Execution Integration

- [ ] Run detection in scheduled APScheduler job
- [ ] Run detection immediately after event ingestion

---

## Testing

- [ ] Insert or simulate 2 `port_scan` events from the same IP
- [ ] Verify a `medium` severity alert is created
- [ ] Verify duplicate open alerts are not created
- [ ] Verify alert appears in dashboard
- [ ] Verify detection works during both scheduled and immediate execution