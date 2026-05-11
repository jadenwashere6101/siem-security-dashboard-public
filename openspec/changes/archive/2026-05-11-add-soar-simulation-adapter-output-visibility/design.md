# Design: SOAR Simulation Adapter Output Visibility

## Proposed frontend visibility behavior
`PlaybooksPanel` should detect `steps_log[*].output.adapter_result` and render a compact read-only adapter simulation section inside the existing step timeline item. The section should expose the meaningful structured fields directly while preserving the existing raw output fallback if the component already provides one.

The display should use wording such as "Simulated adapter output" and should never describe the adapter result as completed real remediation.

## Files likely to change
- `frontend/src/components/PlaybooksPanel.js`
- `frontend/src/components/PlaybooksPanel.test.js`

No service, backend, schema, executor, route, ingest, detection, or correlation files should change.

## Data shown
For each timeline step with `output.adapter_result`, show available fields including:
- Adapter name, such as `slack`, `email`, `firewall`, or `webhook`.
- Adapter action, such as `send_message`, `send_email`, `block_ip`, or `post_event`.
- Success or failure.
- `simulated` flag.
- `executed` flag, if present.
- Message.
- Metadata, rendered safely as key-value rows or compact JSON.

Missing optional fields should not break rendering. Unknown metadata keys should be displayed read-only without adding special behavior.

## Rendering approach
- Keep the current execution detail and timeline structure.
- Add a small helper inside `PlaybooksPanel.js` to normalize adapter result fields for display.
- Render adapter metadata in a bounded, wrapping container so large metadata values do not break layout.
- Continue showing raw JSON only as a secondary read-only fallback if it is already present or useful for troubleshooting.
- Do not add new dependencies.

## Loading, error, and empty behavior
Existing loading, error, and empty states should remain unchanged. Executions with no steps, no output, or no `adapter_result` should continue to use the current generic timeline rendering.

## Safety boundaries
- Visibility only.
- Do not add mutation controls.
- Do not call POST, PUT, PATCH, or DELETE endpoints.
- Do not imply real Slack, email, webhook, or firewall execution occurred.
- Do not change executor behavior or adapter behavior.
- Do not change approval decision behavior.
- Do not change SOAR queue, incident, ingest, detection, or correlation behavior.

## Test strategy
Add focused `PlaybooksPanel` tests that verify:
- A `notify_slack` step with `output.adapter_result` displays adapter name, action, success, message, and simulated status.
- A `block_ip` step displays as simulated and does not imply a real firewall mutation.
- Adapter metadata is rendered read-only.
- Steps without `adapter_result` still render normally.
- The panel does not add run, retry, cancel, approve, deny, or resume controls as part of this change.

## Risks and stop conditions
- Stop if the existing API response does not preserve `steps_log[*].output.adapter_result`.
- Stop if rendering requires backend, executor, schema, or service changes.
- Stop if the UI change starts to introduce execution, retry, approval, or mutation controls.
- Stop if tests require broad rewrites outside `PlaybooksPanel.test.js`.
