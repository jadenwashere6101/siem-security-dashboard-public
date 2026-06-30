import { render, screen } from "@testing-library/react";

import AlertDetailsPanel from "./AlertDetailsPanel";
import { loadSourceIpContext } from "../services/sourceIpContextService";

jest.mock("../services/sourceIpContextService", () => ({
  loadSourceIpContext: jest.fn(),
}));

const selectedAlert = {
  id: 101,
  alert_type: "failed_login_threshold",
  source_ip: "8.8.8.8",
  source: "bank_app",
  source_type: "custom",
  severity: "high",
  status: "open",
  message: "Failed login threshold exceeded",
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
};

const trackingOutcome = {
  decision_id: 10,
  alert_id: 101,
  queue_id: 202,
  playbook_execution_id: 303,
  approval_request_id: 404,
  notification_delivery_attempt_id: 505,
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

beforeEach(() => {
  loadSourceIpContext.mockReset();
  loadSourceIpContext.mockResolvedValue({
    source_ip: "8.8.8.8",
    alerts: { counts: { total: 1, open: 1, resolved: 0 }, recent: [] },
    incidents: { count: 0, recent: [] },
    queue: { counts: { total: 0, by_status: {} }, recent: [] },
    blocklist: { effective_status: "none", entries: [] },
    reputation: {
      behavioral: { score: 0, label: "Normal", summary: "No elevated behavioral signals observed in SIEM history." },
      latest_external: null,
      external_snapshots: [],
    },
    playbook_executions: { count: 0, recent: [] },
  });
});

test("AlertDetailsPanel includes source-IP context for selected alert", async () => {
  render(
    <AlertDetailsPanel
      selectedAlert={selectedAlert}
      selectedAlertTimeline={[]}
      getSourceBadgeMeta={() => ({ label: "Bank App", style: {} })}
      getTargetedAlertMeta={() => null}
      isCorrelationAlert={() => false}
      getCorrelationAlertTypes={() => []}
      correlationPanelStyle={{}}
      targetedAlertPanelStyle={{}}
      expandedLabelStyle={{}}
      expandedTextStyle={{}}
      monoCellStyle={{}}
      correlationListStyle={{}}
      signalRowStyle={{}}
      sourceTypeTextStyle={{}}
    />
  );

  expect(screen.getByText("Source-IP Context")).toBeInTheDocument();
  expect(await screen.findByText("Alerts")).toBeInTheDocument();
  expect(loadSourceIpContext).toHaveBeenCalledWith("8.8.8.8");
});

test("AlertDetailsPanel renders canonical response outcome summary", async () => {
  render(
    <AlertDetailsPanel
      selectedAlert={{ ...selectedAlert, response_outcome: trackingOutcome }}
      selectedAlertTimeline={[]}
      getSourceBadgeMeta={() => ({ label: "Bank App", style: {} })}
      getTargetedAlertMeta={() => null}
      isCorrelationAlert={() => false}
      getCorrelationAlertTypes={() => []}
      correlationPanelStyle={{}}
      targetedAlertPanelStyle={{}}
      expandedLabelStyle={{}}
      expandedTextStyle={{}}
      monoCellStyle={{}}
      correlationListStyle={{}}
      signalRowStyle={{}}
      sourceTypeTextStyle={{}}
    />
  );

  expect(screen.getByText("Response Outcome:")).toBeInTheDocument();
  expect(screen.getByText("Tracking only")).toBeInTheDocument();
  expect(screen.getByText("Block Ip")).toBeInTheDocument();
  expect(screen.getAllByText("Manual")).toHaveLength(2);
  expect(screen.getByText("Tracking-only record created")).toBeInTheDocument();
  expect(screen.getByText("Recorded in SIEM blocklist.")).toBeInTheDocument();
  expect(screen.getByText("Notification delivery id")).toBeInTheDocument();
});

test("AlertDetailsPanel renders no-history response outcome summary", () => {
  render(
    <AlertDetailsPanel
      selectedAlert={{ ...selectedAlert, response_outcome: null }}
      selectedAlertTimeline={[]}
      getSourceBadgeMeta={() => ({ label: "Bank App", style: {} })}
      getTargetedAlertMeta={() => null}
      isCorrelationAlert={() => false}
      getCorrelationAlertTypes={() => []}
      correlationPanelStyle={{}}
      targetedAlertPanelStyle={{}}
      expandedLabelStyle={{}}
      expandedTextStyle={{}}
      monoCellStyle={{}}
      correlationListStyle={{}}
      signalRowStyle={{}}
      sourceTypeTextStyle={{}}
    />
  );

  expect(screen.getByText("No response outcome recorded.")).toBeInTheDocument();
});
