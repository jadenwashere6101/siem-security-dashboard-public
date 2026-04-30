# Reporting / Export Extraction Plan

This document plans the first safe backend extraction for reporting/export code.

It is a planning document only. No functions should be moved until a later implementation phase.

## Scope

Target area:
- the `Reporting / Export Helpers` section in `siem_backend.py`

Goal:
- identify the smallest safe helper-only extraction
- avoid touching routes in the first move if possible
- keep rollback easy if the first extraction proves noisy

Intended first extraction target:
- `backend_reporting_helpers.py`

Phase 1 intent:
- this module should initially contain only pure formatting/narrative helpers
- `siem_backend.py` should import those helpers back from that module
- do not move routes, SQL helpers, or PDF-heavy helpers in phase 1

## 1. Exact Functions That Belong To Reporting / Export

Formatting helpers:
- `format_report_timestamp`
- `format_pdf_timestamp`
- `format_csv_timestamp`
- `format_display_value`

Alert/report enrichment and narrative helpers:
- `enrich_alert_with_mitre`
- `enrich_alert_with_correlation_context`
- `build_alert_summary`
- `build_severity_explanation`
- `build_confidence_level`
- `build_next_steps`
- `normalize_alert_report_data`
- `build_alert_report_sections`

Report/export query helpers:
- `fetch_alert_rows`
- `fetch_response_logs_by_alert_id`
- `fetch_alert_csv_rows`

PDF/report rendering helpers:
- `build_report_header`
- `get_pdf_severity_palette`
- `start_pdf_page`
- `ensure_pdf_space`
- `draw_pdf_wrapped_text`
- `draw_pdf_section_heading`
- `draw_pdf_key_value_rows`
- `draw_pdf_severity_badge`
- `draw_pdf_response_logs`
- `draw_pdf_mitre_section`
- `draw_pdf_next_steps`
- `draw_pdf_summary_grid`
- `draw_pdf_alert_card`
- `build_pdf_report_response`

Report/export routes:
- `export_alert_report`
- `export_alert_report_pdf`
- `export_multi_alert_report`
- `export_alerts_csv`
- `export_multi_alert_report_pdf`

## 2. Which Functions Are Safe To Extract First

Safest first extraction set:
- `format_report_timestamp`
- `format_pdf_timestamp`
- `format_csv_timestamp`
- `format_display_value`
- `build_alert_summary`
- `build_severity_explanation`
- `build_confidence_level`
- `build_next_steps`

Why these first:
- pure helper functions
- no DB access
- no Flask request/current-user coupling
- no route ownership
- easy to import back into `siem_backend.py`
- lowest rollback cost

Second-wave helper candidates, only after the first move is clean:
- `normalize_alert_report_data`
- `build_alert_report_sections`
- `build_report_header`
- `get_pdf_severity_palette`

## 3. Which Functions Should Stay For Now

Keep in `siem_backend.py` initially:

Query helpers:
- `fetch_alert_rows`
- `fetch_response_logs_by_alert_id`
- `fetch_alert_csv_rows`

Why:
- they are still coupled to SQL shape and report route behavior
- moving them early adds more surface area than necessary

PDF-heavy helpers:
- `start_pdf_page`
- `ensure_pdf_space`
- `draw_pdf_wrapped_text`
- `draw_pdf_section_heading`
- `draw_pdf_key_value_rows`
- `draw_pdf_severity_badge`
- `draw_pdf_response_logs`
- `draw_pdf_mitre_section`
- `draw_pdf_next_steps`
- `draw_pdf_summary_grid`
- `draw_pdf_alert_card`
- `build_pdf_report_response`

Why:
- these are still helper code, but they depend on the ReportLab stack and many internal helper calls
- safe later, but not the smallest first move

Routes:
- `export_alert_report`
- `export_alert_report_pdf`
- `export_multi_alert_report`
- `export_alerts_csv`
- `export_multi_alert_report_pdf`

Why:
- route movement is not needed for the first extraction
- keeping routes in place minimizes import churn and rollback complexity

## 4. Dependency Mapping

### Pure formatting/narrative helpers

Depend on:
- basic Python types/strings
- `datetime` / `timezone` for timestamp formatting

Do not depend on:
- DB cursor/connection
- Flask request context
- `current_user`
- route decorators

### `enrich_alert_with_mitre`

Depends on:
- `MITRE_ATTACK_MAPPINGS`

Risk note:
- if extracted later, the mapping either needs to stay imported from `siem_backend.py` or move to a shared constants/config module first

### `normalize_alert_report_data`

Depends on:
- `enrich_alert_with_mitre`
- `format_report_timestamp`
- `build_alert_summary`
- `build_severity_explanation`
- `build_confidence_level`
- `build_next_steps`
- the current `alert_row` tuple shape from SQL

Risk note:
- safe only if the tuple layout remains stable

### Query helpers

Depend on:
- live DB cursor
- current alert/event table shape
- exact SQL clauses and result ordering

### PDF helpers

Depend on:
- `reportlab` imports already in `siem_backend.py`
- `format_pdf_timestamp`
- `format_display_value`
- `simpleSplit`
- `HexColor`
- `colors`
- `letter`
- `canvas`
- cross-calls between PDF helper functions

### Report/export routes

Depend on:
- Flask request/response context
- `login_required`
- `analyst_or_super_admin_required`
- `get_db_connection`
- `current_user`
- `log_audit_event`
- all helper/query functions above

## 5. Risks Of Extraction

Low-risk extraction hazards:
- missed import for a helper function
- broken internal helper call after moving a small pure function

Medium-risk extraction hazards:
- moving `enrich_alert_with_mitre` too early without planning for `MITRE_ATTACK_MAPPINGS`
- moving `normalize_alert_report_data` before verifying tuple-shape assumptions

Higher-risk extraction hazards:
- moving query helpers too early
- moving PDF helpers as the first step
- moving routes in the same phase as helper extraction

## 6. Minimal Extraction Plan

Smallest safe move:

Phase 0: planning only
- define target module name and location
- define import direction back into `siem_backend.py`
- confirm verification and rollback steps before touching code

Phase 1: move only pure formatting/narrative helpers
- target module: `backend_reporting_helpers.py`
- `format_report_timestamp`
- `format_pdf_timestamp`
- `format_csv_timestamp`
- `format_display_value`
- `build_alert_summary`
- `build_severity_explanation`
- `build_confidence_level`
- `build_next_steps`

Phase 2: stop and verify
- do not move query helpers, PDF helpers, or routes in the same phase

If Phase 1 is clean:
- consider a later second phase for `normalize_alert_report_data` and `build_alert_report_sections`

## 7. Rollback Plan

If the first extraction causes import churn, build issues, or behavior uncertainty:

1. revert the moved helper imports and definitions immediately
2. restore the pure helper functions directly into `siem_backend.py`
3. re-run the verification checks below
4. stop and reduce scope instead of continuing to a bigger extraction

Rollback rule:
- if the first extraction touches routes, query helpers, or PDF helpers unexpectedly, revert and re-scope

## 8. Exact Verification Steps After Extraction

Run the baseline checks from `docs/verification-checklist.md`:

```bash
python3 -m py_compile siem_backend.py
cd frontend && npm run build
python3 -m py_compile siem-azure-function/function_app.py
curl -i http://127.0.0.1:5051/health
```

Run the reporting-specific behavior checks from `docs/behavior-checks.md`:

- report/export validation
- minimal DB verification queries if a report was generated from fresh events

Recommended focused checks after the first reporting-helper extraction:

```bash
curl -i http://127.0.0.1:5051/alerts/report
curl -i http://127.0.0.1:5051/alerts/report/pdf
curl -i http://127.0.0.1:5051/alerts/export/csv
```

Expected result:
- backend still compiles
- frontend still builds
- Azure Function file still compiles
- report/export endpoints still return valid responses in the normal authenticated environment

## Practical Recommendation

Do not start by moving all reporting code.

The first real extraction should be helper-only, route-free, query-free, and PDF-light. That keeps the first backend extraction small enough to roll back quickly if needed.
