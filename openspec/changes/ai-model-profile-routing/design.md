## Context

The AI surface includes dashboard graph explanation buttons, dashboard metric buttons, alert detail buttons, source-IP context buttons, incident buttons, SOC Command Center recon buttons, Response Registry buttons, command-palette/Anakin command flows, floating chat, guided investigations, review-only drafts, SOC briefing worker synthesis, and the Repo Architecture Assistant. Most frontend entry points route through shared handlers in `App.js`, then one of `/ai/explain`, `/ai/chat`, `/ai/drafts`, `/ai/investigations`, or `/ai/repo/chat`. SOC briefings call the gateway from the worker path.

The current gateway request contract has no semantic profile, and the provider reads `AI_LOCAL_MODEL`, `AI_LOCAL_TIMEOUT_SECONDS`, and `AI_MAX_PROMPT_CHARS` globally. This causes short UI actions and deep jobs to compete for one model/timeout.

## Inventory Table

The authoritative machine-readable inventory is `core/ai/profile_registry.py`. It maps each AI path to a profile. Human summary:

| Path | Entry Surface | Backend | Profile |
| --- | --- | --- | --- |
| Dashboard metric explain | `DashboardMetrics` | `/ai/explain` `ask_dashboard` | `fast_triage` |
| Dashboard graph/anomaly explain | `DashboardVisuals` | `/ai/explain` `explain_anomaly` | `fast_triage` |
| Alert explain/why/recommend | `AlertDetailsPanel` | `/ai/explain` alert actions | `fast_triage` |
| Detection explain | `AlertDetailsPanel` | `/ai/explain` `explain_detection` | `fast_triage` |
| Source-IP explain/recon/activity | `SourceIpContext` | `/ai/explain` source-IP actions | `fast_triage` |
| Incident summarize/next steps | `IncidentsPanel` | `/ai/explain` incident actions | `fast_triage` |
| SOC Command Center recon explain | `SocCommandCenter` | `/ai/explain` `explain_recon_activity` | `fast_triage` |
| SOC Command Center recon quick investigate | `SocCommandCenter` | `/ai/explain` `investigate_cluster` | `fast_triage` |
| Response Registry explain | `ResponseRegistryPanel` | `/ai/explain` `explain_response` | `fast_triage` |
| Generic command summarize/explain/suggested actions | Command palette/Anakin registry | `/ai/explain` generic actions | `fast_triage` |
| General Ask Anakin chat | Floating chat/command palette | `/ai/chat` | `fast_triage` |
| Guided investigations | Guided investigation buttons/command | `/ai/investigations` | `guided_analysis` |
| Review-only drafts | Draft buttons/command | `/ai/drafts` | `guided_analysis` |
| Manual and scheduled SOC briefings | SOC briefing run-now/worker | worker gateway call | `deep_briefing` |
| Repo Architecture Assistant | admin repo assistant | `/ai/repo/chat` | `developer_assistant` |

## Design Decisions

- Add `profile` to `AiGatewayRequest`; clients never send profile/model/timeout directly.
- Keep final mapping backend-owned through `core/ai/profile_registry.py`.
- Add `AiModelProfile` settings to `AiGatewayConfig`.
- Provider execution resolves the request profile and uses profile model, timeout, prompt budget, output budget, and temperature.
- All profiles are local-only with paid fallback disabled by default.
- Deep briefing still forces local-only when the global gateway mode permits automatic paid fallback.
- Metadata adds profile name, task category, timeout, and output budget.
- Context normalization accepts frontend workspace section IDs for generic Anakin commands while preserving strict ID requirements for specific detail-context buttons.

## Configuration

New environment variables:

- `AI_FAST_MODEL`, `AI_FAST_TIMEOUT_SECONDS`, `AI_FAST_MAX_PROMPT_CHARS`, `AI_FAST_MAX_OUTPUT_TOKENS`, `AI_FAST_TEMPERATURE`
- `AI_GUIDED_MODEL`, `AI_GUIDED_TIMEOUT_SECONDS`, `AI_GUIDED_MAX_PROMPT_CHARS`, `AI_GUIDED_MAX_OUTPUT_TOKENS`, `AI_GUIDED_TEMPERATURE`
- `AI_DEEP_MODEL`, `AI_DEEP_TIMEOUT_SECONDS`, `AI_DEEP_MAX_PROMPT_CHARS`, `AI_DEEP_MAX_OUTPUT_TOKENS`, `AI_DEEP_TEMPERATURE`
- `AI_DEVELOPER_MODEL`, `AI_DEVELOPER_TIMEOUT_SECONDS`, `AI_DEVELOPER_MAX_PROMPT_CHARS`, `AI_DEVELOPER_MAX_OUTPUT_TOKENS`, `AI_DEVELOPER_TEMPERATURE`

Defaults:

- `fast_triage`: `llama3.2:3b`, 45 seconds, 8000 prompt chars, 512 output tokens.
- `guided_analysis`: `llama3.1:8b`, 90 seconds, 14000 prompt chars, 1200 output tokens.
- `deep_briefing`: `llama3.1:8b`, 150 seconds, 18000 prompt chars, 1800 output tokens.
- `developer_assistant`: `llama3.1:8b`, 120 seconds, 20000 prompt chars, 1600 output tokens.

Compatibility:

- Existing `AI_LOCAL_MODEL` and `AI_LOCAL_TIMEOUT_SECONDS` remain the local provider fallback for guided/deep/developer profiles when profile-specific env vars are absent.
- Fast triage intentionally defaults to `llama3.2:3b` so quick UI actions can become responsive once that model is installed.

## Non-Goals

- No VM access, production `.env` change, deployment, commit, push, or Ollama model installation.
- No paid fallback or client-selectable model names.
- No redesign of the provider abstraction, SOC tools, drafts, or briefing worker architecture.
- No migration.

## Risks

- Fast triage will fail until `llama3.2:3b` is installed on the Mini PC or `AI_FAST_MODEL` is configured to an installed model.
- Some DB-backed button contract tests may skip locally if PostgreSQL is unavailable.
- Profile budgets may need tuning after observing real Mini PC latency.
