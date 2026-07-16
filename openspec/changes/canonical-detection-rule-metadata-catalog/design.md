## Context

The current backend owns detection-rule metadata in several separate registries:

- `engines/detection_config.py` defines base-rule inventory, display names, descriptions, and tunable parameter defaults.
- `engines/severity_response_matrix.py` defines default severity, maximum severity, escalation wording, analyst-facing `why`, source/source_type, and its own correlation-rule inventory.
- `engines/detection_applicability.py` defines a separate source-applicability registry keyed by rule ID.
- `engines/correlation_engine.py` remains authoritative for correlation implementation and identifiers, but correlation display metadata is shadow-listed elsewhere.
- `helpers/enrichment_helpers.py` defines a separate MITRE mapping table.

This is already causing drift. The goal is not to parse detector Python or move runtime state into the database. The goal is to create one code-owned static metadata catalog that every consumer reads, while leaving thresholds, active state, playbook definitions, notification policy, and detector logic in their current authoritative locations.

## Goals / Non-Goals

**Goals:**

- Introduce one authoritative static metadata catalog with exactly one record per base or correlation rule.
- Define one shared rule contract covering rule identity, analyst-facing text, severity metadata, applicability, MITRE, supported evidence, investigation guidance, and tunable parameter definitions where applicable.
- Migrate Detection Rules inventory, Severity & Response Matrix, source applicability, MITRE enrichment, and correlation display inventory to read from the catalog.
- Remove duplicate static registries by completion, not just wrap them.
- Add explicit drift validation so missing, malformed, or shadowed rule metadata fails tests.

**Non-Goals:**

- Changing detector behavior, thresholds, or current severity decisions.
- Changing playbook definitions, notification policy logic, or runtime detection overrides.
- Parsing Python detector logic to infer metadata.
- Adding database-backed rule authoring or a new UI.

## Decisions

### Decision 1: Use one code-owned catalog module rather than database-backed metadata

The static contract belongs in source control beside detector code, not in the database. Existing runtime overrides already live in `detection_config`, while playbooks and notification policy remain dynamic runtime inputs. A code-owned catalog keeps the change narrow, avoids migrations, and preserves the current admin/runtime model.

Alternative considered:
- Store rule metadata in PostgreSQL. Rejected because the problem is duplicated source metadata, not end-user editing, and a database layer would add migration and authoring complexity without solving the architectural ownership issue.

### Decision 2: Represent base and correlation rules in the same catalog

The catalog will include `rule_type: base | correlation`. Base rules will also carry tunable parameter definitions; correlation rules will not unless they genuinely have runtime-configurable parameters. This removes the current split where base rules live in `detection_config` and correlation display rows are separately maintained in the matrix builder.

Alternative considered:
- Keep correlation rules in a second registry because their implementations are in `correlation_engine.py`. Rejected because it preserves the exact drift path this change is meant to remove.

### Decision 3: Separate static metadata from runtime state inside one record shape

Each canonical record will carry static metadata plus optional tunable parameter definitions, but not mutable runtime values like current `active`, override status, current playbook enablement, or current notification routing. Consumers will merge catalog metadata with runtime state at read time.

Expected record shape:

- `rule_id`
- `display_name`
- `description`
- `family`
- `rule_type`
- `default_severity`
- `maximum_severity`
- `escalation_conditions`
- `source_applicability`
- `mitre`
- `supported_evidence`
- `investigation_guidance`
- `why`
- `parameters` or `parameter_definitions` for tunable base rules
- optional status field such as `implementation_state` only if needed for explicit reserved/disabled entries

Alternative considered:
- Split metadata into multiple “helper” maps per concern. Rejected because that recreates synchronization requirements and does not produce one authoritative record per rule.

### Decision 4: Keep live response and notification behavior dynamic

The catalog will define static severity and analyst guidance, but `Severity & Response Matrix` must continue to resolve enabled playbooks and effective notification policy live. That prevents another stale registry of response behavior while still centralizing the static rule contract.

### Decision 5: Add explicit inventory validation instead of implicit convention

Implementation must include a validation helper that compares:

- base detector inventory
- correlation-rule inventory
- catalog rule IDs
- Detection Rules API inventory
- Severity Matrix inventory

and fails on mismatch unless a rule is explicitly marked reserved/disabled by the catalog contract.

This is preferable to relying on developers to remember every consumer edit manually.

## Risks / Trade-offs

- [Catalog becomes too broad] → Keep it limited to static metadata plus tunable parameter definitions; do not move runtime enablement, notification policy, or playbook state into it.
- [Correlation inventory remains shadowed] → Require one explicit implementation-to-catalog validation pass for correlation rules and remove matrix-local correlation lists.
- [Backward-compatible wrappers linger permanently] → Allow temporary adapters during migration, but tasks and completion gates require removing duplicate registries before the change is complete.
- [MITRE semantics become over-centralized] → Keep MITRE optional per record, with explicit null/unmapped behavior preserved for intentionally unmapped rules.
- [Detection Rules API and matrix need slightly different projections] → Use projection helpers derived from the same catalog record rather than separate metadata stores.

## Migration Plan

1. Create the canonical catalog module and validation helpers.
2. Port current base-rule static metadata from `detection_config.py` and matrix metadata from `severity_response_matrix.py` into canonical records.
3. Add correlation-rule records for `correlated_activity`, `web_to_app_attack_pattern`, `spray_then_success_pattern`, `cloud_app_error_pattern`, and `azure_auth_abuse_exception_correlation`.
4. Refactor `detection_config.py` to derive inventory, display names, descriptions, and tunable parameter scaffolding from the catalog while preserving runtime override behavior.
5. Refactor `detection_applicability.py` to derive applicability from the catalog or collapse into the catalog helper directly.
6. Refactor `enrichment_helpers.py` to derive MITRE metadata and intentionally-unmapped behavior from the catalog.
7. Refactor `severity_response_matrix.py` to generate rows from the catalog plus live playbook and notification state; remove `_RULE_METADATA` and `_CORRELATION_RULES`.
8. Add drift tests and negative validation for missing rule metadata, invalid severity relationships, malformed MITRE/applicability entries, and consumer inventory mismatches.
9. Remove temporary adapters and compatibility copies.

Rollback: revert the source change. No schema or runtime-data rollback is required because no database migration is expected.

## Open Questions

- Whether `supported_evidence` and `investigation_guidance` should be modeled as free text or bounded lists. The spec can allow bounded structured values with consumer-specific projection text.
- Whether intentionally unmapped MITRE rules should use `mitre: null` only or additionally carry an explicit `mitre_status`/reason field for validation clarity.
