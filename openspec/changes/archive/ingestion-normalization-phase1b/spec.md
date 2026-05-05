# Ingestion Normalization Phase 1b Spec

## Feature Overview

This change is an additive schema extension that adds source-tracking fields to the `events` table so the SIEM can support multiple future ingestion sources.

The goal is to prepare the data model for multi-source ingestion while keeping the current bank app `/ingest` pipeline unchanged.

## Current State

- The `events` table stores core event metadata and raw payload data.
- The current `/ingest` pipeline is built around the bank app and similar custom event senders.
- Source identity is currently implied by the existing event shape rather than stored explicitly in dedicated columns.
- `ingest_normalized_event()` currently inserts the normalized event fields used by the existing pipeline.

## Requirements

1. Add columns to the `events` table:
   - `source TEXT NOT NULL DEFAULT 'bank_app'`
   - `source_type TEXT NOT NULL DEFAULT 'custom'`
   - `event_timestamp TIMESTAMPTZ NULL`

2. Update `schema.sql` with the new columns.

3. Update live DB migration instructions separately after implementation.

4. Update insert logic inside `ingest_normalized_event()` to include:
   - `source = event_dict.get("source", "bank_app")`
   - `source_type = event_dict.get("source_type", "custom")`
   - `event_timestamp = event_dict.get("event_timestamp")`

5. Existing `/ingest` bank app flow must still work without sending these fields.

6. Do not change:
   - `/ingest` endpoint
   - request format
   - response format
   - API key auth
   - validation logic
   - detection logic
   - bank app integration
   - frontend

7. Add no new endpoints.

## Non-Goals

- No frontend changes
- No detection rule changes
- No new ingestion endpoints
- No bank app payload changes required in this phase
- No API contract change for existing senders
- No source-based routing logic yet
- No event replay or backfill logic
- No normalization redesign beyond the additive fields

## Acceptance Criteria

1. Existing bank app events still ingest successfully.
2. Existing events default to `source='bank_app'` and `source_type='custom'`.
3. New events inserted through `/ingest` store those default values when the fields are not provided.
4. `event_timestamp` can remain `NULL`.
5. Detection rules still trigger normally.
6. No frontend changes are required.

## Risks and Mitigations

- Risk: live DB must be migrated before deployment
  - Mitigation: provide separate migration instructions and do not assume `schema.sql` alone updates existing environments

- Risk: insert query drifts from schema definition
  - Mitigation: update `ingest_normalized_event()` insert columns and values in the same scoped change as the schema update

- Risk: defaults accidentally change existing bank app behavior
  - Mitigation: keep `source='bank_app'` and `source_type='custom'` as schema and backend defaults so current senders behave the same without payload changes

- Risk: future contributors assume `event_timestamp` replaces `created_at`
  - Mitigation: keep `event_timestamp` nullable and additive in this phase; `created_at` remains the database ingestion timestamp

- Risk: additive fields accidentally trigger validation or API behavior changes
  - Mitigation: do not change `/ingest` validation or request requirements in this phase
