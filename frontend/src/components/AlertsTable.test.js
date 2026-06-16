import { useState } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import AlertsTable from "./AlertsTable";

const baseAlert = {
  id: 101,
  alert_type: "failed_login_threshold",
  source: "bank_app",
  source_type: "custom",
  source_ip: "8.8.8.8",
  city: "Mountain View",
  country: "United States",
  severity: "high",
  status: "open",
  message: "Failed login threshold exceeded",
  created_at: "2026-06-16T12:00:00Z",
  reputation_score: 0,
  reputation_label: "Normal",
  reputation_source: "test",
  reputation_summary: "No external issues",
  behavioral_reputation: {
    score: 0,
    label: "Normal",
    source: "siem_internal",
    summary: "No elevated behavioral signals observed in SIEM history.",
    contributing_signals: [],
  },
  response_action: "monitor",
  response_status: "pending",
};

const styles = {};

const sidePanelResponseStatus = () =>
  screen.getAllByText(/Response Status:/).at(-1).parentElement;

function AlertsTableHarness({ initialAlerts, onSetAlerts }) {
  const [alerts, setAlertsState] = useState(initialAlerts);
  const [selectedAlertId, setSelectedAlertId] = useState(null);
  const handleSetAlerts = (nextAlerts) => {
    onSetAlerts(nextAlerts);
    setAlertsState(nextAlerts);
  };

  return (
    <AlertsTable
      alerts={alerts}
      canTakeAlertActions={true}
      setAlerts={handleSetAlerts}
      searchTerm=""
      setSearchTerm={() => {}}
      sortOption="newest"
      setSortOption={() => {}}
      severityFilter="all"
      setSeverityFilter={() => {}}
      sourceFilter="all"
      setSourceFilter={() => {}}
      statusFilter="all"
      setStatusFilter={() => {}}
      selectedAlertId={selectedAlertId}
      setSelectedAlertId={setSelectedAlertId}
      getSeverityBadgeStyle={() => ({})}
      cardStyle={styles}
      cardHeaderStyle={styles}
      cardTitleStyle={styles}
      cardSubtitleStyle={styles}
      filterWrapperStyle={styles}
      filterLabelStyle={styles}
      selectStyle={styles}
      emptyStateStyle={styles}
      emptyStateTextStyle={styles}
      tableWrapperStyle={styles}
      tableStyle={styles}
      headerCellStyle={styles}
      bodyCellStyle={styles}
      onUpdateStatus={() => ({ ok: true })}
      monoCellStyle={styles}
      tableRowStyle={styles}
      expandedCellStyle={styles}
      expandedContentStyle={styles}
      expandedLabelStyle={styles}
      expandedTextStyle={styles}
    />
  );
}

function renderAlertsTable(alerts, setAlerts) {
  return render(
    <AlertsTableHarness initialAlerts={alerts} onSetAlerts={setAlerts} />
  );
}

test("side panel uses refreshed alert data after manual response execution", async () => {
  const refreshedAlert = {
    ...baseAlert,
    response_action: "block_ip",
    response_status: "success",
  };
  const setAlerts = jest.fn();

  global.fetch = jest.fn((url, options = {}) => {
    const path = String(url);
    if (path.endsWith("/alerts/101/response-log")) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve([]),
      });
    }
    if (path.endsWith("/alerts/101/notes")) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve([]),
      });
    }
    if (path.endsWith("/alerts/101/execute") && options.method === "POST") {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ response_status: "success" }),
      });
    }
    if (path.endsWith("/alerts")) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve([refreshedAlert]),
      });
    }
    return Promise.reject(new Error(`Unexpected fetch: ${path}`));
  });

  renderAlertsTable([baseAlert], setAlerts);

  await userEvent.click(screen.getByText("failed_login_threshold"));
  expect(sidePanelResponseStatus()).toHaveTextContent("pending");

  await userEvent.click(screen.getAllByRole("button", { name: "Block IP" }).at(-1));

  await waitFor(() => {
    expect(setAlerts).toHaveBeenCalledWith([refreshedAlert]);
  });

  await waitFor(() => {
    expect(sidePanelResponseStatus()).toHaveTextContent("success");
  });
});
