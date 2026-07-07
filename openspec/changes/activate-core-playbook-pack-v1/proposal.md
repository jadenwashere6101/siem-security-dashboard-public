## Why

Core Playbook Pack v1 already exists as data and has an idempotent seed helper, but no supported activation path calls it. As a result, the five approved core playbooks remain dormant in target databases unless an operator manually imports Python and invokes the helper.

## What Changes

- Add a small, explicit activation path for Core Playbook Pack v1.
- Make activation manual and repeat-safe by reusing `seed_core_playbook_pack_v1(conn)`.
- Provide clear operator output showing which playbooks were inserted and which already existed.
- Keep activation out of Flask startup, schema migrations, and deployment automation.
- Do not create, redesign, or modify any playbook definitions in this spec.

## Capabilities

### New Capabilities
- `core-playbook-pack-v1-activation`: Defines how Core Playbook Pack v1 is manually and idempotently seeded into a target database.

### Modified Capabilities
- None.

## Impact

- Affects only a future manual activation script and focused tests.
- Reuses existing database connection conventions and the existing seed helper.
- No schema migration, new dependency, startup side effect, backend route, UI change, or engine change.
