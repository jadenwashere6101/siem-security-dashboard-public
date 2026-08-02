# Design: SOC Briefing Analyst Quality

## Approach

Keep the existing scheduled SOC briefing architecture, structured JSON contract, bounded repair path, and deterministic fallback. Improve quality at two allowed layers:

1. Prompting: add an analyst-handoff quality contract to the synthesis payload so model output must explain what happened, why it matters, what changed, immediate attention, correlation, uncertainty, confidence, and evidence-specific recommendations.
2. Post-processing: normalize accepted or fallback sections into analyst-readable strings using only selected security activity, downgraded/noise context, and collected evidence metadata. Empty sections receive analyst judgments rather than generic "No entries recorded" text.

## Evidence Safety

The post-processor may use candidate and evidence-ref metadata internally to write readable language. It must not expose selected-candidate counts, bounded evidence-reference counts, source paths, tool names, record counts, or investigation-engine mechanics in analyst-facing prose. It must not create new alerts, outcomes, containment actions, destinations, endpoints, or telemetry. Where evidence is missing, it says so naturally.

## Production Defect Correction

Production SOC Briefings showed raw Python dictionary strings in Evidence Reviewed and Recommendations, such as `{'fact': '...'}`, `{'type': 'alert_details', 'description': '...'}`, `{'step': 1, 'description': '...'}`, and `{'action': '...', 'target': '...'}`. The root cause was a narrow dict-field allowlist in `_readable_item_text()` followed by `str(item).strip()` for unknown dict shapes.

The correction replaces direct dict stringification with deterministic, section-aware normalization:

- Evidence Reviewed translates `fact`, `inference`, `uncertainty`, `missing_evidence`, `type`, and `description` into what the evidence showed.
- Recommendations translate `action` + `target`, `step` + `description`, and `recommended_action` + `reason` into prioritized analyst instructions.
- Critical Findings, Escalations, and Low Priority Findings preserve semantic fields when present and degrade gracefully for partial shapes.
- Unknown dicts recursively extract sanitized scalar values, omit internal metadata keys, and produce readable section-specific prose or a deterministic empty-section judgment.
- Analyst-facing output never uses `str(dict)`, `repr(dict)`, raw JSON, source paths, tool names, record IDs/counts, `dedup_key`, or lifecycle/storage terminology.

A later production check found a second Executive Summary defect: `_briefing_summary()` accepted any non-empty model summary that was not a known placeholder and did not contain internal terminology. Bare labels such as "Potential Scanning Activity" and "pfSense Firewall Port Scans" therefore became the Executive Summary.

The correction adds a deterministic Executive Summary quality gate. A model summary is preserved only when it has enough structure and analyst substance to communicate activity, security judgment or why it matters, and analyst direction or next action. Bare titles, fragments, short alert-family labels, placeholder-style summaries, and summaries lacking both judgment and direction fall back to the deterministic handoff composer built from `_activity_overview`, `_security_judgment`, `_attention_sentence`, and `_next_action_sentence`. No model repair is requested solely for summary quality.

## Non-Goals

- No persistence changes.
- No workflow architecture changes.
- No VM work.
- No deployment.
