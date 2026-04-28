# Source-Aware Dashboard Polish Spec

## Feature Overview

This change adds source awareness to the SIEM dashboard so analysts can clearly see and filter events and alerts by data source.

The goal is to make the multi-source ingestion pipeline visible in the product by showing whether data came from `bank_app`, `nginx`, `azure_insights`, or `opentelemetry`, without changing detection behavior or redesigning the dashboard.

## Current State

- Events now include:
  - `source`
  - `source_type`
  - `event_timestamp`
- Supported sources currently include:
  - `bank_app`
  - `nginx`
  - `azure_insights`
  - `opentelemetry`
- The current UI does not clearly expose `source` / `source_type` context.
- Analysts can review alerts and threat-hunt events, but the ingestion origin is not obvious in the current display.

## Requirements

1. Backend
   - Ensure alert and event APIs return `source` and `source_type` where available.
   - Do not change schema.
   - Do not change detection logic.
   - Do not change ingestion behavior.

2. Dashboard UI
   - Add `source` / `source_type` display where practical, including:
     - alerts table
     - threat hunt results
     - event details or raw payload area if applicable

3. Filtering
   - Add a source filter dropdown with:
     - `All Sources`
     - `bank_app`
     - `nginx`
     - `azure_insights`
     - `opentelemetry`

4. Visual labels
   - Add compact source badges:
     - `bank_app` → `App / Bank`
     - `nginx` → `Web Log`
     - `azure_insights` → `Azure`
     - `opentelemetry` → `OTEL`
   - Keep the styling dark-theme consistent and compact.

5. Preserve existing filters and interactions
   - search
   - severity
   - status
   - sort
   - threat hunt filters

6. Do not:
   - add new ingestion sources
   - change detection rules
   - change RBAC
   - change schema
   - redesign the dashboard

## Non-Goals

- No new ingestion pipelines
- No schema migration
- No RBAC changes
- No detector changes
- No dashboard redesign
- No source-specific charts in this phase
- No alert correlation redesign
- No historical backfill for old missing source fields

## Acceptance Criteria

1. Alerts and events clearly show their source.
2. Analysts can filter dashboard data by source.
3. Existing filters still work.
4. `bank_app`, `nginx`, `azure_insights`, and `opentelemetry` data are visually distinguishable.
5. No ingestion or detection behavior changes.
6. Build succeeds.

## Risks and Mitigations

- Risk: `source` may be missing on older alerts
  - Mitigation: display a safe fallback such as `Unknown` or `Legacy` without breaking the table layout

- Risk: alerts may not currently store source directly
  - Mitigation: expose source from the best available backend relationship or extend only response serialization if the data is already derivable

- Risk: frontend filters could desync charts, table, and map
  - Mitigation: reuse existing shared filter state patterns rather than introducing isolated per-widget filtering

- Risk: source badges could add visual clutter
  - Mitigation: keep badges compact, text-first, and visually restrained within the existing dark theme
