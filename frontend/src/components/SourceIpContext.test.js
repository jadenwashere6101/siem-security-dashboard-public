import { render, screen, waitFor } from "@testing-library/react";

import SourceIpContext from "./SourceIpContext";
import { loadSourceIpContext } from "../services/sourceIpContextService";

jest.mock("../services/sourceIpContextService", () => ({
  loadSourceIpContext: jest.fn(),
}));

const contextResponse = {
  source_ip: "8.8.8.8",
  generated_at: "2026-06-16T12:00:00Z",
  limits: {
    alerts: 10,
    incidents: 10,
    queue: 10,
    playbook_executions: 10,
    external_reputation_snapshots: 5,
  },
  alerts: {
    counts: { total: 2, open: 1, resolved: 1 },
    recent: [
      {
        id: 101,
        alert_type: "failed_login_threshold",
        severity: "high",
        status: "open",
        response_status: "pending",
      },
    ],
  },
  incidents: {
    count: 1,
    recent: [
      {
        id: 7,
        title: "Source context incident",
        severity: "high",
        status: "investigating",
      },
    ],
  },
  queue: {
    counts: { total: 1, by_status: { awaiting_approval: 1 } },
    recent: [
      {
        id: 8,
        alert_id: 101,
        action: "block_ip",
        status: "awaiting_approval",
      },
    ],
  },
  blocklist: {
    effective_status: "expired",
    entries: [
      {
        id: 9,
        ip_address: "8.8.8.8",
        raw_status: "active",
        effective_status: "expired",
      },
    ],
  },
  reputation: {
    behavioral: {
      score: 3,
      label: "Low Suspicion",
      source: "siem_internal",
      summary: "Multiple failed login attempts",
      contributing_signals: [],
    },
    latest_external: {
      alert_id: 101,
      score: 91,
      label: "known_bad",
      source: "abuseipdb",
      summary: "Stored external snapshot",
    },
    external_snapshots: [
      {
        alert_id: 101,
        score: 91,
        label: "known_bad",
        source: "abuseipdb",
        summary: "Stored external snapshot",
      },
    ],
  },
  playbook_executions: {
    count: 1,
    recent: [
      {
        id: 11,
        playbook_id: "source_ip_context_contract_pb",
        alert_id: 101,
        status: "pending",
      },
    ],
  },
};

beforeEach(() => {
  loadSourceIpContext.mockReset();
});

test("SourceIpContext renders normalized response sections", async () => {
  loadSourceIpContext.mockResolvedValue(contextResponse);

  render(<SourceIpContext sourceIp="8.8.8.8" />);

  expect(screen.getByText("Loading source-IP context...")).toBeInTheDocument();
  expect(await screen.findByText("Alerts")).toBeInTheDocument();
  expect(screen.getByText("Incidents")).toBeInTheDocument();
  expect(screen.getByText("SOAR Queue")).toBeInTheDocument();
  expect(screen.getByText("Blocklist")).toBeInTheDocument();
  expect(screen.getByText("Reputation")).toBeInTheDocument();
  expect(screen.getByText("Playbook Executions")).toBeInTheDocument();
  expect(screen.getByText("Alert status: open")).toBeInTheDocument();
  expect(
    screen.getByText(/Legacy response status \(non-authoritative\):/)
  ).toBeInTheDocument();
  expect(screen.getByText("Incident status: investigating")).toBeInTheDocument();
  expect(screen.getByText("Queue execution status: awaiting_approval")).toBeInTheDocument();
  expect(screen.getByText("Blocklist effective status")).toBeInTheDocument();
  expect(screen.getByText("Execution status: pending")).toBeInTheDocument();
  expect(loadSourceIpContext).toHaveBeenCalledWith("8.8.8.8");
});

test("SourceIpContext handles empty source IP", () => {
  render(<SourceIpContext sourceIp="" />);

  expect(screen.getByText("No source IP selected.")).toBeInTheDocument();
  expect(loadSourceIpContext).not.toHaveBeenCalled();
});

test("SourceIpContext handles empty context sections", async () => {
  loadSourceIpContext.mockResolvedValue({
    ...contextResponse,
    alerts: { counts: { total: 0, open: 0, resolved: 0 }, recent: [] },
    incidents: { count: 0, recent: [] },
    queue: { counts: { total: 0, by_status: {} }, recent: [] },
    blocklist: { effective_status: "none", entries: [] },
    reputation: {
      behavioral: {
        score: 0,
        label: "Normal",
        summary: "No elevated behavioral signals observed in SIEM history.",
        contributing_signals: [],
      },
      latest_external: null,
      external_snapshots: [],
    },
    playbook_executions: { count: 0, recent: [] },
  });

  render(<SourceIpContext sourceIp="8.8.8.8" />);

  expect(await screen.findByText("No recent alerts")).toBeInTheDocument();
  expect(screen.getByText("No linked incidents")).toBeInTheDocument();
  expect(screen.getByText("No recent queue activity")).toBeInTheDocument();
  expect(screen.getByText("No blocklist entries")).toBeInTheDocument();
  expect(screen.getByText("No external reputation snapshots")).toBeInTheDocument();
  expect(screen.getByText("No linked playbook executions")).toBeInTheDocument();
});

test("SourceIpContext handles 403 permission responses", async () => {
  const error = new Error("forbidden");
  error.status = 403;
  loadSourceIpContext.mockRejectedValue(error);

  render(<SourceIpContext sourceIp="8.8.8.8" />);

  expect(await screen.findByText("Source-IP context unavailable for this role.")).toBeInTheDocument();
});

test("SourceIpContext handles general load errors", async () => {
  loadSourceIpContext.mockRejectedValue(new Error("network down"));

  render(<SourceIpContext sourceIp="8.8.8.8" />);

  await waitFor(() => {
    expect(screen.getByText("network down")).toBeInTheDocument();
  });
});

const outcomeFixture = {
  execution_mode: "simulation",
  execution_state: "succeeded",
  simulated: true,
  external_executed: false,
  tracking_recorded: false,
  outcome_summary: "Simulation completed without enforcement.",
};

test("SourceIpContext renders canonical outcome badge and summary", async () => {
  loadSourceIpContext.mockResolvedValue({
    ...contextResponse,
    response_outcomes: [outcomeFixture],
    response_outcome_counts: {
      execution_mode: { simulation: 1 },
      simulated: { true: 1 },
    },
  });

  render(<SourceIpContext sourceIp="8.8.8.8" />);

  expect(await screen.findByText("Canonical Outcomes")).toBeInTheDocument();
  expect(screen.getAllByText("Simulated").length).toBeGreaterThan(0);
  expect(screen.getByText("Simulation completed without enforcement.")).toBeInTheDocument();
  expect(screen.getByLabelText("Outcome counts for this source IP")).toBeInTheDocument();
});

test("SourceIpContext renders no-history state when no canonical outcomes exist", async () => {
  loadSourceIpContext.mockResolvedValue({
    ...contextResponse,
    response_outcomes: [],
    response_outcome_counts: null,
  });

  render(<SourceIpContext sourceIp="8.8.8.8" />);

  expect(
    await screen.findByText("No canonical response outcomes recorded for this source IP.")
  ).toBeInTheDocument();
  expect(screen.getByText("No canonical outcome counts recorded.")).toBeInTheDocument();
});

test("SourceIpContext renders multiple recent canonical outcomes", async () => {
  loadSourceIpContext.mockResolvedValue({
    ...contextResponse,
    response_outcomes: [
      outcomeFixture,
      {
        ...outcomeFixture,
        execution_mode: "tracking_only",
        tracking_recorded: true,
        simulated: false,
        outcome_summary: "Tracking-only record created.",
      },
    ],
    response_outcome_counts: {
      execution_mode: { simulation: 1, tracking_only: 1 },
    },
  });

  render(<SourceIpContext sourceIp="8.8.8.8" />);

  expect(await screen.findByText("Recent canonical outcomes")).toBeInTheDocument();
  expect(screen.getAllByText("Tracking only").length).toBeGreaterThan(0);
  expect(screen.getByText("Tracking-only record created.")).toBeInTheDocument();
});
