import React from "react";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import SocCommandCenter, {
  buildActivityFeed,
  deriveAttentionItems,
} from "./SocCommandCenter";
import { listApprovals } from "../services/approvalService";
import { getDeadLetterMetrics, getDeadLetters } from "../services/deadLetterService";
import {
  loadIncidentDetail,
  loadIncidentTimeline,
  loadIncidents,
} from "../services/incidentService";
import { getIntegrationStatus } from "../services/integrationService";
import {
  getApprovalMetrics,
  getIncidentMetrics,
  getNotificationDeliveryMetrics,
  getPlaybookMetrics,
  getPlaybookWorkerMetrics,
} from "../services/metricsService";
import {
  listIncidentNotificationDeliveries,
  listNotificationDeliveries,
} from "../services/notificationDeliveryService";
import { listPlaybookExecutions } from "../services/playbookService";
import {
  loadRecentSoarQueueItems,
  loadSoarQueueStatus,
} from "../services/soarQueueService";

jest.mock("../services/approvalService", () => ({
  listApprovals: jest.fn(),
}));

jest.mock("../services/deadLetterService", () => ({
  getDeadLetterMetrics: jest.fn(),
  getDeadLetters: jest.fn(),
}));

jest.mock("../services/incidentService", () => ({
  loadIncidentDetail: jest.fn(),
  loadIncidentTimeline: jest.fn(),
  loadIncidents: jest.fn(),
}));

jest.mock("../services/integrationService", () => ({
  getIntegrationStatus: jest.fn(),
}));

jest.mock("../services/metricsService", () => ({
  getApprovalMetrics: jest.fn(),
  getIncidentMetrics: jest.fn(),
  getNotificationDeliveryMetrics: jest.fn(),
  getPlaybookMetrics: jest.fn(),
  getPlaybookWorkerMetrics: jest.fn(),
}));

jest.mock("../services/notificationDeliveryService", () => ({
  listIncidentNotificationDeliveries: jest.fn(),
  listNotificationDeliveries: jest.fn(),
}));

jest.mock("../services/playbookService", () => ({
  listPlaybookExecutions: jest.fn(),
}));

jest.mock("../services/soarQueueService", () => ({
  loadRecentSoarQueueItems: jest.fn(),
  loadSoarQueueStatus: jest.fn(),
}));

jest.mock("./SourceIpContext", () => ({
  __esModule: true,
  default: ({ sourceIp }) => (
    <section data-testid="source-ip-context">
      <h3>Source-IP Context</h3>
      <p>{sourceIp}</p>
      <p>Mocked normalized source-IP context</p>
    </section>
  ),
}));

const incidentAlpha = {
  id: 7,
  title: "High-risk identity incident",
  severity: "HIGH",
  priority: "P2",
  status: "open",
  source_ip: "203.0.113.10",
  created_at: "2026-05-18T12:00:00Z",
};

const incidentBeta = {
  id: 8,
  title: "Webhook drift incident",
  severity: "MEDIUM",
  priority: "P3",
  status: "investigating",
  source_ip: "203.0.113.20",
  created_at: "2026-05-18T12:05:00Z",
};

function mockResolvedData() {
  loadIncidents.mockResolvedValue({ incidents: [incidentAlpha, incidentBeta], count: 2 });
  listPlaybookExecutions.mockResolvedValue({
    items: [
      {
        id: 41,
        incident_id: 7,
        playbook_id: "containment",
        status: "failed",
        created_at: "2026-05-18T12:08:00Z",
      },
      {
        id: 42,
        incident_id: 8,
        playbook_id: "triage",
        status: "running",
        created_at: "2026-05-18T12:07:00Z",
      },
    ],
  });
  listApprovals.mockResolvedValue({
    approvals: [
      {
        id: 11,
        incident_id: 7,
        action: "block_ip",
        status: "pending",
        created_at: "2026-05-18T12:06:00Z",
      },
    ],
  });
  getDeadLetters.mockResolvedValue({
    items: [
      {
        id: 21,
        incident_id: 7,
        failure_class: "adapter_timeout",
        source_type: "playbook_step",
        status: "open",
        retryable: true,
        created_at: "2026-05-18T12:04:00Z",
      },
    ],
  });
  listNotificationDeliveries.mockResolvedValue({
    items: [
      {
        id: 31,
        incident_id: 7,
        provider: "email",
        adapter_name: "email",
        mode: "simulation",
        status: "failed",
        failure_class: "transient_network_error",
        created_at: "2026-05-18T12:03:00Z",
      },
    ],
  });
  loadRecentSoarQueueItems.mockResolvedValue({
    items: [
      {
        id: 51,
        incident_id: 8,
        playbook_id: "triage",
        status: "running",
        created_at: "2026-05-18T12:02:00Z",
      },
    ],
  });
  getIncidentMetrics.mockResolvedValue({
    by_status: { open: 1, investigating: 1 },
    open_high_critical: 1,
    canonical_outcome_counts: {
      execution_mode: { observed: 2 },
      execution_state: { observed: 2 },
    },
  });
  getPlaybookMetrics.mockResolvedValue({
    by_status: { pending: 1, running: 1, awaiting_approval: 0, failed: 1 },
    stale_running_count: 1,
    canonical_outcome_counts: {
      execution_mode: { simulation: 4, real: 1 },
      execution_state: { succeeded: 3, awaiting_approval: 1 },
      external_executed: { true: 1, false: 4 },
      tracking_recorded: { false: 5 },
      simulated: { true: 4, false: 1 },
    },
  });
  getApprovalMetrics.mockResolvedValue({
    pending_count: 1,
    canonical_outcome_counts: {
      execution_mode: { simulation: 2 },
      execution_state: { awaiting_approval: 1, blocked: 1 },
    },
  });
  getDeadLetterMetrics.mockResolvedValue({ open: 1, retrying: 0 });
  getNotificationDeliveryMetrics.mockResolvedValue({
    recent: { failed: 1, timeout: 0, blocked: 0 },
    by_mode: { simulation: 8, real: 0 },
    canonical_outcome_counts: {
      execution_mode: { simulation: 8 },
      simulated: { true: 8 },
    },
  });
  getPlaybookWorkerMetrics.mockResolvedValue({
    daemon_health: { status: "healthy" },
    queue_depth: { active_total: 2 },
    running: { stale: 1 },
  });
  loadSoarQueueStatus.mockResolvedValue({
    counts: { pending: 1, running: 1, awaiting_approval: 0 },
  });
  getIntegrationStatus.mockResolvedValue({
    mode: "simulation",
    adapters: [
      { name: "email", mode_decision: "simulation", real_enabled: false },
      { name: "webhook", mode_decision: "simulation", real_enabled: false },
    ],
  });
  loadIncidentDetail.mockResolvedValue({
    incident: {
      ...incidentAlpha,
      assigned_to: "analyst1",
      alerts: [
        {
          alert_id: 99,
          alert_type: "failed_login_threshold",
          severity: "HIGH",
        },
        {
          alert_id: 100,
          alert_type: "application_exception_threshold",
          severity: "MEDIUM",
        },
      ],
    },
  });
  loadIncidentTimeline.mockResolvedValue({
    timeline: [
      {
        event_type: "playbook_started",
        created_at: "2026-05-18T12:09:00Z",
      },
    ],
  });
  listIncidentNotificationDeliveries.mockResolvedValue({
    items: [
      {
        id: 88,
        provider: "email",
        status: "failed",
      },
    ],
  });
}

function renderPanel(props = {}) {
  return render(
    <SocCommandCenter
      alerts={[]}
      userRole="analyst"
      currentUsername="analyst1"
      {...props}
    />
  );
}

describe("SocCommandCenter", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockResolvedData();
  });

  test("renders summary cards and simulation-safe integration state", async () => {
    renderPanel();

    expect(screen.getByText("Operational command center")).toBeInTheDocument();

    expect(await screen.findByText("Incident pressure")).toBeInTheDocument();
    expect(screen.getByText("Active automations")).toBeInTheDocument();
    expect(screen.getAllByText("Pending approvals").length).toBeGreaterThan(0);
    expect(screen.getByText("Dead-letter pressure")).toBeInTheDocument();
    expect(screen.getByText("Notification health")).toBeInTheDocument();
    expect(screen.getByText("Worker health")).toBeInTheDocument();
    expect(screen.getByText("Integration safety")).toBeInTheDocument();
    expect(screen.getAllByText("Simulation-Safe Execution").length).toBeGreaterThan(0);
    expect(screen.getByText("Execution Safety Model")).toBeInTheDocument();
    expect(screen.getByText("Alert ingestion")).toBeInTheDocument();
    expect(screen.getByText("Detection/correlation")).toBeInTheDocument();
    expect(screen.getByText("Playbook orchestration")).toBeInTheDocument();
    expect(screen.getByText("Approvals/retry/dead letters")).toBeInTheDocument();
    expect(screen.getByText("Slack/Teams/Email/Webhook")).toBeInTheDocument();
    expect(screen.getByText("Firewall/block_ip")).toBeInTheDocument();
    expect(screen.getAllByText("Real Workflow").length).toBeGreaterThanOrEqual(4);
    expect(screen.getByText("Guarded Real-Capable")).toBeInTheDocument();
    expect(screen.getByText("Dry-Run Only")).toBeInTheDocument();
  });

  test("uses read-only services and never calls mutation endpoints", async () => {
    renderPanel();

    await waitFor(() => expect(loadIncidents).toHaveBeenCalledWith({ limit: 12 }));
    expect(listPlaybookExecutions).toHaveBeenCalledWith({ limit: 12 });
    expect(listApprovals).toHaveBeenCalledWith({ limit: 12 });
    expect(getDeadLetters).toHaveBeenCalledWith({ limit: 12 });
    expect(listNotificationDeliveries).toHaveBeenCalledWith({ limit: 12 });
    expect(getIntegrationStatus).toHaveBeenCalled();
  });

  test("renders global activity feed newest-first with bounded operational sources", async () => {
    renderPanel();

    const feed = await screen.findByRole("heading", { name: "Live operations feed" });
    const feedSection = feed.closest("section");
    const text = feedSection.textContent;

    expect(text.indexOf("containment")).toBeLessThan(text.indexOf("Block Ip"));
    expect(within(feedSection).getByText("Notification")).toBeInTheDocument();
    expect(within(feedSection).getByText("Dead letter")).toBeInTheDocument();
    expect(within(feedSection).getByText("Worker")).toBeInTheDocument();
  });

  test("isolates partial source failures without blanking the console", async () => {
    getIntegrationStatus.mockRejectedValue(new Error("integration unavailable"));

    renderPanel();

    expect((await screen.findAllByText("High-risk identity incident")).length).toBeGreaterThan(0);
    expect(screen.getByRole("status")).toHaveTextContent("integration status");
    expect(screen.getByText("Integration status is unavailable or no adapters are registered.")).toBeInTheDocument();
  });

  test("loads incident context and changes selected incident", async () => {
    renderPanel();

    expect((await screen.findAllByText("High-risk identity incident")).length).toBeGreaterThan(0);
    await waitFor(() => expect(loadIncidentDetail).toHaveBeenCalledWith(7));
    expect(await screen.findByText("failed_login_threshold")).toBeInTheDocument();
    expect(screen.getByText("playbook_started")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /webhook drift incident/i }));
    await waitFor(() => expect(loadIncidentDetail).toHaveBeenCalledWith(8));
  });

  test("wraps long linked alert names without truncating them", async () => {
    renderPanel();

    expect((await screen.findAllByText("High-risk identity incident")).length).toBeGreaterThan(0);
    const linkedAlertName = await screen.findByText("application_exception_threshold");

    expect(linkedAlertName).toBeInTheDocument();
    expect(screen.queryByText("application_exception_threshol")).not.toBeInTheDocument();
    expect(linkedAlertName).toHaveStyle({
      whiteSpace: "normal",
      overflowWrap: "anywhere",
      wordBreak: "break-word",
    });
  });

  test("opens and closes source-IP context drawer from selected incident source", async () => {
    renderPanel();

    expect((await screen.findAllByText("High-risk identity incident")).length).toBeGreaterThan(0);
    await waitFor(() => expect(loadIncidentDetail).toHaveBeenCalledWith(7));

    const sourceIpButton = await screen.findByRole("button", {
      name: "Open source-IP context for 203.0.113.10",
    });
    expect(sourceIpButton).toHaveTextContent("203.0.113.10");

    await userEvent.click(sourceIpButton);

    const drawer = screen.getByRole("dialog", { name: "Source-IP Context" });
    expect(within(drawer).getAllByRole("heading", { name: "Source-IP Context" }).length).toBeGreaterThan(0);
    expect(within(drawer).getByTestId("source-ip-context")).toBeInTheDocument();
    expect(within(drawer).getByText("203.0.113.10")).toBeInTheDocument();
    expect(within(drawer).getByText("Mocked normalized source-IP context")).toBeInTheDocument();

    await userEvent.click(within(drawer).getByRole("button", { name: "Close source-IP context drawer" }));

    expect(screen.queryByRole("dialog", { name: "Source-IP Context" })).not.toBeInTheDocument();
  });

  test("renders empty states for sparse API data", async () => {
    loadIncidents.mockResolvedValue({ incidents: [], count: 0 });
    listPlaybookExecutions.mockResolvedValue({ items: [] });
    listApprovals.mockResolvedValue({ approvals: [] });
    getDeadLetters.mockResolvedValue({ items: [] });
    listNotificationDeliveries.mockResolvedValue({ items: [] });
    loadRecentSoarQueueItems.mockResolvedValue({ items: [] });
    getIntegrationStatus.mockResolvedValue({ mode: "simulation", adapters: [] });

    renderPanel();

    expect(await screen.findByText("No incidents available.")).toBeInTheDocument();
    expect(screen.getByText("No recent operational activity found.")).toBeInTheDocument();
    expect(screen.getByText("Integration status is unavailable or no adapters are registered.")).toBeInTheDocument();
  });

  test("keeps viewer and auditor roles out of operational controls", () => {
    renderPanel({ userRole: "viewer" });

    expect(screen.getByText(/Viewer and auditor roles/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Refresh" })).not.toBeInTheDocument();
    expect(loadIncidents).not.toHaveBeenCalled();
  });

  test("renders without crashing on narrow viewport assumptions", async () => {
    const originalWidth = window.innerWidth;
    Object.defineProperty(window, "innerWidth", {
      configurable: true,
      writable: true,
      value: 640,
    });
    window.dispatchEvent(new Event("resize"));

    renderPanel();

    expect(await screen.findByText("Live operations feed")).toBeInTheDocument();
    expect(screen.getByText("Selected incident")).toBeInTheDocument();

    Object.defineProperty(window, "innerWidth", {
      configurable: true,
      writable: true,
      value: originalWidth,
    });
  });

  test("shows guarded real-mode indicator without exposing secret payloads", async () => {
    getIntegrationStatus.mockResolvedValue({
      mode: "real",
      adapters: [
        {
          name: "email",
          mode_decision: "real-enabled",
          real_enabled: true,
          smtp_password: "super-secret-password",
          webhook_url: "https://hooks.example.invalid/secret",
        },
      ],
    });

    const { container } = renderPanel();

    await waitFor(() => {
      expect(screen.getAllByText("Guarded Real-Capable").length).toBeGreaterThanOrEqual(3);
    });
    expect(container).not.toHaveTextContent("super-secret-password");
    expect(container).not.toHaveTextContent("hooks.example.invalid/secret");
    expect(container).not.toHaveTextContent(/global.*toggle/i);
    expect(container).not.toHaveTextContent(/fake/i);
  });

  test("renders canonical SOAR outcome counts without standalone Executed label", async () => {
    renderPanel();

    expect(await screen.findByLabelText("Canonical SOAR outcome counts")).toBeInTheDocument();
    expect(screen.getAllByText("Simulated").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Real executed").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Awaiting approval").length).toBeGreaterThan(0);
    expect(screen.queryByText(/^Executed$/)).not.toBeInTheDocument();
  });

  test("renders incident workspace response outcome summary and no-history state", async () => {
    loadIncidentDetail.mockResolvedValue({
      incident: {
        ...incidentAlpha,
        assigned_to: "analyst1",
        response_outcome: {
          execution_mode: "simulation",
          execution_state: "succeeded",
          simulated: true,
          external_executed: false,
          tracking_recorded: false,
          selected_action: "block_ip",
          decision_source: "manual",
          outcome_summary: "Simulation completed without enforcement.",
        },
        alerts: [
          {
            alert_id: 99,
            alert_type: "failed_login_threshold",
            severity: "HIGH",
          },
        ],
      },
    });

    renderPanel();

    expect((await screen.findAllByText("High-risk identity incident")).length).toBeGreaterThan(0);
    await waitFor(() => {
      expect(screen.getByText("Simulation completed without enforcement.")).toBeInTheDocument();
    });
    expect(screen.getAllByText("Simulated").length).toBeGreaterThan(0);

    loadIncidentDetail.mockResolvedValue({
      incident: {
        ...incidentBeta,
        assigned_to: "analyst1",
        response_outcome: null,
        alerts: [],
      },
    });

    await userEvent.click(screen.getByRole("button", { name: /webhook drift incident/i }));
    expect(await screen.findByText("No response outcome recorded.")).toBeInTheDocument();
  });

  test("exports helper behavior for activity and attention derivation", () => {
    const feed = buildActivityFeed({
      incidents: [incidentAlpha],
      executions: [{ id: 1, playbook_id: "alpha", status: "failed", created_at: "2026-05-18T12:20:00Z" }],
      approvals: [],
      deadLetters: [],
      notifications: [],
      queueItems: [],
    });
    const attention = deriveAttentionItems({
      playbookMetrics: { by_status: { failed: 2 }, stale_running_count: 1 },
      approvalMetrics: { pending_count: 3 },
      deadLetterMetrics: { open: 1, retrying: 1 },
      notificationMetrics: { recent: { failed: 1 } },
      workerMetrics: { queue_depth: { active_total: 4 } },
      queueStatus: {},
      integrationStatus: { adapters: [] },
      executions: [],
      notifications: [],
    });

    expect(feed[0].title).toBe("alpha");
    expect(attention.find((item) => item.label === "Pending approvals").value).toBe(3);
    expect(attention.find((item) => item.label === "Open or retrying dead letters").value).toBe(2);
  });
});
