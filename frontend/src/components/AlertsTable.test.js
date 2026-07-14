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

const trackingOutcome = {
  decision_id: 10,
  alert_id: 101,
  queue_id: 202,
  selected_action: "block_ip",
  decision_source: "manual",
  execution_actor: "manual",
  execution_mode: "tracking_only",
  execution_state: "succeeded",
  external_executed: false,
  tracking_recorded: true,
  simulated: false,
  reason_code: "tracking_only",
  outcome_summary: "Recorded in SIEM blocklist.",
};

const styles = {};

const sidePanelResponseOutcome = () =>
  screen.getAllByText(/Response Outcome:/)[0].parentElement;

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
      totalAlerts={alerts.length}
      pageOffset={0}
      pageLimit={50}
      pageEnd={alerts.length}
      onRefreshAlerts={async () => {
        const response = await global.fetch("/alerts");
        const payload = await response.json();
        const nextItems = Array.isArray(payload?.items) ? payload.items : payload;
        handleSetAlerts(nextItems);
      }}
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
    response_outcome: trackingOutcome,
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
        json: () => Promise.resolve({ response_outcome: trackingOutcome }),
      });
    }
    if (path.endsWith("/alerts")) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ items: [refreshedAlert], total: 1, limit: 50, offset: 0 }),
      });
    }
    return Promise.reject(new Error(`Unexpected fetch: ${path}`));
  });

  renderAlertsTable([baseAlert], setAlerts);

  await userEvent.click(screen.getByText("failed_login_threshold"));
  expect(sidePanelResponseOutcome()).toHaveTextContent("Observed only");
  expect(screen.queryByText("Response Status:")).not.toBeInTheDocument();

  await userEvent.click(screen.getAllByRole("button", { name: "Block IP" }).at(-1));

  await waitFor(() => {
    expect(setAlerts).toHaveBeenCalledWith([refreshedAlert]);
  });

  await waitFor(() => {
    expect(sidePanelResponseOutcome()).toHaveTextContent("Tracking only");
  });
});

test("side panel ignores stale legacy pending when canonical outcome is terminal", async () => {
  const alertWithStaleStatus = {
    ...baseAlert,
    response_action: "block_ip",
    response_status: "pending",
    response_outcome: trackingOutcome,
  };

  global.fetch = jest.fn((url) => {
    const path = String(url);
    if (path.endsWith("/alerts/101/response-log") || path.endsWith("/alerts/101/notes")) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve([]),
      });
    }
    return Promise.reject(new Error(`Unexpected fetch: ${path}`));
  });

  renderAlertsTable([alertWithStaleStatus], jest.fn());
  await userEvent.click(screen.getByText("failed_login_threshold"));

  expect(sidePanelResponseOutcome()).toHaveTextContent("Tracking only");
  expect(screen.queryByText("Response Status:")).not.toBeInTheDocument();
  expect(screen.getAllByTestId("response-state-summary")[0]).toHaveTextContent(
    "Tracking only"
  );
  expect(screen.queryByText("Pending approval")).not.toBeInTheDocument();
});

test("manual block_ip feedback uses tracking-only wording without executed copy", async () => {
  const refreshedAlert = {
    ...baseAlert,
    response_action: "block_ip",
    response_status: "success",
    response_outcome: trackingOutcome,
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
        json: () => Promise.resolve({ response_outcome: trackingOutcome }),
      });
    }
    if (path.endsWith("/alerts")) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ items: [refreshedAlert], total: 1, limit: 50, offset: 0 }),
      });
    }
    return Promise.reject(new Error(`Unexpected fetch: ${path}`));
  });

  renderAlertsTable([{ ...baseAlert, response_outcome: null }], setAlerts);

  await userEvent.click(screen.getByText("failed_login_threshold"));
  await userEvent.click(screen.getAllByRole("button", { name: "Block IP" }).at(-1));

  const feedback = await screen.findByText(/Tracking only: SIEM blocklist entry recorded/i);
  expect(feedback).toHaveTextContent("No firewall, provider, external, or local enforcement occurred.");
  expect(feedback).not.toHaveTextContent("Executed");
});

test("pfSense alert rows show cooldown and suppressed roll-up indicators", async () => {
  global.fetch = jest.fn((url) => {
    const path = String(url);
    if (path.endsWith("/alerts/101/response-log") || path.endsWith("/alerts/101/notes")) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve([]),
      });
    }
    return Promise.reject(new Error(`Unexpected fetch: ${path}`));
  });

  renderAlertsTable([
    {
      ...baseAlert,
      alert_type: "pfsense_firewall_noisy_source",
      source: "pfsense",
      source_type: "firewall",
      operational_history: { is_pre_tuning: true, label: "Pre-Tuning" },
      pfsense_quality: {
        why_fired_available: true,
        suppressed_rollup: true,
        cooldown: { active: true },
      },
    },
  ], jest.fn());

  expect(screen.getByText("Cooldown active")).toBeInTheDocument();
  expect(screen.getByText("Suppressed roll-up")).toBeInTheDocument();
  expect(screen.getByText("Pre-Tuning")).toBeInTheDocument();
});

test("renders bounded-page pagination controls without changing alert interactions", async () => {
  global.fetch = jest.fn((url) => {
    const path = String(url);
    if (path.endsWith("/alerts/101/response-log") || path.endsWith("/alerts/101/notes")) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve([]),
      });
    }
    return Promise.reject(new Error(`Unexpected fetch: ${path}`));
  });

  render(
    <AlertsTable
      alerts={[baseAlert]}
      canTakeAlertActions={true}
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
      selectedAlertId={null}
      setSelectedAlertId={() => {}}
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
      totalAlerts={120}
      pageOffset={50}
      pageLimit={50}
      pageEnd={100}
      canGoToPreviousPage={true}
      canGoToNextPage={true}
      onPreviousPage={jest.fn()}
      onNextPage={jest.fn()}
    />
  );

  expect(screen.getByText("Showing 51-100 of 120 · Page size 50")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Previous" })).toBeEnabled();
  expect(screen.getByRole("button", { name: "Next" })).toBeEnabled();
  expect(screen.getByText("failed_login_threshold")).toBeInTheDocument();
});
