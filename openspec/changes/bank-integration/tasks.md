# Bank Application to SIEM Integration Tasks

## Environment Configuration

- [ ] Define `SIEM_API_URL`
- [ ] Define `SIEM_INGEST_API_KEY`
- [ ] Ensure bank app uses the intended internal SIEM endpoint

---

## Helper Function

- [ ] Implement `send_siem_event(...)`
- [ ] Build structured JSON payload
- [ ] Add `Content-Type: application/json`
- [ ] Add `X-API-Key` header when configured
- [ ] Send request with `requests.post(...)`

---

## Route Integration

- [ ] Send event on login success
- [ ] Send event on login failure
- [ ] Send event on account lock
- [ ] Send event on deposit
- [ ] Send event on withdraw
- [ ] Send event on registration

---

## Error Handling

- [ ] Catch request exceptions
- [ ] Log SIEM send failures
- [ ] Ensure bank app route continues even if SIEM call fails

---

## Validation

- [ ] Verify payload contains:
  - event_type
  - severity
  - source_ip
  - message
  - app_name
  - environment

- [ ] Verify API key header is sent correctly

---

## Testing

- [ ] Trigger login failure and confirm SIEM receives event
- [ ] Trigger account lock and confirm SIEM receives event
- [ ] Trigger deposit/withdraw and confirm SIEM receives event
- [ ] Verify bank app still functions if SIEM is unavailable
- [ ] Verify SIEM logs and dashboard reflect received events# Bank Application to SIEM Integration Tasks

## Environment Configuration

- [ ] Define `SIEM_API_URL`
- [ ] Define `SIEM_INGEST_API_KEY`
- [ ] Ensure bank app uses the intended internal SIEM endpoint

---

## Helper Function

- [ ] Implement `send_siem_event(...)`
- [ ] Build structured JSON payload
- [ ] Add `Content-Type: application/json`
- [ ] Add `X-API-Key` header when configured
- [ ] Send request with `requests.post(...)`

---

## Route Integration

- [ ] Send event on login success
- [ ] Send event on login failure
- [ ] Send event on account lock
- [ ] Send event on deposit
- [ ] Send event on withdraw
- [ ] Send event on registration

---

## Error Handling

- [ ] Catch request exceptions
- [ ] Log SIEM send failures
- [ ] Ensure bank app route continues even if SIEM call fails

---

## Validation

- [ ] Verify payload contains:
  - event_type
  - severity
  - source_ip
  - message
  - app_name
  - environment

- [ ] Verify API key header is sent correctly

---

## Testing

- [ ] Trigger login failure and confirm SIEM receives event
- [ ] Trigger account lock and confirm SIEM receives event
- [ ] Trigger deposit/withdraw and confirm SIEM receives event
- [ ] Verify bank app still functions if SIEM is unavailable
- [ ] Verify SIEM logs and dashboard reflect received events
