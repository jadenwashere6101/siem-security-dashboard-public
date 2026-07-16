## 1. Investigation Value And Confidence

- [x] 1.1 Audit the current analyst-priority surfaces that still rely mainly on Severity, including alerts, incidents, recon activity, source-IP context, and SOC summary views.
- [x] 1.2 Define the explainable Investigation Value model, its allowed inputs, and the visible "why this deserves attention" reasoning contract.
- [x] 1.3 Decide whether analyst confidence adds enough separate value to justify implementation; if retained, define a strictly explainable model and display contract.
- [x] 1.4 Define how Investigation Value evolves over time as progression, recurrence, campaign evidence, and response history accumulate.
- [x] 1.5 Define the smallest additive backend and read-model changes needed to expose Investigation Value reasons without inventing opaque scoring.

## 2. Campaign Intelligence And Returning Attackers

- [x] 2.1 Audit the current recon, source-IP context, and incident linkages to determine where campaign evidence already exists and where it is missing.
- [x] 2.2 Define a target-centered campaign object that groups related activity by repeated destination, repeated services, recurrence, timing patterns, subnet or ASN relationships, and progression evidence.
- [x] 2.3 Define returning-attacker context fields such as first seen, last seen, days observed, prior incidents, prior responses, repeated destinations, repeated services, and campaign membership.
- [x] 2.4 Define campaign-evidence rules that improve investigation context without creating standalone returning-IP alerts or generic campaign alert spam.
- [x] 2.5 Define how campaign membership, recurrence across days, and target-focused linkage should raise Investigation Value while remaining explainable.

## 3. Incident Intelligence

- [x] 3.1 Audit current incident-creation, merge, deduplication, and priority behavior against the goals of lower volume, lower P2 inflation, and clearer ownership.
- [x] 3.2 Define smarter incident ownership rules for source-specific progression, campaign-owned activity, aggregate-owned activity, and commodity recon.
- [x] 3.3 Define when incidents should merge, when they should remain separate, when they should auto-close, and when an alert should never create an incident at all.
- [x] 3.4 Define a more explainable P1/P2/P3 model that is driven by investigation actionability rather than Severity alone.
- [x] 3.5 Define how incident priority and closure reasoning should be visible to analysts in plain English.

## 4. Recon Workflow And Analyst Language

- [x] 4.1 Audit Recon Activity visibility, navigation, and investigation flow across alert details, incidents, source-IP context, and SOC operational surfaces.
- [x] 4.2 Define Recon Activities as first-class analyst workflow objects with natural discovery paths, history, campaign relationships, and target-centered summaries.
- [x] 4.3 Define the analyst-facing Port Scan experience so it quickly communicates routine internet recon, persistence, repeated targeting, campaign evidence, and progression absence or presence.
- [x] 4.4 Define Allow After Deny campaign enrichment behavior for many-source same-destination patterns before proposing any additional alerts.
- [x] 4.5 Perform a scoped wording and label pass in the spec for touched analyst surfaces so anything unclear at a glance is reworded into shorter plain English without expanding into long prose.

## 5. Verification And Handoff

- [x] 5.1 Create focused capability specs covering Investigation Value, campaign intelligence, incident intelligence, Recon workflow, Port Scan explanation, and Allow After Deny enrichment.
- [x] 5.2 Ensure the design and tasks explicitly prohibit standalone returning-IP alerts, automatic severity inflation for returning IPs, alert multiplication, and opaque AI-style scoring.
- [x] 5.3 Run `openspec validate analyst-investigation-intelligence --strict`.
- [x] 5.4 Confirm this change remained Mac-only implementation work with no commit, push, deployment, or VM activity, and capture verification evidence before handoff.
