# Alert System Tasks

## Database

- [ ] Define `alerts` table in schema
- [ ] Include fields:
  - id
  - alert_type
  - severity
  - message
  - source_ip
  - status
  - created_at

---

## Backend Logic

- [ ] Implement alert creation from detection rules
- [ ] Default new alerts to `open`
- [ ] Support status updates to `resolved`

---

## Duplicate Prevention

- [ ] Check for existing open alert before insert
- [ ] Skip insert if duplicate is found

---

## Validation

- [ ] Restrict status to `open` or `resolved`
- [ ] Ensure severity and alert_type are populated correctly

---

## Testing

- [ ] Verify alerts are created when detection triggers
- [ ] Verify duplicate open alerts are not created
- [ ] Verify resolving alert updates status only
- [ ] Verify resolved alerts remain queryable