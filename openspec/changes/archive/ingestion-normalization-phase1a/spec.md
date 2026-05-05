# Ingestion Normalization Phase 1a Spec

## Feature Overview

This change is a safe backend refactor that extracts the core event insert and detection-dispatch logic from `/ingest` into a reusable internal function such as:

`ingest_normalized_event(event_dict, conn, cur)`

The goal is to prepare the SIEM for future multi-source ingestion while preserving the exact current behavior of the existing `/ingest` API.

## Current State

- The `/ingest` route currently performs:
  - API key authentication
  - request JSON parsing
  - required field validation
  - `event_type`, `severity`, and `source_ip` validation
  - optional geo enrichment
  - database insert into `events`
  - alert detection dispatch based on `event_type`
  - response generation
- The insert and detection-dispatch logic is embedded directly inside `add_event()`.
- This works today, but it couples normalized event processing to the HTTP route.

## Requirements

1. Extract the shared event insert and detection-dispatch logic into a reusable internal backend function.
   - Example target shape:
     - `ingest_normalized_event(event_dict, conn, cur)`

2. The extracted function should handle only normalized event processing.
   - insert the event into `events`
   - run the same detection dispatch currently triggered by `event_type`
   - return the same alert creation result needed by `/ingest`

3. The existing `/ingest` route must continue to do all current request-facing work:
   - authenticate API key
   - parse JSON
   - validate required fields
   - validate `event_type`
   - validate `severity`
   - validate `source_ip`
   - perform geo enrichment as it currently does
   - build the same event payload/raw payload
   - call the extracted internal function
   - return the same response JSON and status code behavior

4. Preserve all current behavior exactly.
   - no schema changes
   - no frontend changes
   - no bank app changes
   - no API changes
   - no request shape changes
   - no response shape changes
   - no detection logic changes
   - no auth changes
   - no rate limit changes
   - no `VALID_EVENT_TYPES` changes
   - no severity validation changes

5. Keep current detection dispatch unchanged for:
   - `failed_login`
   - `port_scan`
   - `password_spraying_threshold`
   - `successful_login_after_spray`

6. No database migration is required.

## Non-Goals

- No new ingestion endpoints
- No schema redesign
- No bank app integration changes
- No normalization pipeline redesign
- No event model changes
- No detection rule refactor
- No runtime config changes
- No frontend work

## Acceptance Criteria

1. Bank app and other existing `/ingest` clients continue working unchanged.
2. Existing `failed_login`, `port_scan`, `password_spraying`, and `successful_login_after_spray` detections still work.
3. `/ingest` response JSON remains unchanged.
4. No database migration is required.
5. Syntax check passes.
6. Behavior is identical before and after the refactor.
7. Existing curl tests still pass:
   - missing API key returns `401`
   - valid `failed_login` event inserts successfully
   - fresh IP with threshold count triggers alert

## Risks and Mitigations

- Risk: refactor accidentally changes `/ingest` response behavior
  - Mitigation: keep response generation in `add_event()` and only extract normalized insert/dispatch work

- Risk: refactor changes detection trigger order or event flow
  - Mitigation: preserve the existing detection dispatch branches and call sequence exactly

- Risk: shared function starts taking over route-level validation/enrichment responsibilities
  - Mitigation: keep validation, auth, and enrichment in `/ingest`; only move normalized processing

- Risk: transaction handling changes subtly
  - Mitigation: keep the same `conn` / `cur` flow and commit/rollback behavior owned by the existing route

- Risk: future contributors assume this phase changes ingestion semantics
  - Mitigation: document clearly that this is Phase 1a refactor-only work with no functional changes
