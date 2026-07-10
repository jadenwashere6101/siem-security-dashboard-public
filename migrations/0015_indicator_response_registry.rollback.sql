-- Rollback companion for 0015_indicator_response_registry.sql
-- Drops ONLY Phase-1 registry tables. Never deletes blocked_ips, alerts,
-- incidents, queue, approvals, playbooks, or soar_response_* data.
--
-- Apply manually only when rolling back an unused/empty registry deployment:
--   psql "$DATABASE_URL" -f migrations/0015_indicator_response_registry.rollback.sql

DROP TABLE IF EXISTS indicator_response_events;
DROP TABLE IF EXISTS indicator_registry;
