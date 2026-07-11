import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import IncidentsPanel from "./IncidentsPanel";
import {
  loadIncidentDetail,
  loadIncidentTimeline,
  loadIncidents,
  updateIncidentStatus,
} from "../services/incidentService";
import { listIncidentNotificationDeliveries } from "../services/notificationDeliveryService";

jest.mock("../services/incidentService", () => ({
  loadIncidents: jest.fn(),
  loadIncidentDetail: jest.fn(),
  loadIncidentTimeline: jest.fn(),
  updateIncidentStatus: jest.fn(),
}));

jest.mock("../services/notificationDeliveryService", () => ({
  listIncidentNotificationDeliveries: jest.fn(),
}));

const incidentFixture = {
  id: 7,
  title: "[AUTO] HIGH alert from 203.0.113.10",
  severity: "HIGH",
  priority: "P2",
  status: "open",
  source_ip: "203.0.113.10",
  assigned_to: null,
  created_at: "2026-05-07T12:00:00Z",
  resolved_at: null,
};

const incidentDetailFixture = {
  ...incidentFixture,
  alerts: [
    {
      alert_id: 42,
      alert_type: "failed_login_threshold",
      severity: "HIGH",
      source_ip: "203.0.113.10",
      status: "open",
      created_at: "2026-05-07T12:00:00Z",
      linked_at: "2026-05-07T12:01:00Z",
    },
  ],
};

const renderPanel = (props = {}) =>
  render(
    <IncidentsPanel
      cardStyle={{}}
      cardHeaderStyle={{}}
      cardTitleStyle={{}}
      cardSubtitleStyle={{}}
      filterLabelStyle={{}}
      selectStyle={{}}
      canTakeAlertActions
      {...props}
    />
  );

const deferred = () => {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
};

describe("IncidentsPanel", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    loadIncidentTimeline.mockResolvedValue({ timeline: [] });
    listIncidentNotificationDeliveries.mockResolvedValue({ items: [], limit: 50, offset: 0 });
  });

  test("shows loading state while incidents load", () => {
    const pending = deferred();
    loadIncidents.mockReturnValue(pending.promise);

    renderPanel();

    expect(screen.getByText("Loading incidents...")).toBeInTheDocument();
  });

  test("shows error state when incident list fails", async () => {
    loadIncidents.mockRejectedValue(new Error("load failed"));

    renderPanel();

    expect(await screen.findByText("Error: load failed")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  test("shows empty state when no incidents are returned", async () => {
    loadIncidents.mockResolvedValue({ incidents: [], count: 0 });

    renderPanel();

    expect(await screen.findByText("No incidents found.")).toBeInTheDocument();
  });

  test("renders incident list rows", async () => {
    loadIncidents.mockResolvedValue({ incidents: [incidentFixture], count: 1 });

    renderPanel();

    expect(await screen.findByText(incidentFixture.title)).toBeInTheDocument();
    expect(screen.getAllByText("HIGH").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Open").length).toBeGreaterThan(0);
    expect(screen.getByText("203.0.113.10")).toBeInTheDocument();
  });

  test("refetches when status filter changes", async () => {
    loadIncidents.mockResolvedValue({ incidents: [incidentFixture], count: 1 });

    renderPanel();
    await screen.findByText(incidentFixture.title);

    await userEvent.selectOptions(screen.getByLabelText("Status"), "resolved");

    await waitFor(() =>
      expect(loadIncidents).toHaveBeenCalledWith({
        status: "resolved",
        severity: "all",
      })
    );
  });

  test("row click loads incident detail", async () => {
    loadIncidents.mockResolvedValue({ incidents: [incidentFixture], count: 1 });
    loadIncidentDetail.mockResolvedValue({ incident: incidentDetailFixture });

    renderPanel();
    await screen.findByText(incidentFixture.title);
    await userEvent.click(screen.getByText(incidentFixture.title));

    await waitFor(() => expect(loadIncidentDetail).toHaveBeenCalledWith(7));
    await waitFor(() => expect(loadIncidentTimeline).toHaveBeenCalledWith(7));
    await waitFor(() =>
      expect(listIncidentNotificationDeliveries).toHaveBeenCalledWith(7, { limit: 50 })
    );
  });

  test("shows detail loading state", async () => {
    const pendingDetail = deferred();
    loadIncidents.mockResolvedValue({ incidents: [incidentFixture], count: 1 });
    loadIncidentDetail.mockReturnValue(pendingDetail.promise);

    renderPanel();
    await screen.findByText(incidentFixture.title);
    await userEvent.click(screen.getByText(incidentFixture.title));

    expect(screen.getByText("Loading incident...")).toBeInTheDocument();
  });

  test("shows detail error state", async () => {
    loadIncidents.mockResolvedValue({ incidents: [incidentFixture], count: 1 });
    loadIncidentDetail.mockRejectedValue(new Error("detail failed"));

    renderPanel();
    await screen.findByText(incidentFixture.title);
    await userEvent.click(screen.getByText(incidentFixture.title));

    expect(await screen.findByText("Error loading incident: detail failed")).toBeInTheDocument();
  });

  test("renders incident detail", async () => {
    loadIncidents.mockResolvedValue({ incidents: [incidentFixture], count: 1 });
    loadIncidentDetail.mockResolvedValue({ incident: incidentDetailFixture });

    renderPanel();
    await screen.findByText(incidentFixture.title);
    await userEvent.click(screen.getByText(incidentFixture.title));

    expect(await screen.findByText(/Incident #7/)).toBeInTheDocument();
    expect(screen.getAllByText("P2").length).toBeGreaterThan(0);
    expect(screen.getAllByText("203.0.113.10").length).toBeGreaterThan(0);
  });

  test("renders timeline loading state", async () => {
    const pendingTimeline = deferred();
    loadIncidents.mockResolvedValue({ incidents: [incidentFixture], count: 1 });
    loadIncidentDetail.mockResolvedValue({ incident: incidentDetailFixture });
    loadIncidentTimeline.mockReturnValue(pendingTimeline.promise);

    renderPanel();
    await screen.findByText(incidentFixture.title);
    await userEvent.click(screen.getByText(incidentFixture.title));

    expect(await screen.findByText("Loading timeline...")).toBeInTheDocument();
  });

  test("renders empty timeline state", async () => {
    loadIncidents.mockResolvedValue({ incidents: [incidentFixture], count: 1 });
    loadIncidentDetail.mockResolvedValue({ incident: incidentDetailFixture });
    loadIncidentTimeline.mockResolvedValue({ timeline: [] });

    renderPanel();
    await screen.findByText(incidentFixture.title);
    await userEvent.click(screen.getByText(incidentFixture.title));

    expect(
      await screen.findByText("No SOAR timeline events found for this incident.")
    ).toBeInTheDocument();
  });

  test("renders timeline entries with safe metadata only", async () => {
    loadIncidents.mockResolvedValue({ incidents: [incidentFixture], count: 1 });
    loadIncidentDetail.mockResolvedValue({ incident: incidentDetailFixture });
    loadIncidentTimeline.mockResolvedValue({
      timeline: [
        {
          timestamp: "2026-05-10T18:25:00Z",
          event_type: "playbook_step_completed",
          source: "playbook_execution",
          title: "Notify analyst",
          summary: "Simulated notification completed",
          metadata: {
            playbook_id: "pb_notify",
            execution_id: 123,
            simulated: true,
            webhook_url: "https://hooks.example.invalid/secret",
            raw_params: { token: "secret" },
            secret: "do-not-render",
          },
        },
        {
          timestamp: "2026-05-10T18:26:00Z",
          event_type: "custom_unknown_event",
          source: "audit_log",
          summary: "Custom audit event",
          metadata: {
            alert_id: 42,
          },
        },
      ],
    });

    renderPanel();
    await screen.findByText(incidentFixture.title);
    await userEvent.click(screen.getByText(incidentFixture.title));

    expect(await screen.findByText("Playbook step completed")).toBeInTheDocument();
    expect(screen.getByText("Notify analyst")).toBeInTheDocument();
    expect(screen.getByText("Simulated notification completed")).toBeInTheDocument();
    expect(screen.getByText("Playbook Execution")).toBeInTheDocument();
    expect(screen.getByText("playbook_id:")).toBeInTheDocument();
    expect(screen.getByText("pb_notify")).toBeInTheDocument();
    expect(screen.getByText("execution_id:")).toBeInTheDocument();
    expect(screen.getByText("123")).toBeInTheDocument();
    expect(screen.getByText("simulated:")).toBeInTheDocument();
    expect(screen.getByText("true")).toBeInTheDocument();
    expect(screen.getByText("Custom Unknown Event")).toBeInTheDocument();
    expect(screen.queryByText(/hooks\.example/)).not.toBeInTheDocument();
    expect(screen.queryByText("raw_params:")).not.toBeInTheDocument();
    expect(screen.queryByText("do-not-render")).not.toBeInTheDocument();
  });

  test("timeline errors do not clear incident detail and can retry", async () => {
    loadIncidents.mockResolvedValue({ incidents: [incidentFixture], count: 1 });
    loadIncidentDetail.mockResolvedValue({ incident: incidentDetailFixture });
    loadIncidentTimeline
      .mockRejectedValueOnce(new Error("timeline failed"))
      .mockResolvedValueOnce({
        timeline: [
          {
            timestamp: "2026-05-10T18:25:00Z",
            event_type: "approval_requested",
            source: "approval_request",
            summary: "Approval requested for simulated step",
          },
        ],
      });

    renderPanel();
    await screen.findByText(incidentFixture.title);
    await userEvent.click(screen.getByText(incidentFixture.title));

    expect(await screen.findByText(/Incident #7/)).toBeInTheDocument();
    expect(await screen.findByText("Error loading timeline: timeline failed")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Retry timeline" }));

    expect(await screen.findByText("Approval requested")).toBeInTheDocument();
    expect(screen.getByText("Approval requested for simulated step")).toBeInTheDocument();
    expect(loadIncidentTimeline).toHaveBeenCalledTimes(2);
  });

  test("renders incident notification delivery history with safe fields", async () => {
    loadIncidents.mockResolvedValue({ incidents: [incidentFixture], count: 1 });
    loadIncidentDetail.mockResolvedValue({ incident: incidentDetailFixture });
    listIncidentNotificationDeliveries.mockResolvedValue({
      items: [
        {
          id: 12,
          correlation_id: "incident-corr-12",
          provider: "slack",
          mode: "simulation",
          status: "success",
          incident_id: 7,
          adapter_name: "slack",
          action: "send_message",
          circuit_breaker_state: "closed",
          timeout_seconds: 30,
          failure_code: null,
          failure_message: null,
          requested_at: "2026-05-09T12:00:00Z",
          started_at: "2026-05-09T12:00:01Z",
          completed_at: "2026-05-09T12:00:02Z",
          created_at: "2026-05-09T12:00:02Z",
          metadata: {
            channel_label: "#soc",
            webhook_url: "https://hooks.example.invalid/secret",
            raw_payload: { token: "secret" },
          },
        },
      ],
      limit: 50,
      offset: 0,
    });

    renderPanel();
    await screen.findByText(incidentFixture.title);
    await userEvent.click(screen.getByText(incidentFixture.title));

    expect(await screen.findByText("Notification Delivery History")).toBeInTheDocument();
    expect(screen.getByText(/operational evidence only/i)).toBeInTheDocument();
    expect(screen.getByText(/does not prove that a human saw the message/i)).toBeInTheDocument();
    expect(screen.getByText("Delivery #12")).toBeInTheDocument();
    expect(screen.getByText("slack / simulation")).toBeInTheDocument();
    expect(screen.getByText("incident-corr-12")).toBeInTheDocument();
    expect(screen.getByText("send_message")).toBeInTheDocument();
    expect(screen.getAllByText(/^closed$/i).length).toBeGreaterThan(0);
    expect(screen.getByText("30")).toBeInTheDocument();
    expect(screen.getByText("Safe metadata")).toBeInTheDocument();
    expect(screen.getByText("#soc")).toBeInTheDocument();
    expect(screen.queryByText(/hooks\.example/)).not.toBeInTheDocument();
    expect(screen.queryByText(/raw_payload/i)).not.toBeInTheDocument();
  });

  test("renders failure metadata for incident notification deliveries", async () => {
    loadIncidents.mockResolvedValue({ incidents: [incidentFixture], count: 1 });
    loadIncidentDetail.mockResolvedValue({ incident: incidentDetailFixture });
    listIncidentNotificationDeliveries.mockResolvedValue({
      items: [
        {
          id: 13,
          correlation_id: "incident-corr-13",
          provider: "teams",
          mode: "real",
          status: "failed",
          adapter_name: "teams",
          action: "send_message",
          circuit_breaker_state: "open",
          timeout_seconds: null,
          failure_code: "network_error",
          failure_message: "bad https://hooks.example.invalid/secret",
          requested_at: "2026-05-09T12:00:00Z",
          started_at: null,
          completed_at: "2026-05-09T12:00:05Z",
          created_at: "2026-05-09T12:00:05Z",
          metadata: { provider_status: "down" },
        },
      ],
      limit: 50,
      offset: 0,
    });

    renderPanel();
    await screen.findByText(incidentFixture.title);
    await userEvent.click(screen.getByText(incidentFixture.title));

    expect(await screen.findByText("teams / real")).toBeInTheDocument();
    expect(screen.getByText("network_error")).toBeInTheDocument();
    expect(screen.getByText("[REDACTED_URL]")).toBeInTheDocument();
    expect(screen.getByText("provider_status")).toBeInTheDocument();
    expect(screen.getByText("down")).toBeInTheDocument();
    expect(screen.queryByText(/hooks\.example/)).not.toBeInTheDocument();
  });

  test("delivery errors do not clear incident detail or timeline", async () => {
    loadIncidents.mockResolvedValue({ incidents: [incidentFixture], count: 1 });
    loadIncidentDetail.mockResolvedValue({ incident: incidentDetailFixture });
    loadIncidentTimeline.mockResolvedValue({
      timeline: [
        {
          timestamp: "2026-05-10T18:25:00Z",
          event_type: "approval_requested",
          source: "approval_request",
          summary: "Approval requested for simulated step",
        },
      ],
    });
    listIncidentNotificationDeliveries
      .mockRejectedValueOnce(new Error("delivery failed"))
      .mockResolvedValueOnce({ items: [], limit: 50, offset: 0 });

    renderPanel();
    await screen.findByText(incidentFixture.title);
    await userEvent.click(screen.getByText(incidentFixture.title));

    expect(await screen.findByText(/Incident #7/)).toBeInTheDocument();
    expect(await screen.findByText("Approval requested")).toBeInTheDocument();
    expect(
      await screen.findByText("Error loading notification deliveries: delivery failed")
    ).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Retry deliveries" }));

    expect(
      await screen.findByText("No notification delivery attempts found for this incident.")
    ).toBeInTheDocument();
    expect(listIncidentNotificationDeliveries).toHaveBeenCalledTimes(2);
  });

  test("timeline section does not render mutation controls", async () => {
    loadIncidents.mockResolvedValue({ incidents: [incidentFixture], count: 1 });
    loadIncidentDetail.mockResolvedValue({ incident: incidentDetailFixture });
    loadIncidentTimeline.mockResolvedValue({
      timeline: [
        {
          timestamp: "2026-05-10T18:25:00Z",
          event_type: "playbook_adapter_simulated",
          source: "playbook_execution",
          summary: "Simulated adapter event",
          metadata: { adapter: "slack", simulated: true, executed: false },
        },
        {
          timestamp: "2026-05-10T18:26:00Z",
          event_type: "playbook_adapter_real",
          source: "playbook_execution",
          summary: "Slack real-mode notification sent.",
          metadata: { adapter: "slack", simulated: false, executed: true },
        },
      ],
    });

    renderPanel({ canTakeAlertActions: false });
    await screen.findByText(incidentFixture.title);
    await userEvent.click(screen.getByText(incidentFixture.title));

    expect(await screen.findByText("Simulated adapter step")).toBeInTheDocument();
    expect(await screen.findByText("Real adapter step")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Timeline is read-only. Each event's mode (internal, tracking-only, simulated, or real) is determined by the backend and shown per event."
      )
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Deny" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Resume" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Run" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cancel" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reset to Closed" })).not.toBeInTheDocument();
  });

  test("renders dash for null resolved_at", async () => {
    loadIncidents.mockResolvedValue({ incidents: [incidentFixture], count: 1 });
    loadIncidentDetail.mockResolvedValue({ incident: incidentDetailFixture });

    renderPanel();
    await screen.findByText(incidentFixture.title);
    await userEvent.click(screen.getByText(incidentFixture.title));

    expect(await screen.findByText("—")).toBeInTheDocument();
  });

  test("renders linked alerts", async () => {
    loadIncidents.mockResolvedValue({ incidents: [incidentFixture], count: 1 });
    loadIncidentDetail.mockResolvedValue({ incident: incidentDetailFixture });

    renderPanel();
    await screen.findByText(incidentFixture.title);
    await userEvent.click(screen.getByText(incidentFixture.title));

    expect(await screen.findByText("failed_login_threshold")).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument();
  });

  test("renders no linked alerts state", async () => {
    loadIncidents.mockResolvedValue({ incidents: [incidentFixture], count: 1 });
    loadIncidentDetail.mockResolvedValue({
      incident: { ...incidentDetailFixture, alerts: [] },
    });

    renderPanel();
    await screen.findByText(incidentFixture.title);
    await userEvent.click(screen.getByText(incidentFixture.title));

    expect(await screen.findByText("No linked alerts.")).toBeInTheDocument();
  });

  test("shows status update control for users who can act", async () => {
    loadIncidents.mockResolvedValue({ incidents: [incidentFixture], count: 1 });
    loadIncidentDetail.mockResolvedValue({ incident: incidentDetailFixture });

    renderPanel({ canTakeAlertActions: true });
    await screen.findByText(incidentFixture.title);
    await userEvent.click(screen.getByText(incidentFixture.title));

    expect(await screen.findByRole("button", { name: "Update Status" })).toBeInTheDocument();
    expect(screen.getByLabelText("Update status:")).toBeInTheDocument();
  });

  test("hides status update control when user cannot act", async () => {
    loadIncidents.mockResolvedValue({ incidents: [incidentFixture], count: 1 });
    loadIncidentDetail.mockResolvedValue({ incident: incidentDetailFixture });

    renderPanel({ canTakeAlertActions: false });
    await screen.findByText(incidentFixture.title);
    await userEvent.click(screen.getByText(incidentFixture.title));
    await screen.findByText(/Incident #7/);

    expect(screen.queryByRole("button", { name: "Update Status" })).not.toBeInTheDocument();
  });

  test("updates incident status and refreshes detail", async () => {
    loadIncidents.mockResolvedValue({ incidents: [incidentFixture], count: 1 });
    loadIncidentDetail.mockResolvedValue({ incident: incidentDetailFixture });
    updateIncidentStatus.mockResolvedValue({
      incident: { ...incidentDetailFixture, status: "investigating" },
    });

    renderPanel();
    await screen.findByText(incidentFixture.title);
    await userEvent.click(screen.getByText(incidentFixture.title));
    await screen.findByRole("button", { name: "Update Status" });

    await userEvent.selectOptions(screen.getByLabelText("Update status:"), "investigating");
    await userEvent.click(screen.getByRole("button", { name: "Update Status" }));

    await waitFor(() =>
      expect(updateIncidentStatus).toHaveBeenCalledWith(7, "investigating")
    );
    expect(loadIncidentDetail).toHaveBeenCalledTimes(2);
  });

  test("shows status update errors inline", async () => {
    loadIncidents.mockResolvedValue({ incidents: [incidentFixture], count: 1 });
    loadIncidentDetail.mockResolvedValue({ incident: incidentDetailFixture });
    updateIncidentStatus.mockRejectedValue(new Error("invalid status transition"));

    renderPanel();
    await screen.findByText(incidentFixture.title);
    await userEvent.click(screen.getByText(incidentFixture.title));
    await screen.findByRole("button", { name: "Update Status" });

    await userEvent.selectOptions(screen.getByLabelText("Update status:"), "closed");
    await userEvent.click(screen.getByRole("button", { name: "Update Status" }));

    expect(await screen.findByText("invalid status transition")).toBeInTheDocument();
  });

  test("closes detail panel", async () => {
    loadIncidents.mockResolvedValue({ incidents: [incidentFixture], count: 1 });
    loadIncidentDetail.mockResolvedValue({ incident: incidentDetailFixture });

    renderPanel();
    await screen.findByText(incidentFixture.title);
    const row = screen.getByText(incidentFixture.title).closest("tr");
    await userEvent.click(row);
    const detailHeading = await screen.findByText(/Incident #7/);
    expect(detailHeading).toHaveFocus();
    expect(row).toHaveAttribute("aria-selected", "true");
    expect(screen.getByLabelText("Incident list and selected incident detail")).toHaveClass(
      "master-detail-layout--open"
    );
    expect(screen.getByRole("complementary", { name: "Selected incident detail" })).toBeVisible();

    await userEvent.click(screen.getByRole("button", { name: "Close" }));

    expect(screen.queryByText(/Incident #7/)).not.toBeInTheDocument();
    expect(row).toHaveFocus();
  });
});
