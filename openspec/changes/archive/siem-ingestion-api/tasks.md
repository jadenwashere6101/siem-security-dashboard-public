# Tasks for SIEM Ingestion API

## Backend Implementation

- Ensure `/ingest` endpoint exists in Flask backend
- Validate required fields: event_type, severity, source_ip, message
- Enforce allowed values for event_type and severity
- Implement API key authentication (if configured)
- Return appropriate HTTP responses (200, 400, 401, 500)

## Database Integration

- Insert valid events into `events` table
- Store full payload for traceability

## Detection Integration

- Trigger detection logic immediately after event ingestion
- Ensure detection rules evaluate newly ingested events

## Error Handling

- Handle malformed JSON requests
- Handle missing or invalid fields
- Log errors for debugging

## Testing

- Test valid event ingestion
- Test missing fields
- Test invalid event_type and severity
- Test API key authentication behavior