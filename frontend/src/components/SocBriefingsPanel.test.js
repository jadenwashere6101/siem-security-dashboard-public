import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import SocBriefingsPanel from "./SocBriefingsPanel";
import {
  getSocBriefing,
  getSocBriefingControl,
  listSocBriefings,
  runSocBriefingNow,
  updateSocBriefingMode,
  updateSocBriefingPause,
} from "../services/socBriefingService";

jest.mock("../services/socBriefingService", () => ({
  getSocBriefing: jest.fn(),
  getSocBriefingControl: jest.fn(),
  listSocBriefings: jest.fn(),
  runSocBriefingNow: jest.fn(),
  updateSocBriefingMode: jest.fn(),
  updateSocBriefingPause: jest.fn(),
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
      run: { status: "success", provider_status: "local" },
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
  run: { status: "success", provider_status: "local", runtime_ms: 1234, service_actor: "scheduled_soc_briefing_worker" },
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

const controlPayload = {
  mode: "manual_only",
  schedules_paused: true,
  next_scheduled_run: { name: "Morning SOC briefing", next_due_at: "2026-07-28T08:00:00Z" },
  last_successful_run: { generated_at: "2026-07-27T08:02:00Z" },
  catch_up: { status: "paused", max_windows: 3, max_lookback_hours: 24, coalesce_missed_windows: true },
  active_jobs: { manual: { pending: 0, running: 0 }, scheduled: { pending: 0, running: 0 } },
  ai: {
    local_only: true,
    no_paid_fallback: true,
    gateway: { mode: "local_only", local_model: "llama3.1:8b" },
    local_provider: { provider: "ollama", ready: true, status: "success", model: "llama3.1:8b" },
  },
};

describe("SocBriefingsPanel", () => {
  beforeEach(() => {
    listSocBriefings.mockResolvedValue(listPayload);
    getSocBriefing.mockResolvedValue(detailPayload);
    getSocBriefingControl.mockResolvedValue(controlPayload);
    runSocBriefingNow.mockResolvedValue({ created: true, status: "queued", job: { id: 44 } });
    updateSocBriefingMode.mockResolvedValue({ ...controlPayload, mode: "scheduled_autonomous", schedules_paused: false });
    updateSocBriefingPause.mockResolvedValue({ ...controlPayload, schedules_paused: false });
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  test("renders history list, structured detail, and separate status badges", async () => {
    render(<SocBriefingsPanel />);

    expect(await screen.findByText("Morning SOC Briefings")).toBeInTheDocument();
    expect(screen.getByText("Read-only autonomous SOC agent")).toBeInTheDocument();
    expect(screen.getByText(/Anakin summarizes scheduled investigations/i)).toBeInTheDocument();
    expect(screen.getByText("Total Briefings")).toBeInTheDocument();
    expect(screen.getByText("Latest Briefing")).toBeInTheDocument();
    expect(screen.getAllByText("Next Scheduled Run").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Anakin Status")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run Anakin Briefing Now" })).toBeInTheDocument();
    await screen.findByText("llama3.1:8b");
    expect(screen.getByLabelText("Briefing mode")).toHaveValue("manual_only");
    await waitFor(() => expect(screen.getByLabelText("Pause schedules")).toBeChecked());
    expect(screen.getByText("No Paid Fallback: Completed")).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByText("Critical auth anomaly reviewed.").length).toBeGreaterThanOrEqual(1));
    expect(await screen.findByText("Executive Summary")).toBeInTheDocument();
    expect(screen.getByText("Critical Findings")).toBeInTheDocument();
    expect(screen.getByText("Investigation Metadata")).toBeInTheDocument();
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

  test("runs manual briefing and updates mode and pause controls", async () => {
    render(<SocBriefingsPanel />);

    await screen.findByText("Critical auth anomaly reviewed.");
    await userEvent.selectOptions(screen.getByLabelText("Briefing mode"), "scheduled_autonomous");
    await waitFor(() => expect(updateSocBriefingMode).toHaveBeenCalledWith("scheduled_autonomous"));

    await userEvent.click(screen.getByRole("button", { name: "Run Anakin Briefing Now" }));
    expect(await screen.findByText(/Anakin briefing queued/i)).toBeInTheDocument();
    expect(runSocBriefingNow).toHaveBeenCalledTimes(1);

    await userEvent.click(screen.getByLabelText("Pause schedules"));
    await waitFor(() => expect(updateSocBriefingPause).toHaveBeenCalledWith(false, ""));
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

  test("renders polished empty state and no-data summary values", async () => {
    listSocBriefings.mockResolvedValueOnce({ items: [], limit: 10, offset: 0, total: 0 });
    render(<SocBriefingsPanel />);

    expect(await screen.findByText(/Anakin's analyst summaries appear here/i)).toBeInTheDocument();
    expect(screen.getAllByText("No Data").length).toBeGreaterThanOrEqual(3);
    expect(screen.queryByText("Select a briefing")).not.toBeInTheDocument();
  });
});
