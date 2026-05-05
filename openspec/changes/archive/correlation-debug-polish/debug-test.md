# Correlation Debug Test

## Goal

Verify that multi-source correlation creates a `correlated_activity` alert when the same fresh IP triggers qualifying alerts from both `bank_app` and `nginx`.

## Important Notes

- Use a **fresh IP address every run**
- Do not reuse an IP from a prior successful correlation test
- Duplicate suppression can prevent repeated `correlated_activity` creation on the same IP while an open correlation alert already exists

## Fresh Test IP

Choose a new public-format test IP for each run, for example:

- `203.0.113.41`
- `203.0.113.42`
- `203.0.113.43`

## Step 1: Trigger `bank_app` failed login threshold

Send enough failed-login style events through the existing bank app ingest path to trigger:

- `failed_login_threshold`

Minimum expectation:

- same `source_ip`
- enough failed login events within the detector window

## Step 2: Trigger `nginx` HTTP error threshold

Send enough nginx web-log events for the same fresh IP to trigger:

- `http_error_threshold`

Minimum expectation:

- same `source_ip` as Step 1
- enough `http_error` nginx events within the detector window

## Step 3: Watch backend logs

Look for correlation log lines with the `[CORRELATION]` prefix.

Expected sequence:

- evaluation start
- either a skip reason or success

Successful example pattern:

```text
[CORRELATION] Evaluating IP: 203.0.113.41
[CORRELATION] Success | IP: 203.0.113.41 | alerts=2 | types=failed_login_threshold, http_error_threshold | sources=bank_app, nginx
```

## Step 4: Verify in database

Check that a `correlated_activity` alert exists for the fresh IP:

```sql
SELECT
    id,
    alert_type,
    severity,
    source_ip,
    source,
    source_type,
    message,
    status,
    created_at
FROM alerts
WHERE source_ip = '203.0.113.41'
ORDER BY created_at DESC;
```

Expected result:

- one open `correlated_activity` alert
- message should mention the involved alert types

## Step 5: Verify no duplicate correlation alert is created

If you repeat the same test on the same IP without resolving the open correlation alert, duplicate suppression should prevent another `correlated_activity` alert from being created.

Expected log example:

```text
[CORRELATION] Skipped: duplicate open correlated_activity alert exists | IP: 203.0.113.41
```
