## 1. Canonical Catalog Contract

- [x] 1.1 Create one backend-owned canonical detection-rule metadata catalog module with one record per base or correlation rule.
- [x] 1.2 Define the final catalog schema covering rule identity, display metadata, severity metadata, source applicability, MITRE metadata, supported evidence, investigation guidance, analyst-facing why, and tunable parameter definitions where applicable.
- [x] 1.3 Populate catalog records for every currently implemented base detection rule and every currently implemented correlation rule, including `pfsense_firewall_allow_after_deny`.
- [x] 1.4 Add validation helpers for duplicate rule IDs, missing required metadata, invalid severities, `default_severity > maximum_severity`, malformed MITRE metadata, and unsupported applicability sources.

## 2. Consumer Migration

- [x] 2.1 Refactor `engines/detection_config.py` to derive rule inventory, display names, descriptions, and tunable parameter scaffolding from the canonical catalog while preserving runtime override and active-state behavior.
- [x] 2.2 Refactor `engines/severity_response_matrix.py` to derive automatic rule inventory and static rule metadata from the catalog while continuing to merge live playbook and notification-policy behavior dynamically.
- [x] 2.3 Refactor source applicability helpers so applicability metadata is derived from the catalog rather than an independently maintained per-rule registry.
- [x] 2.4 Refactor MITRE enrichment so mapped and intentionally unmapped behavior derives from the catalog rather than a separate MITRE map.
- [x] 2.5 Refactor correlation-rule display inventory so correlation metadata is catalog-owned and no longer shadow-listed outside the catalog.

## 3. Duplicate Registry Removal

- [x] 3.1 Remove `_RULE_METADATA` from `engines/severity_response_matrix.py`.
- [x] 3.2 Remove `_CORRELATION_RULES` from `engines/severity_response_matrix.py`.
- [x] 3.3 Remove duplicate per-rule MITRE registry ownership from `helpers/enrichment_helpers.py`.
- [x] 3.4 Remove independently maintained applicability registry ownership from `engines/detection_applicability.py` or collapse it into catalog-derived helpers.
- [x] 3.5 Remove independently maintained rule inventory, display-name, and description ownership from `engines/detection_config.py`.
- [x] 3.6 Verify no compatibility copy requiring manual synchronization remains in the completed implementation unless a documented compatibility boundary explicitly requires it.

## 4. Drift Validation and Focused Regression

- [x] 4.1 Add focused validation tests proving every implemented base detection rule has exactly one catalog record.
- [x] 4.2 Add focused validation tests proving every implemented correlation rule has exactly one catalog record.
- [x] 4.3 Add focused tests proving Detection Rules inventory and Severity & Response Matrix inventory agree unexpectedly only when validation intentionally allows it.
- [x] 4.4 Add focused tests proving `pfsense_firewall_allow_after_deny` and at least one future-rule-style fixture reach the matrix and relevant consumers automatically through the catalog.
- [x] 4.5 Add focused tests proving MITRE enrichment and intentional-unmapped behavior derive from the catalog without behavior drift.
- [x] 4.6 Add focused tests proving applicability metadata derives from the catalog and rejects unsupported source definitions.

## 5. Verification and Completion Gates

- [x] 5.1 Run focused backend tests for detection rules, severity matrix, applicability, correlations, and MITRE enrichment.
- [x] 5.2 Run `openspec validate canonical-detection-rule-metadata-catalog --strict`.
- [x] 5.3 Run `git diff --check`.
- [x] 5.4 Verify the completed codebase has one authoritative static metadata catalog, all current base and correlation rules represented, duplicate static registries removed, and no unintended detector, severity, threshold, playbook, or notification behavior changes.
