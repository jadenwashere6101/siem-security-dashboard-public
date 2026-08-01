# Design: SOC Briefing Reliability And Assistant Boundaries

## SOC Briefing Step Persistence

Step records remain keyed by `(run_id, step_index)`. The store should treat this as an idempotency key for the current deterministic worker plan rather than as an exceptional retry hazard.

The step writer must:

- preserve monotonic deterministic step indexes;
- insert a new step when absent;
- update the existing row when the same run and step index is retried;
- keep useful transition metadata such as status, detail, evidence counts, provider state, and timestamps;
- avoid swallowing unexpected constraint errors by preventing duplicate inserts up front or using a safe upsert.

Retries should resume against the existing run and steps without corrupting prior completed steps.

## Stale Recovery

Stale recovery must only act on non-terminal jobs whose leases have actually expired. It must not treat a one-shot timer worker waiting for its next timer invocation as an abandoned active job.

Recovery outcomes:

- active valid lease: leave untouched;
- expired running lease with attempts remaining: requeue/retry;
- expired running lease with attempts exhausted: mark timed out or failed with exact error code;
- terminal job: leave untouched;
- timer not active but no running job: report waiting/inactive health, not job failure.

Retries remain bounded.

## Worker Health

The worker health API should be timer-aware. A oneshot systemd timer normally has no continuously running process, so “not running” is not automatically offline.

The health contract should expose:

- `running` when a worker heartbeat/execution is fresh and active work exists;
- `healthy_waiting` when the timer model is healthy and no job is due/running;
- `recently_successful` when a recent worker execution completed successfully;
- `stale` when expected heartbeat/execution is late relative to configured cadence;
- `failed` when the last worker execution/job failed and no healthier state overrides it;
- `timer_inactive` when timer/schedule metadata indicates the timer is disabled or inactive.

The API may infer timer health from persisted worker heartbeat/execution metadata and SOC briefing control/job state, since Mac source code cannot inspect live systemd state without VM runtime access.

## Run Now Lifecycle

Manual Run Now remains a queue-only request. Gunicorn must not run briefing AI work. The UI should continue polling the manual lifecycle until terminal and then refresh history and select the produced briefing if one exists.

Manual-only mode and paused schedules must not block explicit Run Now. Duplicate active manual jobs remain prevented.

## Repo Assistant Boundaries

Repo Assistant remains for source-code, architecture, implementation, and test questions. A boundary classifier detects questions about live SIEM state: current alerts, incidents, source IP activity, firing detections, dashboard metrics, live SOC state, briefings, and investigation data.

For clearly live-data questions, the service returns a non-provider boundary response with guidance to use normal Anakin surfaces. Repository retrieval and provider calls are skipped. Ambiguous mixed questions fail conservatively when the live-data intent is clear enough to risk a misleading repo answer.

Factual and evaluative repository questions continue to use backend-owned citations.

## Deployment Handoff

Later VM work must verify the SOC briefing timer/service state, migration state if any, manual Run Now lifecycle through `/siem/`, saved briefing history refresh, and Repo Assistant boundary behavior through the deployed browser path.
