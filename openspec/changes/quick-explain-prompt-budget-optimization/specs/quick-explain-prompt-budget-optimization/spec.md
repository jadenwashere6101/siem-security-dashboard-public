# quick-explain-prompt-budget-optimization

## ADDED Requirements

### Requirement: Compact Quick Explain Prompt

Quick Explain SHALL use a compact persona/style prompt that preserves required behavior while reducing fixed prompt overhead.

#### Scenario: Quick Explain fits production-like alert context
- **WHEN** a realistic alert-scoped Quick Explain prompt is built
- **THEN** the full prompt SHALL remain below the `fast_triage` prompt limit
- **AND** SHALL retain a useful safety margin without increasing that limit.

#### Scenario: Tone variants fit
- **WHEN** casual, professional, or technical Quick Explain prompts are built
- **THEN** each prompt SHALL remain below the `fast_triage` prompt limit
- **AND** SHALL include the tone classification instruction.

### Requirement: Quick Explain Behavior Preserved

Quick Explain SHALL preserve natural, direct, evidence-bounded behavior.

#### Scenario: Required quick behavior remains
- **WHEN** the Quick Explain policy is generated
- **THEN** it SHALL instruct Anakin to answer immediately, use 2-6 concise sentences, avoid corporate preambles, avoid visible-field-only restatement, state evidence-bounded uncertainty, give one concrete next step, and avoid generic closing disclaimers.

#### Scenario: Few-shot example stays bounded
- **WHEN** the Quick Explain policy is generated
- **THEN** it SHALL keep a minimal style example
- **AND** SHALL NOT include the full broader interactive example block.

### Requirement: Prompt Compaction Preserves Evidence Identity

Quick Explain prompt compaction SHALL keep enough identity and truncation metadata for safe analysis.

#### Scenario: Large context compacts safely
- **WHEN** a large alert, source-IP, or dashboard context is compacted for Quick Explain
- **THEN** the prompt SHALL preserve the user's question, source identity, evidence identity, and truncation metadata
- **AND** SHALL remain fail-closed if the prompt still exceeds the profile limit.

### Requirement: Other Workflow Prompt Contracts Remain Stable

Optimizing Quick Explain SHALL NOT regress other canonical workflows.

#### Scenario: Other workflow prompts stay within limits
- **WHEN** Deep Investigate, Decision Support, Repo Assistant, Generate Artifact, or SOC Briefing prompts are built
- **THEN** they SHALL remain within their configured profile limits
- **AND** SHALL preserve their existing prompt contracts.
