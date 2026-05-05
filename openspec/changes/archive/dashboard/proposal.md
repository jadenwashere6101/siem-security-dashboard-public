# Dashboard Proposal

## Purpose
Define the behavior of the SIEM dashboard that retrieves alert data from the backend and visualizes security activity for monitoring and response.

---

## Problem
Alert data exists in the backend, but without a defined dashboard behavior, there is no consistent user-facing way to monitor active threats, review recent alerts, or interact with alert status.

---

## Proposed Solution
Implement a React-based dashboard that:

- Polls the backend periodically for updated alert data
- Visualizes alert information using Chart.js
- Displays:
  - Total alerts
  - Alerts by severity
  - Top source IPs
  - Recent alerts table
- Supports alert filtering by:
  - severity
  - status
- Supports resolving alerts directly from the UI

---

## Behavior

- Frontend retrieves alert data from:
  - `GET /alerts`
- Polling occurs every few seconds so the dashboard stays up to date
- Users can filter alert data without changing the backend contract
- Users can resolve alerts through:
  - `POST /alerts/<id>/status`

---

## Scope

This proposal applies to:
- React frontend dashboard behavior
- Backend-to-frontend alert display flow
- Alert interaction from the dashboard

---

## Out of Scope

- User authentication/authorization
- Historical analytics beyond current alerts response
- Non-alert event exploration

---

## Success Criteria

- Dashboard displays live alert data from backend
- Polling keeps UI updated automatically
- Filtering works correctly by severity and status
- Alerts can be resolved from the UI