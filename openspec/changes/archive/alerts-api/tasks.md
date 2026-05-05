# Alerts API Tasks

## GET /alerts

- [ ] Create route for `GET /alerts`
- [ ] Query alerts table
- [ ] Order results by `created_at DESC`
- [ ] Return JSON response

---

## POST /alerts/<id>/status

- [ ] Create route for `POST /alerts/<id>/status`
- [ ] Parse request JSON
- [ ] Validate `status`
- [ ] Update matching alert record
- [ ] Return success response

---

## Validation

- [ ] Reject invalid status values
- [ ] Ensure route handles nonexistent IDs safely

---

## Frontend Integration

- [ ] Connect dashboard polling to `GET /alerts`
- [ ] Connect resolve button to `POST /alerts/<id>/status`

---

## Testing

- [ ] Verify alerts are returned in descending order
- [ ] Verify alert resolution updates status
- [ ] Verify invalid status returns error