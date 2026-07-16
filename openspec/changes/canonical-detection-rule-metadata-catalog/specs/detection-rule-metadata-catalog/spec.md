## ADDED Requirements

### Requirement: Canonical detection-rule metadata catalog
The backend SHALL define one authoritative code-owned detection-rule metadata catalog for both base detection rules and correlation rules. The catalog SHALL contain exactly one static metadata record per rule and SHALL be the authoritative source for shared rule metadata consumed by backend APIs and enrichment helpers.

Each catalog record SHALL support:

- `rule_id`
- `display_name`
- `description`
- `family`
- `rule_type` with values `base` or `correlation`
- `default_severity`
- `maximum_severity`
- `escalation_conditions`
- `source_applicability`
- MITRE metadata
- `supported_evidence`
- `investigation_guidance`
- analyst-facing `why`
- tunable parameter definitions where applicable

The catalog SHALL describe static behavior only. Runtime threshold overrides, active state, enabled playbooks, notification policy, and detector execution logic SHALL remain authoritative in their current runtime systems.

#### Scenario: Catalog record exists for every implemented rule
- **WHEN** the backend rule inventory is evaluated
- **THEN** every implemented base detection rule and every implemented correlation rule SHALL have exactly one catalog record

#### Scenario: Catalog does not require Python parsing
- **WHEN** a consumer needs rule metadata
- **THEN** it SHALL read that metadata from the catalog rather than inferring it from detector or correlation Python logic

### Requirement: Duplicate static metadata registries are removed
After implementation completion, duplicate static metadata registries SHALL be removed rather than left as compatibility copies requiring manual synchronization.

The completed implementation SHALL NOT retain:

- `engines/severity_response_matrix.py::_RULE_METADATA`
- `engines/severity_response_matrix.py::_CORRELATION_RULES`
- a duplicate per-rule MITRE mapping table in `helpers/enrichment_helpers.py`
- an independently maintained per-rule applicability registry in `engines/detection_applicability.py`
- independently redefined rule inventory, display names, or descriptions in `engines/detection_config.py`
- shadow-listed correlation-rule display metadata outside the catalog

Temporary adapters MAY exist during implementation, but SHALL be removed before the change is complete unless a documented compatibility boundary genuinely requires one.

#### Scenario: Final state has one authoritative static registry
- **WHEN** implementation is complete
- **THEN** all static shared rule metadata SHALL resolve to the canonical catalog and no independently maintained duplicate registry SHALL remain in the completed codebase

### Requirement: Detection Rules inventory derives from the catalog
The Detection Rules backend inventory and related UI scaffolding SHALL derive rule inventory, display names, descriptions, and tunable parameter definitions from the canonical catalog while preserving the existing runtime override system for parameter values and active state.

#### Scenario: Base-rule detection inventory uses catalog metadata
- **WHEN** Detection Rules inventory is requested
- **THEN** each base rule SHALL expose its `rule_id`, display text, description, applicability, and tunable parameter scaffolding from the catalog
- **AND** current runtime override values and active state SHALL still come from the existing detection configuration system

#### Scenario: Correlation rules remain outside runtime threshold editing
- **WHEN** a catalog record represents a correlation rule without tunable runtime parameters
- **THEN** it SHALL still exist in the catalog
- **AND** it SHALL NOT require fake threshold scaffolding solely to satisfy the Detection Rules contract

### Requirement: Severity & Response Matrix derives rule inventory from the catalog
The Severity & Response Matrix SHALL derive its rule inventory and static rule metadata directly from the canonical catalog. Static severity wording, escalation explanation, analyst `why`, and correlation-rule display metadata SHALL not be maintained in the matrix builder separately.

The matrix MAY continue to merge live playbook behavior and effective notification policy dynamically at read time.

#### Scenario: Cataloged rule automatically appears in the matrix
- **WHEN** a new implemented rule is added to the catalog
- **THEN** the Severity & Response Matrix SHALL include that rule without requiring a separate matrix-local rule registration

#### Scenario: Allow-after-deny appears through the catalog
- **WHEN** `pfsense_firewall_allow_after_deny` exists in the detector implementation and in the catalog
- **THEN** the Severity & Response Matrix SHALL include it automatically from the catalog-driven inventory

### Requirement: Source applicability derives from the catalog
Rule source applicability metadata SHALL derive from the canonical catalog rather than from an independently maintained applicability registry.

#### Scenario: Applicability metadata matches catalog source applicability
- **WHEN** a consumer requests rule applicability metadata
- **THEN** the returned classification and allowed sources SHALL be derived from the catalog record for that rule

### Requirement: MITRE enrichment derives from the catalog
Per-rule MITRE mappings and intentional unmapped behavior SHALL derive from the canonical catalog rather than a separate independently maintained MITRE registry.

#### Scenario: Mapped rule enriches from catalog MITRE metadata
- **WHEN** an alert is enriched for a rule whose catalog record contains MITRE metadata
- **THEN** the enrichment helper SHALL return those MITRE fields from the catalog

#### Scenario: Intentionally unmapped rule preserves null MITRE shape
- **WHEN** an alert is enriched for a rule whose catalog record intentionally omits MITRE mapping
- **THEN** the enrichment helper SHALL preserve the existing null-field shape without inventing a mapping

### Requirement: Correlation rules are first-class catalog records
Correlation rules SHALL be represented in the same canonical catalog as base detection rules, using `rule_type: correlation`, and SHALL be discoverable by consumers that need rule inventory or analyst-facing metadata.

#### Scenario: Correlation rule inventory is catalog-owned
- **WHEN** the system evaluates correlation-rule metadata for display or matrix generation
- **THEN** it SHALL use catalog records rather than a separately shadow-listed correlation metadata registry

### Requirement: Drift validation fails on incomplete or conflicting rule metadata
Implementation SHALL include validation and focused tests that fail when the rule catalog, rule implementations, and metadata consumers drift from one another.

Validation SHALL fail when:

- an implemented base detection rule lacks a catalog record
- an implemented correlation rule lacks a catalog record
- a catalog rule has no corresponding implementation unless explicitly marked reserved or disabled by the catalog contract
- duplicate rule IDs exist
- required metadata is missing
- severity values are invalid
- `default_severity` exceeds `maximum_severity`
- applicability references unsupported sources
- MITRE entries are malformed
- a consumer still contains an independently maintained duplicate registry
- the matrix omits a catalog rule
- Detection Rules inventory and matrix inventory disagree unexpectedly

#### Scenario: Inventory mismatch fails validation
- **WHEN** rule implementations, the catalog, Detection Rules inventory, and matrix inventory are compared during focused validation
- **THEN** the validation SHALL fail if their rule inventories differ unexpectedly

#### Scenario: Future rule automatically reaches consumers
- **WHEN** a future implemented rule is added with one valid catalog record
- **THEN** focused tests SHALL prove it appears through the catalog in the relevant inventory and matrix consumers without requiring separate static metadata edits elsewhere

### Requirement: Completion leaves one authoritative final state
The final implementation SHALL not stop in a half-canonical state. Consumer-by-consumer migration MAY be used during implementation, but the completed change SHALL leave one authoritative static metadata catalog with duplicate registries removed.

#### Scenario: Completed change preserves behavior while removing drift paths
- **WHEN** the catalog migration is complete
- **THEN** static metadata consumers SHALL read from one authoritative catalog
- **AND** no detector behavior, severity decision, threshold, playbook behavior, or notification policy behavior SHALL change unintentionally as a side effect of the metadata consolidation
