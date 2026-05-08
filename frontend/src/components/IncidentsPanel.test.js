import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import IncidentsPanel from "./IncidentsPanel";
import {
  loadIncidentDetail,
  loadIncidents,
  updateIncidentStatus,
} from "../services/incidentService";

jest.mock("../services/incidentService", () => ({
  loadIncidents: jest.fn(),
  loadIncidentDetail: jest.fn(),
  updateIncidentStatus: jest.fn(),
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
    await userEvent.click(screen.getByText(incidentFixture.title));
    expect(await screen.findByText(/Incident #7/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Close" }));

    expect(screen.queryByText(/Incident #7/)).not.toBeInTheDocument();
  });
});
