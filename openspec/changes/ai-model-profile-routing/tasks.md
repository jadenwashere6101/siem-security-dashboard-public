## 1. OpenSpec

- [x] 1.1 Create proposal, design, spec, and tasks for `ai-model-profile-routing`.
- [x] 1.2 Include the full AI invocation inventory and button-contract fixes in the OpenSpec.
- [x] 1.3 Run strict OpenSpec validation before final handoff.

## 2. Inventory And Button Contracts

- [x] 2.1 Create a machine-readable AI invocation inventory mapped to approved profiles.
- [x] 2.2 Audit SOC Command Center AI buttons and fix unsupported backend action/context mappings.
- [x] 2.3 Normalize generic command-palette workspace context IDs safely.
- [x] 2.4 Add tests that fail when backend AI actions/drafts/workflows are missing profile assignments.

## 3. Backend Profile Routing

- [x] 3.1 Add backend-owned model profile configuration and safe defaults.
- [x] 3.2 Add profile selection to `AiGatewayRequest` and sanitized response metadata.
- [x] 3.3 Make Ollama provider use profile model, timeout, prompt budget, output budget, and temperature.
- [x] 3.4 Wire explain/chat, draft, guided investigation, SOC briefing, and repo assistant call sites to profiles.
- [x] 3.5 Preserve local-only/no-paid-fallback policy for briefing and profile-routed local requests.

## 4. Frontend Metadata

- [x] 4.1 Display selected profile metadata in existing AI response provider metadata.
- [x] 4.2 Do not expose model/timeout controls to clients.

## 5. Verification

- [x] 5.1 Run Python compilation for modified modules.
- [x] 5.2 Run focused AI Gateway/provider/route/worker tests.
- [x] 5.3 Run affected frontend tests.
- [x] 5.4 Run frontend production build.
- [x] 5.5 Run `git diff --check`.
- [x] 5.6 Run `openspec validate ai-model-profile-routing --strict`.
- [x] 5.7 Run `openspec status --change ai-model-profile-routing`.
