# Canonical Response Action Inventory (Phase 1.1)

Snapshot of producers/consumers for analyst response actions before unification.

## `block_ip`

| Surface | Path | Behavior before Phase 1 |
|---------|------|-------------------------|
| Manual alert execute | `routes/alert_mutation_routes.py` → `execute_response_action` | Creates Blocklist tracking + log |
| Blocklist form | `routes/blocklist_routes.py` → `create_blocked_ip_record` | Creates Blocklist; errors on duplicate active |
| Playbook step | `engines/playbook_step_executor.py` via firewall adapter | Simulation only; no Blocklist write |
| Response queue | `engines/soar_action_worker.py` + `SimulationExecutor` | Simulation only; approval-gated |
| Ingest enqueue | `engines/soar_enqueue_orchestrator.py` → `enqueue_response_action` | Queues detection-chosen action |
| Reputation default | `core/ip_helpers.determine_response_action` | Score ≥ 80 → `block_ip` |

## `monitor`

| Surface | Path | Behavior before Phase 1 |
|---------|------|-------------------------|
| Manual alert execute | `alert_mutation_routes` | Log-only simulation details |
| Playbook step | CORE_ACTIONS in playbook registry | Simulated playbook step |
| Response queue | `SimulationExecutor._simulate_monitor` | Log-only |
| Reputation default | score &lt; 60 → `monitor` | Enqueued for simulation |

## `flag_high_priority` / escalate

| Surface | Path | Behavior before Phase 1 |
|---------|------|-------------------------|
| Manual alert execute | `alert_mutation_routes` | Log-only “simulated escalation” |
| Playbook step | CORE_ACTIONS | Simulated step |
| Response queue | `SimulationExecutor._simulate_flag_high_priority` | Log-only |
| Reputation default | 60–79 → `flag_high_priority` | Enqueued for simulation |

## `notify` (bare)

| Surface | Path | Behavior before Phase 1 |
|---------|------|-------------------------|
| Historical / bad producers | queue / dead letters | `unsupported_action` dead letters |
| Playbook validation | `KNOWN_PLAYBOOK_ACTIONS` | Bare `notify` not in set (provider-specific only) |
| Legacy outcome tests | insert `response_action='notify'` | Compatibility fixtures only |

## `enrich_context`

| Surface | Path | Behavior before Phase 1 |
|---------|------|-------------------------|
| Playbook executor | `_execute_enrich_context_step` | Read-only DB enrichment (correct owner) |
| Misrouted queue rows | historical dead letters | `unsupported_action` when hit by SimulationExecutor |

## Shared outcome / audit

- `core/soar_response_outcomes.py` — decisions + outcome events
- `response_actions_log` / `response_actions_queue`
- `core/soar_protected_targets.require_unprotected_target` for `block_ip`
