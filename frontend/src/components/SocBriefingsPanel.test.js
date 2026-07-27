import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import SocBriefingsPanel from "./SocBriefingsPanel";
import { getSocBriefing, listSocBriefings } from "../services/socBriefingService";

jest.mock("../services/socBriefingService", () => ({
  getSocBriefing: jest.fn(),
  listSocBriefings: jest.fn(),
}));

const listPayload = {
  items: [
    {
      id: 1,
      summary: "Critical auth anomaly reviewed.",
      content_status: "ready",
      status: "success",
      generated_at: "2026-07-27T08:02:00Z",
      created_at: "2026-07-27T08:02:00Z",
      schedule: { name: "Morning SOC briefing" },
      delivery: { latest_status: "sent", attempt_count: 1 },
    },
  ],
  limit: 10,
  offset: 0,
  total: 1,
};

const detailPayload = {
  id: 1,
  summary: "Critical auth anomaly reviewed.",
  content_status: "ready",
  generated_at: "2026-07-27T08:02:00Z",
  created_at: "2026-07-27T08:02:00Z",
  schedule: { name: "Morning SOC briefing" },
  run: { status: "success" },
  sections: {
    alerts_reviewed: ["Alert #1001 reviewed"],
    dismissed_low_priority_findings: ["Known scanner dismissed"],
    escalations: ["Escalate auth anomaly"],
    critical_findings: ["Repeated admin failures"],
    evidence: ["alert:1001"],
    recommendations: ["Review source IP reputation"],
  },
  deliveries: [
    {
      id: 9,
      status: "sent",
      created_at: "2026-07-27T08:03:00Z",
      last_attempted_at: "2026-07-27T08:03:00Z",
      failure_code: null,
    },
  ],
};

describe("SocBriefingsPanel", () => {
  beforeEach(() => {
    listSocBriefings.mockResolvedValue(listPayload);
    getSocBriefing.mockResolvedValue(detailPayload);
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  test("renders history list, structured detail, and separate status badges", async () => {
    render(<SocBriefingsPanel />);

    expect(await screen.findByText("SOC Briefing History")).toBeInTheDocument();
    expect(await screen.findByText("Critical auth anomaly reviewed.")).toBeInTheDocument();
    expect(await screen.findByText("Alerts reviewed")).toBeInTheDocument();
    expect(screen.getByText("Critical findings")).toBeInTheDocument();
    expect(screen.getAllByText(/Content:/)[0]).toBeInTheDocument();
    expect(screen.getAllByText(/Slack:/)[0]).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /retry/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/approve/i)).not.toBeInTheDocument();
  });

  test("applies search and delivery filters through the service", async () => {
    render(<SocBriefingsPanel />);

    await screen.findByText("Critical auth anomaly reviewed.");
    await userEvent.type(screen.getByLabelText("Search briefings"), "auth");
    await userEvent.selectOptions(screen.getByLabelText("Slack delivery status"), "sent");

    await waitFor(() => {
      expect(listSocBriefings).toHaveBeenLastCalledWith(
        expect.objectContaining({
          search: "auth",
          delivery_status: "sent",
          limit: 10,
          offset: 0,
        })
      );
    });
  });

  test("renders degraded states without mutation controls", async () => {
    listSocBriefings.mockResolvedValueOnce({
      ...listPayload,
      items: [{ ...listPayload.items[0], content_status: "failed", delivery: { latest_status: "failed" } }],
    });
    getSocBriefing.mockResolvedValueOnce({
      ...detailPayload,
      content_status: "failed",
      error_code: "provider_timeout",
      error_message: "Provider timeout.",
      deliveries: [{ ...detailPayload.deliveries[0], status: "failed", failure_code: "timeout" }],
    });

    render(<SocBriefingsPanel />);

    expect(await screen.findByText(/provider_timeout/i)).toBeInTheDocument();
    expect(screen.getByText("timeout")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /retry/i })).not.toBeInTheDocument();
  });
});
