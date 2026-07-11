import { render, screen } from "@testing-library/react";

import AlertExpandedRow from "./AlertExpandedRow";

const baseAlert = {
  id: 101,
  alert_type: "failed_login_threshold",
  source: "bank_app",
  source_type: "custom",
  source_ip: "8.8.8.8",
  severity: "high",
  status: "open",
  message: "Failed login threshold exceeded",
  response_action: "block_ip",
  response_status: "success",
  created_at: "2026-06-16T12:00:00Z",
  behavioral_reputation: {
    score: 0,
    label: "Normal",
    source: "siem_internal",
    summary: "No elevated behavioral signals observed in SIEM history.",
    contributing_signals: [],
  },
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

const renderExpandedRow = (alert) =>
  render(
    <table>
      <tbody>
        <AlertExpandedRow
          alert={alert}
          sourceBadge={{ label: "Bank App", style: {} }}
          correlationAlert={false}
          targetedAlertMeta={null}
          correlatedAlertTypes={[]}
          responseLog={[]}
          expandedCellStyle={{}}
          expandedContentStyle={{}}
          expandedLabelStyle={{}}
          expandedTextStyle={{}}
          monoCellStyle={{}}
          canTakeAlertActions={true}
          downloadPdfReport={() => {}}
          executeAction={() => {}}
          executingActionId={null}
          getActionButtonStyle={(style) => style}
          getReputationBadgeStyle={() => ({})}
        />
      </tbody>
    </table>
  );

test("AlertExpandedRow renders canonical response outcome badge for non-null outcome", () => {
  renderExpandedRow({
    ...baseAlert,
    response_status: "pending",
    response_outcome: trackingOutcome,
  });

  expect(screen.getByText("Response Outcome:")).toBeInTheDocument();
  expect(screen.getAllByText("Tracking only").length).toBeGreaterThan(0);
  expect(screen.getByLabelText(/mode tracking_only/i)).toBeInTheDocument();
  expect(screen.getByText("Response Action:")).toBeInTheDocument();
  expect(screen.queryByText("Response Status:")).not.toBeInTheDocument();
  expect(screen.queryByText(/^pending$/i)).not.toBeInTheDocument();
});

test("AlertExpandedRow prefers terminal outcome over stale legacy pending status", () => {
  const terminalSimulated = {
    ...trackingOutcome,
    execution_mode: "simulation",
    execution_state: "succeeded",
    tracking_recorded: false,
    simulated: true,
    reason_code: "simulation_mode",
    outcome_summary: "Playbook simulation completed.",
  };
  renderExpandedRow({
    ...baseAlert,
    response_status: "pending",
    response_outcome: terminalSimulated,
  });

  expect(screen.getAllByText("Simulated").length).toBeGreaterThan(0);
  expect(screen.queryByText("Response Status:")).not.toBeInTheDocument();
  expect(screen.getByTestId("response-state-summary")).toHaveTextContent("Simulated");
  expect(screen.getByTestId("response-state-summary")).not.toHaveTextContent("Pending approval");
});

test("AlertExpandedRow renders no-history badge for null response outcome", () => {
  renderExpandedRow({ ...baseAlert, response_outcome: null });

  expect(screen.getByText("Observed only")).toBeInTheDocument();
  expect(screen.getByLabelText(/no canonical outcome recorded/i)).toBeInTheDocument();
});
