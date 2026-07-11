# pfSense Runtime Ingest Filtering

## Phase 1 backend contract

The filterlog path is:

```text
UDP listener source/rate/size checks
-> IPv4 filterlog parse and normalization
-> authenticated POST /ingest/pfsense
-> normalized-event validation
-> per-request effective pfsense_ingest_config load
-> deterministic retention decision
-> geolocation (retained only)
-> ingest_normalized_event() (retained only)
-> existing detection, correlation, incident, queue, playbook, and SOAR flow
```

The standalone listener remains database-free. A filtered event returns HTTP 202 with a bounded category and reason. It does not reach geolocation, centralized ingest, a raw-event table, or downstream processing.

Safe defaults retain all supported blocks and inbound TCP/UDP allows to canonical sensitive ports. Routine allows, destination-port-53 traffic, and allowed ICMP are filtered unless their categories are enabled. The canonical default sensitive ports are `21, 22, 23, 25, 135, 445, 1433, 3306, 3389, 5432, 5900, 6379, 27017` and are also used by suspicious-allow detection.

The backend reads and validates configuration for every pfSense ingest request. Missing, unavailable, or invalid configuration activates the restrictive source-controlled defaults. It never activates retain-all behavior. Phase 2 will add super-admin mutation APIs, audit events for changes, and Administration UI; direct database edits are not an operational control.

Listener counters distinguish accepted transport, forwarded requests, filtered outcomes, ingested outcomes, rejected backend requests, parsing/edge rejections, and backend failures. Backend filter metrics are bounded process-local aggregates and reset when the backend process restarts; they do not store dropped payloads.
