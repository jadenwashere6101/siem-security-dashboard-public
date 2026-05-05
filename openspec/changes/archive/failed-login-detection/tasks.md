# Failed Login Detection Tasks

## Backend
- Query events within 15-minute window
- Group by source_ip
- Count failed login events
- Check for existing open alert
- Insert new alert if conditions met

## Frontend
- Display alerts in dashboard
- Show severity and message
- Allow filtering by type and status

## Validation
- Trigger 3 failed logins → alert appears
- Ensure no duplicate alerts created
- Verify correct message and severity
