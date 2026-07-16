## Why

Static detection-rule metadata is currently split across multiple backend registries, including detection defaults, Severity & Response Matrix metadata, source applicability, correlation-rule listings, and MITRE mappings. That duplication has already drifted: rules can exist in detection logic before appearing correctly in the matrix, and future changes will keep reintroducing the same failure unless one authoritative catalog owns the shared rule contract.

## What Changes

- Add one backend-owned canonical detection-rule metadata catalog covering both base detections and correlation rules.
- Define one metadata record per rule with static analyst-facing and platform-facing fields, including severity, escalation wording, source applicability, MITRE metadata, supported evidence, investigation guidance, and tunable parameter definitions where applicable.
- Migrate current consumers to read from the catalog:
  - Detection Rules inventory and parameter scaffolding
  - Severity & Response Matrix rule inventory and static explanations
  - source applicability metadata
  - MITRE enrichment
  - correlation-rule display inventory
- Remove duplicate static registries after migration, including `_RULE_METADATA`, `_CORRELATION_RULES`, duplicate MITRE maps, and independently maintained applicability inventories.
- Add validation and focused regression coverage that fail when a rule is implemented without catalog metadata, catalog metadata lacks a valid implementation target, inventories drift, or a consumer retains an independently maintained duplicate registry.

## Capabilities

### New Capabilities
- `detection-rule-metadata-catalog`: Introduce one authoritative code-owned metadata catalog for base and correlation detection rules, define consumer behavior, and require drift-prevention validation across the matrix, detection-rule inventory, applicability, and MITRE enrichment.

### Modified Capabilities
- None.

## Impact

- Backend metadata composition in `engines/detection_config.py`, `engines/severity_response_matrix.py`, `engines/detection_applicability.py`, `engines/correlation_engine.py`, and `helpers/enrichment_helpers.py`
- Detection Rules admin API inventory and Severity & Response Matrix API output
- Focused tests for detection rules, severity matrix, source applicability, correlations, and MITRE enrichment
- No database migration expected
