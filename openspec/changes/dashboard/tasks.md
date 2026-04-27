# Dashboard Tasks

## Frontend Setup

- [ ] Implement React dashboard structure
- [ ] Integrate Chart.js for data visualization
- [ ] Maintain alert data in frontend state

---

## Backend Data Retrieval

- [ ] Fetch alerts from `GET /alerts`
- [ ] Parse backend JSON response
- [ ] Store results in local state

---

## Polling

- [ ] Implement periodic polling
- [ ] Refresh alert state every few seconds
- [ ] Ensure polling updates UI automatically

---

## Display Logic

- [ ] Show total alert count
- [ ] Aggregate alerts by severity
- [ ] Aggregate alerts by source IP
- [ ] Render recent alerts table

---

## Filtering

- [ ] Add severity filter control
- [ ] Add status filter control
- [ ] Apply filters in frontend state/view logic

---

## Resolve Interaction

- [ ] Add resolve button to alert rows
- [ ] Send `POST /alerts/<id>/status`
- [ ] Update frontend state after resolution

---

## Testing

- [ ] Verify dashboard loads alerts from backend
- [ ] Verify polling refreshes data automatically
- [ ] Verify severity filter works
- [ ] Verify status filter works
- [ ] Verify resolve action updates alert state
- [ ] Verify charts and table stay in sync with filtered data