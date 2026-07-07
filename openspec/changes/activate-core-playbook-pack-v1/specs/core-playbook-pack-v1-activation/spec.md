## ADDED Requirements

### Requirement: Manual Core Pack Activation
The system SHALL provide an explicit manual activation path for Core Playbook Pack v1 that an operator runs intentionally against a target PostgreSQL database.

#### Scenario: Operator runs activation manually
- **WHEN** an operator invokes the Core Playbook Pack v1 activation command with a valid database URL
- **THEN** the command SHALL connect to that database and call the existing Core Playbook Pack v1 seed helper.

#### Scenario: Startup does not seed playbooks
- **WHEN** the Flask application, playbook worker, or response-action worker starts
- **THEN** Core Playbook Pack v1 SHALL NOT be seeded automatically.

#### Scenario: Migration does not seed playbooks
- **WHEN** schema migrations run
- **THEN** they SHALL NOT create, update, enable, or disable Core Playbook Pack v1 playbook definitions.

### Requirement: Idempotent Seed Behavior
The activation path SHALL be safe to run repeatedly and SHALL NOT duplicate or overwrite existing playbook definitions.

#### Scenario: Empty target database
- **WHEN** the activation command runs against a database with no Core Playbook Pack v1 definitions
- **THEN** it SHALL insert the five playbook definitions already defined by `CORE_PLAYBOOK_PACK_V1`.

#### Scenario: Repeated activation
- **WHEN** the activation command runs after the five Core Playbook Pack v1 definitions already exist
- **THEN** it SHALL insert zero rows and SHALL exit successfully with a no-op summary.

#### Scenario: Existing matching ID
- **WHEN** a playbook definition with a Core Playbook Pack v1 ID already exists
- **THEN** activation SHALL leave that row unchanged.

### Requirement: Transactional Script Execution
The activation command SHALL validate before writing, commit on success, and roll back on failure.

#### Scenario: Pack validation fails
- **WHEN** Core Playbook Pack v1 validation returns one or more errors
- **THEN** activation SHALL fail before inserting playbook definitions and SHALL report the validation errors.

#### Scenario: Seed succeeds
- **WHEN** validation passes and the seed helper completes successfully
- **THEN** activation SHALL commit the transaction and report inserted playbook IDs.

#### Scenario: Seed raises an error
- **WHEN** validation or seeding raises an exception
- **THEN** activation SHALL roll back the transaction, close the database connection, and exit non-zero.

### Requirement: No Content or Engine Changes
Activation SHALL use the existing Core Playbook Pack v1 definitions and existing playbook store APIs without changing playbook content or playbook engine behavior.

#### Scenario: Playbook content remains unchanged
- **WHEN** this activation capability is implemented
- **THEN** it SHALL NOT add new playbooks or modify any `CORE_PLAYBOOK_PACK_V1` playbook definition.

#### Scenario: Engine behavior remains unchanged
- **WHEN** this activation capability is implemented
- **THEN** it SHALL NOT modify playbook matching, execution, registry validation, approval handling, scheduling, chaining, branching, or enrichment behavior.
