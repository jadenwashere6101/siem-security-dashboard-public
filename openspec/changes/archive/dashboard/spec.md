# Dashboard Specification

## Overview

The SIEM dashboard is a React frontend that retrieves alert data from the Flask backend and displays it in a real-time monitoring interface.

The dashboard uses:

- React for UI rendering and state management
- Chart.js for visualization
- Periodic polling to keep alert data current

---

## Data Flow

1. Frontend sends request to:
   - `GET /alerts`

2. Backend returns alerts as JSON

3. Frontend stores the alert array in local state

4. Frontend derives dashboard metrics and filtered views from the alert array

5. Frontend renders:
   - summary metrics
   - charts
   - recent alerts table

---

## Polling Behavior

The frontend polls the backend periodically using `GET /alerts`.

### Current Behavior
- Poll interval: every few seconds
- Polling refreshes alert state automatically without manual page reload

### Expected Behavior
- Latest alerts appear in the dashboard shortly after backend creation
- Resolved alerts are reflected after the next poll cycle

---

## Dashboard Displays

### 1. Total Alerts
Display the total count of alerts currently returned by the backend.

### 2. Alerts by Severity
Display counts for:
- `low`
- `medium`
- `high`
- `critical`

Visualized using Chart.js.

### 3. Top Source IPs
Aggregate alerts by `source_ip` and visualize the most active IPs.

### 4. Recent Alerts Table
Display alerts in tabular form with fields such as:
- `id`
- `alert_type`
- `source_ip`
- `severity`
- `message`
- `created_at`
- `status`

---

## Filtering Behavior

Filtering is implemented in the frontend using the full alert set returned by `GET /alerts`.

### Severity Filter
Supported options:
- all
- low
- medium
- high
- critical

### Status Filter
Supported options:
- open
- resolved

### Behavior
- Filters update displayed alerts and derived chart metrics
- Filtering does not require a separate backend endpoint

---

## Resolve Alert Interaction

The dashboard allows an alert to be resolved using:

- `POST /alerts/<id>/status`

### Request Body

```json
{
  "status": "resolved"
}