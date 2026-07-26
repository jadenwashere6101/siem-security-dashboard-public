import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import ReconWorkspace from "./ReconWorkspace";
import {
  loadReconActivities,
  loadReconActivity,
  loadReconActivityAlerts,
} from "../services/reconActivityService";

jest.mock("../services/reconActivityService", () => ({
  loadReconActivities: jest.fn(),
  loadReconActivity: jest.fn(),
  loadReconActivityAlerts: jest.fn(),
}));

const activity = {
  id: 90,
  label: "Distributed Internet Reconnaissance Activity",
  severity: "high",
  status: "open",
  protected_range_key: "203.0.113.0/24",
  last_seen: "2026-05-18T12:00:00Z",
  recon_intelligence: {
    classification: "campaign_recon",
    confidence: "high",
  },
  display: {
    headline: "Campaign-grade recon",
    target_summary: "203.0.113.44 (203.0.113.0/24)",
    representative_source: "198.51.100.10",
    primary_target: "203.0.113.44",
    linked_alert_count: 14,
  },
};

const detail = {
  ...activity,
  first_seen: "2026-05-18T10:30:00Z",
  related_incident_id: 7,
  assessment_text: "Campaign-grade evidence is present.",
  summary: {
    source_ip_count: 4,
  },
  recon_intelligence: {
    classification: "campaign_recon",
    confidence: "high",
    duration_minutes: 90,
    reasons: [{ id: "source_diversity", text: "4 contributing sources" }],
    missing_evidence: [{ id: "incident_correlation", text: "No active incident correlation is present" }],
  },
};

beforeEach(() => {
  jest.clearAllMocks();
  loadReconActivities.mockResolvedValue({ items: [activity], total: 24, limit: 20, offset: 0 });
  loadReconActivity.mockResolvedValue(detail);
  loadReconActivityAlerts.mockResolvedValue({
    items: [
      {
        id: 101,
        alert_type: "pfsense_firewall_port_scan",
        severity: "high",
        source_ip: "198.51.100.10",
        created_at: "2026-05-18T12:00:00Z",
      },
    ],
    total: 14,
    limit: 10,
    offset: 0,
  });
});

test("renders paginated recon history with filters, evidence, linked alerts, and pivots", async () => {
  const onViewRelatedAlerts = jest.fn();
  const onOpenIncident = jest.fn();

  render(<ReconWorkspace onViewRelatedAlerts={onViewRelatedAlerts} onOpenIncident={onOpenIncident} />);

  expect(await screen.findByText("Distributed recon history")).toBeInTheDocument();
  expect(await screen.findByText("Campaign-grade recon")).toBeInTheDocument();
  expect(await screen.findByText("4 contributing sources")).toBeInTheDocument();
  expect(screen.getAllByText("Campaign Recon").length).toBeGreaterThan(0);
  expect(screen.getAllByText("High confidence").length).toBeGreaterThan(0);
  expect(screen.getByText("#101 pfsense_firewall_port_scan")).toBeInTheDocument();

  await userEvent.selectOptions(screen.getByLabelText("Tier"), "campaign_recon");
  await waitFor(() =>
    expect(loadReconActivities).toHaveBeenLastCalledWith(expect.objectContaining({ classification: "campaign_recon" }))
  );

  await userEvent.type(screen.getByPlaceholderText("Source, target, service, assessment"), "203.0.113.44");
  await userEvent.click(screen.getByRole("button", { name: "Apply" }));
  await waitFor(() =>
    expect(loadReconActivities).toHaveBeenLastCalledWith(expect.objectContaining({ search: "203.0.113.44" }))
  );

  await userEvent.click(screen.getAllByRole("button", { name: "Next" })[0]);
  await waitFor(() =>
    expect(loadReconActivities).toHaveBeenLastCalledWith(expect.objectContaining({ offset: 20 }))
  );

  await userEvent.click(screen.getAllByRole("button", { name: "Next" })[1]);
  await waitFor(() =>
    expect(loadReconActivityAlerts).toHaveBeenLastCalledWith(90, expect.objectContaining({ offset: 10 }))
  );

  await userEvent.click(screen.getByRole("button", { name: "View alerts for source" }));
  expect(onViewRelatedAlerts).toHaveBeenCalledWith({ sourceIp: "198.51.100.10" });

  await userEvent.click(screen.getByRole("button", { name: "Open incident" }));
  expect(onOpenIncident).toHaveBeenCalledWith(7);
});
