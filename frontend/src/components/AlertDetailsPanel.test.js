import { render, screen } from "@testing-library/react";

import AlertDetailsPanel from "./AlertDetailsPanel";
import { loadPfsenseWhyFired } from "../services/pfsenseAlertInvestigationService";
import { loadSourceIpContext } from "../services/sourceIpContextService";

jest.mock("../services/sourceIpContextService", () => ({
  loadSourceIpContext: jest.fn(),
}));

jest.mock("../services/pfsenseAlertInvestigationService", () => ({
  loadPfsenseWhyFired: jest.fn(),
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
  loadPfsenseWhyFired.mockReset();
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
  loadPfsenseWhyFired.mockResolvedValue({
    alert_id: 101,
    rule_id: "pfsense_firewall_repeated_deny",
    summary: "Repeated deny threshold exceeded",
    evidence: [
      { field: "event_count", label: "Matching events", value: 6 },
      { field: "destination_port", label: "Destination port", value: 22 },
    ],
    suppressed_rollup: false,
    cooldown: {
      active: true,
      cooldown_until: "2026-07-13T14:10:00+00:00",
    },
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

test("AlertDetailsPanel renders pfSense why-fired evidence from the backend", async () => {
  render(
    <AlertDetailsPanel
      selectedAlert={{
        ...selectedAlert,
        alert_type: "pfsense_firewall_repeated_deny",
        source: "pfsense",
        source_type: "firewall",
        pfsense_quality: {
          why_fired_available: true,
          suppressed_rollup: false,
          cooldown: { active: true },
        },
      }}
      selectedAlertTimeline={[]}
      getSourceBadgeMeta={() => ({ label: "pfSense", style: {} })}
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

  expect(await screen.findByText("Why this fired")).toBeInTheDocument();
  expect(await screen.findByText("Repeated deny threshold exceeded")).toBeInTheDocument();
  expect(screen.getByText("Matching events")).toBeInTheDocument();
  expect(screen.getByText("6")).toBeInTheDocument();
  expect(screen.getByText("Cooldown active until 2026-07-13T14:10:00+00:00")).toBeInTheDocument();
  expect(loadPfsenseWhyFired).toHaveBeenCalledWith(101);
});

test("AlertDetailsPanel renders single-target pfSense target context", () => {
  render(
    <AlertDetailsPanel
      selectedAlert={{
        ...selectedAlert,
        alert_type: "pfsense_firewall_repeated_deny",
        context: {
          target_context: {
            mode: "exact_target",
            destination_ip: "203.0.113.10",
            destination_port: 22,
            primary_destination_ip: "203.0.113.10",
            primary_destination_port: 22,
            sample_destination_ips: ["203.0.113.10"],
            sample_destination_ports: [22],
            distinct_destination_count: 1,
            distinct_port_count: 1,
            protocol: "tcp",
            firewall_action: "block",
            attempts: 6,
            first_seen: "2026-07-13T14:00:00Z",
            last_seen: "2026-07-13T14:09:00Z",
            interface: "wan",
            direction: "out",
          },
        },
      }}
      selectedAlertTimeline={[]}
      getSourceBadgeMeta={() => ({ label: "pfSense", style: {} })}
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

  expect(screen.getByText("Target Context")).toBeInTheDocument();
  expect(screen.getByText("Exact destination evidence captured for this alert.")).toBeInTheDocument();
  expect(screen.getByText("Primary Destination IP")).toBeInTheDocument();
  expect(screen.getAllByText("203.0.113.10").length).toBeGreaterThan(0);
  expect(screen.getByText("LAN to WAN (outbound)")).toBeInTheDocument();
});

test("AlertDetailsPanel renders aggregate pfSense target context", () => {
  render(
    <AlertDetailsPanel
      selectedAlert={{
        ...selectedAlert,
        alert_type: "pfsense_firewall_port_scan",
        message: "Scanned port 443 across 5 public IPs.",
        context: {
          target_context: {
            mode: "aggregate_sample",
            top_destination_ip: "203.0.113.20",
            top_destination_port: 443,
            primary_destination_ip: "203.0.113.20",
            primary_destination_port: 443,
            sample_destination_ips: ["203.0.113.20", "203.0.113.21"],
            sample_destination_ports: [443, 3389],
            distinct_destination_count: 5,
            distinct_port_count: 2,
            firewall_action: "block",
            attempts: 7,
            first_seen: "2026-07-13T14:00:00Z",
            last_seen: "2026-07-13T14:09:00Z",
          },
          recon_activity: {
            id: 901,
            label: "Distributed Internet Reconnaissance Activity",
            coordination_status: "not_established",
          },
        },
      }}
      selectedAlertTimeline={[]}
      getSourceBadgeMeta={() => ({ label: "pfSense", style: {} })}
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

  expect(screen.getByText("Bounded aggregate target evidence from the detection window.")).toBeInTheDocument();
  expect(screen.getByText("Scanned port 443 across 5 public IPs.")).toBeInTheDocument();
  expect(screen.getByText("Primary Destination IP")).toBeInTheDocument();
  expect(screen.getByText("203.0.113.20")).toBeInTheDocument();
  expect(screen.getByText("Distinct Destinations")).toBeInTheDocument();
  expect(screen.getByText("5")).toBeInTheDocument();
  expect(screen.getByText("Recon campaign context")).toBeInTheDocument();
  expect(screen.getByText("#901")).toBeInTheDocument();
});

test("AlertDetailsPanel renders unavailable when pfSense target evidence is missing", () => {
  render(
    <AlertDetailsPanel
      selectedAlert={{
        ...selectedAlert,
        alert_type: "pfsense_firewall_noisy_source",
        context: {},
      }}
      selectedAlertTimeline={[]}
      getSourceBadgeMeta={() => ({ label: "pfSense", style: {} })}
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

  expect(screen.getByText("Target Context")).toBeInTheDocument();
  expect(screen.getByText("Unavailable")).toBeInTheDocument();
});

test("AlertDetailsPanel does not render target context for non-pfSense alerts", () => {
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

  expect(screen.queryByText("Target Context")).not.toBeInTheDocument();
});
