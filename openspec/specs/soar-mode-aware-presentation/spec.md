# soar-mode-aware-presentation Specification

## Purpose
TBD - created by archiving change mac-soar-mode-accuracy-parent. Update Purpose after archive.
## Requirements
### Requirement: Canonical execution-mode presentation
The frontend SHALL normalize execution mode from supported backend fields and SHALL use truthful, consistent language for real, simulation, read-only, and unknown executions.

#### Scenario: Real execution is completed
- **WHEN** a completed execution has normalized mode `real`
- **THEN** Playbooks status, subtitle/context, and timeline copy SHALL describe a completed real execution and SHALL NOT call it a simulation

#### Scenario: Simulation execution is completed
- **WHEN** a completed execution has normalized mode `simulation`
- **THEN** the view SHALL identify it as a simulation consistently with its mode badge

#### Scenario: Mode is missing or unknown
- **WHEN** neither `mode` nor `execution_mode` supplies a recognized value
- **THEN** the view SHALL use neutral execution language and SHALL NOT assert real or simulation behavior

### Requirement: Mode-aware paused and resumed controls
Approval banners, timeline events, and retry/resume controls SHALL describe workflow state using the selected execution's normalized mode.

#### Scenario: Real execution pauses for approval
- **WHEN** a real execution is awaiting approval
- **THEN** the banner and Resume control SHALL identify the execution as real or use neutral execution wording and SHALL NOT say “simulation”

#### Scenario: Approval is resumed
- **WHEN** an `approval_resumed` event is rendered
- **THEN** its label SHALL match the execution mode, with neutral wording when mode is unknown

#### Scenario: Failed execution can retry
- **WHEN** a failed execution exposes a Retry control
- **THEN** the control SHALL say Retry execution or a correct mode-qualified equivalent and SHALL NOT contradict the mode badge

### Requirement: Conditional provider copy
Provider descriptions SHALL distinguish capability from current enablement and SHALL not imply that a disabled provider is actively delivering.

#### Scenario: Teams remains disabled
- **WHEN** Teams real-mode guards are not satisfied
- **THEN** its description SHALL state that external delivery occurs only when real mode is enabled and its live badge SHALL remain disabled or simulation

