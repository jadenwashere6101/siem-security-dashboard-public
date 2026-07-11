## ADDED Requirements

### Requirement: Clean approved deployment preflight
The VM AI SHALL verify a clean deployment repository and exact approved Mac commit before any merge, migration, restart, or artifact copy.

#### Scenario: VM is dirty
- **WHEN** `git status --short` returns output
- **THEN** deployment SHALL stop and report the files without stashing, resetting, discarding, or merging

#### Scenario: Commit is not approved
- **WHEN** the requested commit cannot be matched to the approved remote commit
- **THEN** deployment SHALL stop before runtime mutation

### Requirement: Ordered migration and service deployment
The VM AI SHALL dry-run then apply migrations, deploy backend and listener artifacts, verify health, and deploy the Mac-built frontend in dependency order.

#### Scenario: Migration dry-run fails
- **WHEN** the dry-run reports an error
- **THEN** no migration apply, service restart, or frontend deployment SHALL occur

#### Scenario: Backend deploy succeeds
- **WHEN** migration apply and service deployment complete
- **THEN** backend health, backend status, listener status, and relevant journals SHALL be healthy before frontend deployment

### Requirement: Synthetic retained and dropped matrix
Runtime validation SHALL cover blocks, inbound sensitive allows, outbound sensitive allows, routine allows, DNS port-53 traffic, supported ICMP block/allow, invalid payloads, and overlapping category controls.

#### Scenario: Defaults are tested
- **WHEN** the approved default configuration is active
- **THEN** all blocks and inbound sensitive allows SHALL be ingested while routine allows, DNS allows, ICMP allows, and unmatched outbound allows SHALL be filtered as specified

#### Scenario: Each override is tested
- **WHEN** a category is enabled or disabled
- **THEN** a next-request canary SHALL prove only the expected matrix rows change

### Requirement: Database non-storage proof
The VM AI SHALL use before/after queries to prove filtered events create no event, raw-event, alert, incident, playbook, queue, or delivery records.

#### Scenario: Routine allow is filtered
- **WHEN** a uniquely identifiable synthetic routine allow returns filtered
- **THEN** all relevant database counts and searches SHALL show zero stored/downstream record for that canary

#### Scenario: Block is retained
- **WHEN** a uniquely identifiable synthetic block is ingested
- **THEN** the event SHALL exist and existing applicable pfSense detection behavior SHALL remain functional

### Requirement: Restartless configuration proof
Every editable category and the sensitive-port list SHALL be proven effective on the next request without restarting backend or listener services.

#### Scenario: Sensitive port changes
- **WHEN** the list is changed through the approved UI/API
- **THEN** the next matching allow and suspicious-allow detector evaluation SHALL use the new list while recorded service PIDs/start times remain unchanged

#### Scenario: Defaults are restored
- **WHEN** restartless testing completes
- **THEN** the approved production defaults SHALL be restored and re-read from the API/UI

### Requirement: Outcome and counter reconciliation
Route responses, listener statistics, backend metrics, journals, and database deltas SHALL consistently distinguish rejected, filtered, failed, and ingested test cases.

#### Scenario: Filtered listener canary runs
- **WHEN** a valid datagram is normalized and backend-filtered
- **THEN** listener/backend filtered counters SHALL increment without an ingested counter or event-table delta

#### Scenario: Invalid datagram runs
- **WHEN** a canary is rejected by source, parsing, authentication, or schema validation
- **THEN** it SHALL not be counted as policy-filtered or ingested

### Requirement: Configuration failure fallback validation
The VM AI SHALL safely prove that unavailable or invalid overrides use conservative code defaults rather than ingest-all behavior.

#### Scenario: Override is invalid or unavailable
- **WHEN** the approved non-destructive failure test is executed
- **THEN** block and inbound sensitive defaults SHALL remain retained, routine allows SHALL remain filtered, and sanitized fallback evidence SHALL be recorded

### Requirement: Rollback and production readiness gate
External pfSense forwarding SHALL remain disabled until deployment, matrix, non-storage, restartless, observability, fallback, and rollback checks pass.

#### Scenario: Any acceptance check fails
- **WHEN** a required runtime check fails
- **THEN** readiness SHALL be denied, external handoff SHALL remain blocked, and rollback or Mac escalation SHALL be performed without VM source edits

#### Scenario: All acceptance checks pass
- **WHEN** evidence is complete and approved defaults are restored
- **THEN** the VM AI SHALL issue a readiness report containing commit, migrations, services, frontend artifact, matrix, counts, counters, rollback status, and explicit permission boundary for the later uncle/pfSense handoff
