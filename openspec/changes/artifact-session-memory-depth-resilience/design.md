## Context

Session memory deliberately rejects structured values deeper than six levels. Generated artifacts are trusted server output but can contain nested objects inside draft payload list entries. The exact failing path is `assistant structured_payload.artifact.payload.<draft-list-field>[].<nested provider object>`, which crosses the global limit during finalization. The current artifact size bound does not normalize depth.

## Goals / Non-Goals

**Goals:**

- Normalize generated artifact previews to fit the existing session-memory depth and size contract.
- Preserve meaningful draft fields, provenance, auditability, preview-only safety, and thread context.
- Keep fresh and long-lived conversation persistence reliable.
- Continue rejecting arbitrary or unsafe deeply nested session data.

**Non-Goals:**

- Increasing `MAX_JSON_DEPTH` globally.
- Changing draft generation, planner behavior, schemas, providers, routing, or workflows.
- Persisting or applying an operational artifact.

## Decisions

1. Normalize only the server-generated artifact value inside the assistant structured payload, immediately before the existing session-memory sanitizer. Public/user structured payload validation remains unchanged.
2. Preserve the artifact envelope and payload field names. Scalar fields remain scalar; nested list or object values below payload fields are encoded into bounded canonical JSON strings where necessary to prevent excess depth while retaining their meaning.
3. Add shallow storage-normalization metadata with original/stored depth, flattened paths, and truncation state. Existing provenance and preview-only labels remain outside and alongside the normalized artifact.
4. Malformed artifact envelopes and values that cannot be safely bounded continue to fail closed. The normalizer is not a general bypass around session validation.

Alternatives considered: globally raising the depth limit would weaken all session-memory inputs; dropping nested values would lose artifact meaning and auditability.

## Risks / Trade-offs

- [Flattened nested values are less directly machine-addressable] → Preserve canonical JSON text, field names, and flattened-path metadata for review and audit.
- [Provider output can still be excessively large] → Retain existing byte bounds and record truncation explicitly.
- [Normalization could accidentally broaden trust] → Invoke it only for completed server-owned Artifact Generation previews; retain final global sanitization.

## Migration Plan

No schema or existing-row migration is required. New artifact previews use the bounded representation; rollback restores prior persistence behavior.

## Open Questions

None.
