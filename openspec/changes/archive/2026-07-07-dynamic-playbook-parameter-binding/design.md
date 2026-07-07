## Context

### Current execution path (re-verified)

1. **Trigger matching** (`engines/playbook_engine.py`): `_fetch_alert` loads alert columns including `source_ip`, `severity`, `reputation_score`, `reputation_label`, `message`, and geo fields. `_evaluate_trigger` uses these for AND-based trigger evaluation. Alert data is not passed to step execution — only `alert_id` is stored on the `playbook_executions` row.

2. **Orchestration** (`engines/soar_playbook_orchestrator.py`): creates `playbook_executions` with `alert_id`. No alert snapshot or param-binding context is attached.

3. **Step execution** (`engines/playbook_step_executor.py`): for adapter actions, `params = step.get("params")` is taken directly from the stored step definition. A separate `context` dict (`execution_id`, `playbook_id`, `alert_id`, `incident_id`, `step_index`) is passed to `execute_playbook_simulated_adapter` but is not merged into `params`. For `block_ip`, `require_unprotected_target(params.get("source_ip"))` validates the static value only. `_resolve_playbook_alert_source_ip` exists for outcome-event linkage but is not used to populate step params.

4. **Definition validation** (`engines/playbook_registry.py`): `validate_playbook_steps` explicitly does not validate `params` shapes — "param shapes are action-specific and belong at execution time."

5. **No binding infrastructure exists:** repo-wide search under playbook modules finds no templating, substitution, or alert-to-param resolution helper.

### Gap

Playbooks are triggered per alert but execute with per-definition static parameters. The engine can match `failed_login_threshold` from `1.2.3.4` and `5.6.7.8` but a `block_ip` step in the matched playbook would target the same authored IP for both. Notification `params.message` strings are equally static. This is not a content-layer problem — it is missing engine capability.

## Goals / Non-Goals

**Goals:**
- Define a single, explicit mechanism for binding playbook step parameter values to alert (and execution) fields at execution time.
- Preserve backward compatibility: literal static values continue to work unchanged.
- Specify validation, security boundaries, and failure behavior so containment and notification actions can be authored safely.
- Expose only fields already available on the alert row at trigger time (no new enrichment pipeline in this spec).

**Non-Goals:**
- Not playbook content (`Core Playbook Pack v1` consumes this capability; does not define it here).
- Not conditional branching, chaining, ad hoc triggers, or enrichment steps (separate roadmap items).
- Not new actions or adapters.
- Not real (non-simulated) firewall execution — simulation vs. live dispatch is unchanged.
- Not a generic expression language (no arithmetic, no cross-step references, no user-defined functions in v1 of this capability).

## Decisions

### Parameter syntax

Playbook authors MAY express a dynamic parameter value as a string containing exactly one alert-field reference using the form `{{alert.<field_name>}}`.

- **Examples:** `"{{alert.source_ip}}"`, `"{{alert.severity}}"`, `"{{alert.reputation_score}}"`, `"{{alert.message}}"`.
- **Static values:** any string (or non-string JSON scalar) that does not match the binding pattern, or that matches but is escaped per validation rules, is passed through verbatim.
- **Rejected alternatives:**
  - Bare `alert.source_ip` without delimiters — too easy to confuse with literal hostnames or messages.
  - Full templating with inline static text (`"Block {{alert.source_ip}} now"`) — deferred; v1 binds whole parameter values only, not embedded substitutions inside a larger string. Notification messages that need alert context should bind the entire `message` param to `{{alert.message}}` or use a dedicated field, or wait for a future embedded-template extension.

### Alert field surface

The binding resolver SHALL expose only fields already loaded by `engines/playbook_engine.py`'s `_fetch_alert` at trigger time:

| Field | Type | Notes |
|---|---|---|
| `id` | integer | alert primary key |
| `alert_type` | string | |
| `severity` | string | `low` / `medium` / `high` / `critical` |
| `source_ip` | string | text via `host(source_ip)` |
| `source` | string | |
| `source_type` | string | |
| `message` | string | |
| `status` | string | |
| `country` | string | nullable |
| `city` | string | nullable |
| `latitude` | number | nullable |
| `longitude` | number | nullable |
| `reputation_score` | number | nullable |
| `reputation_label` | string | nullable |
| `reputation_source` | string | nullable |
| `reputation_summary` | string | nullable |
| `response_action` | string | nullable |
| `response_status` | string | nullable |
| `created_at` | string (ISO) | |

**Not exposed in v1:** MITRE tags, Source-IP Context API payloads, incident fields, prior step outputs, or computed expressions. Those require `Ad Hoc Trigger & Enrichment Step` or chaining.

### Execution context surface (secondary, v1 minimal)

In addition to `alert.*`, the resolver MAY expose read-only execution metadata for future notification templates:

| Field | Type |
|---|---|
| `execution.id` | integer |
| `execution.playbook_id` | string |
| `execution.alert_id` | integer |

Syntax: `{{execution.<field_name>}}` using the same delimiter rules. v1 scope: optional; if omitted from implementation, alert-only binding still satisfies this spec's core requirement.

### Resolution point

Binding SHALL occur in the playbook step executor immediately before action-specific validation and adapter dispatch — after the step is selected for execution, using the `alert_id` on the execution row to load (or reuse) the alert snapshot. Resolved params are used for that execution only; stored playbook definitions remain unchanged.

### Static vs dynamic parameters

- A step's `params` object MAY mix static and dynamic values per key.
- Resolution is per-key: each value is inspected independently.
- After resolution, downstream code (`require_unprotected_target`, adapter dispatch, notification delivery) sees only concrete values — no binding syntax leaks to adapters.

### Actions that benefit

| Action | Param keys | Why binding matters |
|---|---|---|
| `block_ip` | `source_ip` | Must target the triggering alert's offender IP, not a fixed authored IP |
| `notify_slack`, `notify_teams`, `notify_email`, `notify_webhook` | `message`, `subject` (email), `url` (webhook) | Analyst notifications should reference alert-specific context |
| `require_approval` | `reason` (optional) | Approval prompts can cite the triggering alert's type, severity, or IP |
| `monitor`, `flag_high_priority` | none today | No params; unaffected |

### Validation rules

**At definition save time (registry / API):**
- Each `params` value that is a string containing `{{` MUST conform to `{{alert.<field>}}` or `{{execution.<field>}}` with `<field>` in the allowed surface for that namespace.
- Unknown field names SHALL be rejected at save time.
- Non-string param values (numbers, booleans, objects) are always static.

**At execution time:**
- If a dynamic reference resolves to `null`/missing (e.g., `reputation_score` is null), behavior is action-specific (see Missing-field behavior).
- Resolved values MUST be coerced to the type the action expects (string for IPs and messages, number where applicable).

### Security boundaries

- **No arbitrary code execution:** binding is field lookup only — no `eval`, no SQL, no external HTTP at resolution time.
- **Protected-target policy applies post-resolution:** `require_unprotected_target` runs on the resolved `source_ip`, not the binding expression. A dynamic `block_ip` against a protected IP is rejected the same as a static one.
- **No cross-alert data:** resolver loads only the alert linked to the current execution's `alert_id`.
- **Authoring RBAC unchanged:** whoever can `POST /playbooks` can author bindings; no elevation of privilege.
- **Auditability:** resolved values SHOULD appear in the step's `steps_log` output (implementation detail) so analysts can see what IP was targeted, not just the binding expression.

### Missing-field behavior

| Situation | Behavior |
|---|---|
| Dynamic reference to nullable field that is null | Step fails with a defined error code (e.g., `binding_field_missing`) unless the action documents optional params |
| `alert_id` missing on execution | Step fails — no alert context to resolve |
| Alert row deleted between trigger and execution | Step fails — alert not found |
| `block_ip` with unresolved `source_ip` | Step fails; no adapter dispatch |
| Notification with unresolved optional field | Step fails (fail-closed for v1; no silent empty notifications) |

### Future extensibility

- **Embedded templates** (`"Alert from {{alert.source_ip}}: ..."`) — add in a follow-on spec; do not block v1 whole-value binding.
- **Enrichment fields** (MITRE, external context) — add when `Ad Hoc Trigger & Enrichment Step` defines an enrichment snapshot object (e.g., `{{enrichment.mitre_technique}}`).
- **Prior-step outputs** — add when `Playbook Chaining & Cross-Path Orchestration Layer` defines cross-step context.
- **Branch-selected params** — add when `Conditional Branching Primitive` lands.

## Risks / Trade-offs

- **[Risk]** Authors bind `block_ip` to the wrong field (e.g., `source` hostname instead of `source_ip`).
  **[Mitigation]** Definition-time validation documents allowed fields per action; `Core Playbook Pack v1` provides canonical examples.
- **[Risk]** Nullable reputation fields cause notification steps to fail on alerts without enrichment.
  **[Mitigation]** Playbooks should bind required fields that are guaranteed for their trigger (e.g., `source_ip` for IP-based alerts); pack spec documents which fields are safe per trigger.
- **[Risk]** Loading alert row per step adds DB reads.
  **[Mitigation]** Implementation may cache the alert snapshot for the duration of a single execution batch; design allows but does not mandate caching.

## Migration Plan

- Existing playbook definitions with fully static params require no migration — they continue to work.
- No schema change required for v1 binding (resolution is runtime-only). Optional future column for alert snapshot at execution creation is out of scope.
- Rollback: disable binding resolution and treat all params as static (reverts to today's behavior).

## Open Questions

- Should `{{execution.<field>}}` be required in v1 or deferred to keep the first implementation minimal?
- Should definition-time validation warn (vs. reject) on dynamic bindings in notification params where the referenced field is commonly null?
- Should the frontend playbook editor offer a field picker, or is API/server validation sufficient for v1?
