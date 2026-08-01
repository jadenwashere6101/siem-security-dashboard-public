## Overview

The failure mode is not a single timeout. The frontend currently sends broad visible dashboard context with many entity-specific actions, while backend context builders still serialize large raw domain objects into generic JSON prompts. This change introduces a narrow bounded-evidence layer for interactive SOC Anakin actions and makes the selected profile the source of truth for prompt budget checks.

## Action Inventory

| Surface | Route | Selector | Context | Profile |
| --- | --- | --- | --- | --- |
| Dashboard summary | `/ai/explain` | `ask_dashboard` | dashboard | `fast_triage` |
| Dashboard graph/anomaly | `/ai/explain` | `explain_anomaly` | dashboard | `fast_triage` for quick explain, `guided_analysis` for guided investigation |
| Alert explanation | `/ai/explain` | `explain_alert`, `why_important` | alert | `fast_triage` |
| Alert investigation recommendation | `/ai/explain` | `recommend_investigation` | alert | `guided_analysis` |
| Alert guided investigation | `/ai/investigations` | route | alert | `guided_analysis` |
| Alert drafts/checklists | `/ai/drafts` | draft type | alert/detection | `guided_analysis` |
| Source-IP explanation/recon/activity | `/ai/explain` | `explain_ip`, `assess_reconnaissance`, `summarize_activity` | source_ip | `guided_analysis` |
| Source-IP guided/drafts | `/ai/investigations`, `/ai/drafts` | route/draft type | source_ip | `guided_analysis` |
| Incident summarize/next steps | `/ai/explain` | `summarize_incident`, `recommend_next_steps` | incident | `guided_analysis` |
| Recon/SOC Command Center explain/cluster | `/ai/explain` | `explain_recon_activity`, `investigate_cluster` | recon_activity | `guided_analysis` |
| Recon guided/drafts | `/ai/investigations`, `/ai/drafts` | route/draft type | recon_activity | `guided_analysis` |
| Response Registry explain/review/draft | `/ai/explain`, `/ai/investigations`, `/ai/drafts` | `explain_response`/route/draft | response_registry | `guided_analysis` |
| Command Palette Anakin | `/ai/explain` or `/ai/chat` | command action/chat | general/dashboard/entity when available | `fast_triage` for short chat; `guided_analysis` for correlation-heavy actions |
| Floating Anakin chat | `/ai/chat` | `general_chat` | general | `fast_triage` |
| Analyst Workspace AI | `/ai/explain`, `/ai/chat`, `/ai/drafts`, `/ai/investigations` | normalized action | general/entity context | profile by action |

Manual/scheduled SOC briefings remain `deep_briefing` but are not modified here. Repo Architecture Assistant remains `developer_assistant` and is not modified here.

## Context Bounding

Frontend entity-specific actions should send only stable identifiers and concise command metadata. The backend owns evidence selection. Dashboard visible context is still allowed for dashboard/general chat actions, but it must be capped before serialization.

Each backend context builder will return a compact evidence package instead of full raw objects. Packages keep the fields required for analytical value: identifiers, severity/status, timestamps, source/target/service, detection reason, compact intelligence, response state, representative related events, and omitted counts. Builders must remove duplicated nested data and report truncation metadata.

The service constructing the prompt selects the profile first and checks against that profile's `max_prompt_chars`. The provider remains a second enforcement layer.

## Prompt Quality

Prompts become task-specific but share anti-repetition rules:

- do not repeat the alert description or list all visible fields;
- identify what stands out and why it matters here;
- include support, contradiction/benign possibilities, confidence, missing evidence, and concrete read-only next steps;
- do not claim remediation, blocking, approval, SOAR execution, or production mutation occurred;
- do not invent correlations or attack stages.

Explain actions may use compact prose. Guided/draft actions can retain structured schemas, but must consume bounded evidence and avoid generic filler.

## Stale Handling

Read-only AI responses may become stale when the visible UI refreshes, but they remain viewable with an advisory notice. Hard stale blocking remains reserved for confirmable or mutating previews. Stable request identity is based on action, context type, draft/investigation mode, and entity identifier rather than broad dashboard state and filters.

## Security And Safety

Clients still cannot select arbitrary models, timeouts, profiles, prompts, tools, or production actions. All AI paths remain RBAC-protected, read-only/advisory, provider-neutral, local-only/no-paid-fallback under existing gateway policy, and bounded by tool, evidence, prompt, and output budgets.

## Verification Strategy

Backend tests cover inventory/profile mapping, oversized recon/source-IP/incident/registry fixtures, prompt limits, metadata, anti-repetition prompt instructions, and client injection rejection. Frontend tests cover payload shape and stale behavior. Integration-style contract tests trace representative frontend actions through backend route/context/profile/prompt behavior with a recording gateway.
