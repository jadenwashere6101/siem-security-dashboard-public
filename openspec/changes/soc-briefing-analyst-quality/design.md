# Design: SOC Briefing Analyst Quality

## Approach

Keep the existing scheduled SOC briefing architecture, structured JSON contract, bounded repair path, and deterministic fallback. Improve quality at two allowed layers:

1. Prompting: add an analyst-handoff quality contract to the synthesis payload so model output must explain what happened, why it matters, what changed, immediate attention, correlation, uncertainty, confidence, and evidence-specific recommendations.
2. Post-processing: normalize accepted or fallback sections into analyst-readable strings using only selected security activity, downgraded/noise context, and collected evidence metadata. Empty sections receive analyst judgments rather than generic "No entries recorded" text.

## Evidence Safety

The post-processor may use candidate and evidence-ref metadata internally to write readable language. It must not expose selected-candidate counts, bounded evidence-reference counts, source paths, tool names, record counts, or investigation-engine mechanics in analyst-facing prose. It must not create new alerts, outcomes, containment actions, destinations, endpoints, or telemetry. Where evidence is missing, it says so naturally.

## Non-Goals

- No persistence changes.
- No workflow architecture changes.
- No VM work.
- No deployment.
