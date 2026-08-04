## Context

Guided-analysis synthesis currently bounds context and tool JSON separately, then concatenates policy, conversation memory, instructions, routing data, question, source citations, context, and evidence. The final serialization can therefore exceed the profile ceiling even though individual sections were compacted. Production observed this after all planning and evidence work had succeeded.

## Goals / Non-Goals

**Goals:**

- Guarantee that every provider-bound guided-analysis prompt fits the selected profile limit.
- Retain mandatory analyst intent, entity/task context, essential evidence, provenance, truncation disclosure, grounding, and safety instructions.
- Produce a deterministic grounded partial result when mandatory content cannot fit.
- Expose measurements that demonstrate what was compacted and whether a provider was invoked.

**Non-Goals:**

- Raising the guided-analysis prompt limit.
- Changing prompts semantically beyond bounded serialization.
- Changing planner ownership, routing, provider assignments, validation, or Anthropic behavior.

## Decisions

1. A prompt-build result will carry the optional prompt and measurements. The builder will assemble a compact mandatory core first and test the complete serialized length after every optional addition. This replaces estimates based on independently sized sections.
2. Optional conversation history is omitted first. Lower-priority context and tool detail is admitted only while the full candidate remains within budget. Compact source references and explicit compaction metadata remain mandatory.
3. If even the mandatory core cannot fit, the gateway is not called. The investigation result uses validated source references and compact evidence summaries to produce a deterministic partial answer that states its limitations and read-only status.
4. The configured 14,000-character ceiling remains unchanged. Before/after candidate measurements and included/omitted section data are attached to the correlation step metadata.

Alternatives considered: raising the limit would mask the serialization defect and increase local inference pressure; truncating the final string could sever instructions or JSON and undermine grounding.

## Risks / Trade-offs

- [Very large questions or source identifiers can consume mandatory space] → Bound individual mandatory values while preserving explicit truncation metadata and source identity.
- [Compaction can omit useful detail] → Prefer essential source-backed summaries and disclose all omissions; preserve full evidence in the investigation result outside the provider prompt.
- [Deterministic fallback is less interpretive] → Label it partial and avoid unsupported synthesis or action claims.

## Migration Plan

No schema or data migration is required. Deploy the backend change after focused and acceptance tests; rollback restores the prior prompt builder.

## Open Questions

None.
