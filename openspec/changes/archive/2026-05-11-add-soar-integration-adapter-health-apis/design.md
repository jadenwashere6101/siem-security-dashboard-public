# Design: SOAR Integration Adapter Health APIs

## Proposed architecture
Add a small read-only route for integration adapter status. The route should use the existing integration registry to enumerate simulation adapters and should not instantiate real provider clients or call any external service.

Recommended endpoint:

```http
GET /integrations/status
```

The endpoint should return a stable JSON object that is useful for operators and tests while remaining safe in development and production.

## Files likely to change
- `routes/integration_routes.py` or the existing route module that best matches current route registration patterns.
- `siem_backend.py` only if route registration is centralized there.
- `tests/test_integration_routes.py` or an existing route test file if that matches local convention.
- Existing integration registry code only if a narrow read-only metadata helper is needed.

No schema, frontend, executor, ingest, detection, correlation, SOAR queue, approval, incident, or adapter execution behavior should change.

## API endpoint behavior
`GET /integrations/status` should:
- Require authentication using existing route auth patterns.
- Allow analyst and super-admin read access unless existing project conventions require a narrower read role.
- Return HTTP 200 with adapter status metadata.
- Never perform network calls.
- Never require Slack, email, webhook, or firewall secrets.
- Never mutate firewall or blocklist state.

Example response shape:

```json
{
  "mode": "simulation",
  "simulated": true,
  "real_mode_enabled": false,
  "real_mode_status": "disabled",
  "adapters": [
    {
      "name": "slack",
      "mode": "simulation",
      "simulated": true,
      "real_client": false,
      "supported_actions": ["send_message"]
    }
  ]
}
```

Exact field names may follow existing API naming conventions, but the response must expose adapter name, supported actions, mode, simulated status, and real-mode disabled status.

## Auth and permission expectations
- Use existing token/session authentication helpers.
- Read access should be available to roles that can already inspect SOAR/playbook state, such as analysts and super-admins.
- Unauthenticated requests should return the existing unauthorized response shape.
- Mutation roles are not needed because the endpoint is read-only.

## Registry behavior
The endpoint should call safe registry metadata paths only. It may use `list_integration_adapters()` in simulation mode if that remains local and offline, or a new metadata-only helper if tests show that is cleaner.

Real mode must remain fail-closed. The endpoint may report real mode as disabled/not implemented, but it must not try to initialize real mode or validate real credentials.

## Safety boundaries
- Read-only.
- Simulation-only.
- No provider clients.
- No network calls.
- No secret access requirement.
- No firewall or blocklist mutation.
- No SOAR queue enqueueing.
- No playbook execution or executor invocation.
- Preserve existing adapter and executor behavior.

## Failure behavior
- If adapter metadata cannot be loaded due to an internal bug, return the project-standard 500 error and log the failure.
- Invalid or unsupported `INTEGRATION_MODE=real` should not trigger real behavior. The safest behavior is to report real mode as disabled/fail-closed or to return a controlled unavailable status without network calls.
- Unknown adapters should not appear unless registered in the simulation registry.

## Test strategy
Add backend tests that verify:
- Authenticated analyst or super-admin can read `GET /integrations/status`.
- Unauthenticated requests are rejected using existing auth behavior.
- Response includes `mode: simulation`, `simulated: true`, and real mode disabled/not implemented status.
- Response includes `slack`, `email`, `firewall`, and `webhook` adapters with supported actions.
- Tests monkeypatch network primitives and prove the route makes no network calls.
- Tests clear relevant secret env vars and prove the route does not require secrets.
- Existing playbook executor and integration adapter tests still pass.

## Risks and stop conditions
- Stop if the endpoint requires real provider clients, credentials, or network checks.
- Stop if implementing status requires executor, SOAR queue, schema, frontend, ingest, detection, or correlation changes.
- Stop if auth patterns are unclear enough that adding a route could expose adapter metadata publicly.
- Stop if real mode cannot remain fail-closed.
