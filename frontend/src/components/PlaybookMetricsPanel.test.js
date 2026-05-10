import React from "react";
import { render, screen, waitFor } from "@testing-library/react";

import PlaybookMetricsPanel from "./PlaybookMetricsPanel";
import { getPlaybookMetrics } from "../services/metricsService";

jest.mock("../services/metricsService", () => ({
  getPlaybookMetrics: jest.fn(),
}));

const styleProps = {
  cardStyle: {},
  cardHeaderStyle: {},
  cardTitleStyle: {},
  cardSubtitleStyle: {},
};

const fullPayload = {
  total_executions: 12,
  by_status: {
    pending: 2,
    running: 1,
    awaiting_approval: 1,
    success: 5,
    failed: 2,
    abandoned: 1,
  },
  by_playbook_id: [
    {
      playbook_id: "block_and_notify",
      total: 7,
      by_status: {
        pending: 1,
        running: 0,
        awaiting_approval: 0,
        success: 4,
        failed: 2,
        abandoned: 0,
      },
      other_status_count: 1,
    },
    {
      playbook_id: "monitor_only",
      total: 5,
      by_status: {
        pending: 1,
        running: 1,
        awaiting_approval: 1,
        success: 1,
        failed: 0,
        abandoned: 1,
      },
    },
  ],
  recent: {
    window_hours: 24,
    success: 3,
    failed: 1,
    time_basis: "Rows are included when COALESCE(completed_at, created_at) falls within the last 24 hours (UTC).",
  },
  approval_gated: {
    awaiting_approval: 1,
    with_linked_approval: 3,
  },
  unknown_statuses: {
    legacy_unknown: 2,
  },
};

beforeEach(() => {
  jest.clearAllMocks();
});

test("renders loading state while request is in flight", async () => {
  getPlaybookMetrics.mockImplementation(
    () =>
      new Promise((resolve) => {
        setTimeout(() => resolve(fullPayload), 60);
      })
  );

  render(<PlaybookMetricsPanel {...styleProps} />);

  expect(screen.getByText(/loading playbook metrics/i)).toBeInTheDocument();
  expect(screen.getByRole("note")).toHaveTextContent(/simulation only/i);

  await waitFor(() => {
    expect(screen.getByText(/status breakdown/i)).toBeInTheDocument();
  });
});

test("renders error state on API failure", async () => {
  getPlaybookMetrics.mockRejectedValueOnce(new Error("Request failed"));

  render(<PlaybookMetricsPanel {...styleProps} />);

  expect(await screen.findByText(/error: request failed/i)).toBeInTheDocument();
  expect(screen.queryByText(/status breakdown/i)).not.toBeInTheDocument();
});

test("renders empty state when total and all known statuses are zero", async () => {
  getPlaybookMetrics.mockResolvedValueOnce({
    total_executions: 0,
    by_status: {
      pending: 0,
      running: 0,
      awaiting_approval: 0,
      success: 0,
      failed: 0,
      abandoned: 0,
    },
    by_playbook_id: [],
    recent: { window_hours: 24, success: 0, failed: 0 },
    approval_gated: { awaiting_approval: 0, with_linked_approval: 0 },
  });

  render(<PlaybookMetricsPanel {...styleProps} />);

  expect(await screen.findByText(/no playbook execution data yet/i)).toBeInTheDocument();
});

test("shows total executions in populated state", async () => {
  getPlaybookMetrics.mockResolvedValueOnce(fullPayload);

  render(<PlaybookMetricsPanel {...styleProps} />);

  expect(await screen.findByText(/total executions/i)).toBeInTheDocument();
  expect(screen.getByText("12")).toBeInTheDocument();
});

test("renders all six known statuses including zeros", async () => {
  getPlaybookMetrics.mockResolvedValueOnce({
    ...fullPayload,
    by_status: {
      pending: 0,
      running: 0,
      awaiting_approval: 0,
      success: 1,
      failed: 0,
      abandoned: 0,
    },
  });

  render(<PlaybookMetricsPanel {...styleProps} />);

  expect(await screen.findByText("pending")).toBeInTheDocument();
  expect(screen.getByText("running")).toBeInTheDocument();
  expect(screen.getByText("awaiting_approval")).toBeInTheDocument();
  expect(screen.getByText("success")).toBeInTheDocument();
  expect(screen.getByText("failed")).toBeInTheDocument();
  expect(screen.getByText("abandoned")).toBeInTheDocument();
});

test("renders recent success/failure with window label", async () => {
  getPlaybookMetrics.mockResolvedValueOnce(fullPayload);

  render(<PlaybookMetricsPanel {...styleProps} />);

  expect(await screen.findByText(/last 24 hours - success: 3 \| failed: 1/i)).toBeInTheDocument();
});

test("renders approval-gated counts", async () => {
  getPlaybookMetrics.mockResolvedValueOnce(fullPayload);

  render(<PlaybookMetricsPanel {...styleProps} />);

  expect(await screen.findByText(/currently awaiting approval: 1/i)).toBeInTheDocument();
  expect(screen.getByText(/ever had a linked approval: 3/i)).toBeInTheDocument();
});

test("renders per-playbook breakdown with id and total", async () => {
  getPlaybookMetrics.mockResolvedValueOnce(fullPayload);

  render(<PlaybookMetricsPanel {...styleProps} />);

  expect(await screen.findByText("block_and_notify")).toBeInTheDocument();
  expect(screen.getByText("monitor_only")).toBeInTheDocument();
  expect(screen.getByText(/total: 7/i)).toBeInTheDocument();
  expect(screen.getByText(/total: 5/i)).toBeInTheDocument();
});

test("simulation notice remains visible in populated state", async () => {
  getPlaybookMetrics.mockResolvedValueOnce(fullPayload);

  render(<PlaybookMetricsPanel {...styleProps} />);
  await screen.findByText("block_and_notify");

  expect(screen.getByRole("note")).toHaveTextContent(/no real remediation/i);
});

test("does not render run/retry/cancel/approve mutation controls", async () => {
  getPlaybookMetrics.mockResolvedValueOnce(fullPayload);

  render(<PlaybookMetricsPanel {...styleProps} />);
  await screen.findByText("block_and_notify");

  expect(screen.queryByRole("button", { name: /run/i })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /retry/i })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /cancel/i })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /approve/i })).not.toBeInTheDocument();
});

test("does not crash when by_playbook_id is missing", async () => {
  getPlaybookMetrics.mockResolvedValueOnce({
    ...fullPayload,
    by_playbook_id: undefined,
  });

  render(<PlaybookMetricsPanel {...styleProps} />);

  expect(await screen.findByText(/no playbook-level data available/i)).toBeInTheDocument();
});

test("does not crash when recent is missing", async () => {
  getPlaybookMetrics.mockResolvedValueOnce({
    ...fullPayload,
    recent: null,
  });

  render(<PlaybookMetricsPanel {...styleProps} />);

  expect(await screen.findByText(/last 24 hours - success: 0 \| failed: 0/i)).toBeInTheDocument();
});

test("does not crash when approval_gated is missing", async () => {
  getPlaybookMetrics.mockResolvedValueOnce({
    ...fullPayload,
    approval_gated: null,
  });

  render(<PlaybookMetricsPanel {...styleProps} />);

  expect(await screen.findByText(/currently awaiting approval: 0/i)).toBeInTheDocument();
  expect(screen.getByText(/ever had a linked approval: 0/i)).toBeInTheDocument();
});

test("renders Other when other_status_count is present and > 0", async () => {
  getPlaybookMetrics.mockResolvedValueOnce(fullPayload);

  render(<PlaybookMetricsPanel {...styleProps} />);
  await screen.findByText("block_and_notify");

  expect(screen.getByText(/other: 1/i)).toBeInTheDocument();
});

test("does not render Other when other_status_count is absent", async () => {
  getPlaybookMetrics.mockResolvedValueOnce({
    ...fullPayload,
    by_playbook_id: [
      {
        playbook_id: "monitor_only",
        total: 5,
        by_status: {
          pending: 1,
          running: 1,
          awaiting_approval: 1,
          success: 1,
          failed: 0,
          abandoned: 1,
        },
      },
    ],
  });

  render(<PlaybookMetricsPanel {...styleProps} />);
  await screen.findByText("monitor_only");

  expect(screen.queryByText(/other:/i)).not.toBeInTheDocument();
});

test("renders Other / Unknown row when unknown_statuses exists", async () => {
  getPlaybookMetrics.mockResolvedValueOnce(fullPayload);

  render(<PlaybookMetricsPanel {...styleProps} />);

  expect(await screen.findByText(/other \/ unknown/i)).toBeInTheDocument();
  expect(screen.getAllByText("2").length).toBeGreaterThanOrEqual(1);
});

test("does not render Other / Unknown row when unknown_statuses is absent", async () => {
  getPlaybookMetrics.mockResolvedValueOnce({
    ...fullPayload,
    unknown_statuses: undefined,
  });

  render(<PlaybookMetricsPanel {...styleProps} />);

  await screen.findByText(/status breakdown/i);
  expect(screen.queryByText(/other \/ unknown/i)).not.toBeInTheDocument();
});
