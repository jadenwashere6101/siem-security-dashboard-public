import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import DeadLettersPanel from "./DeadLettersPanel";
import {
  getDeadLetter,
  getDeadLetterMetrics,
  getDeadLetters,
} from "../services/deadLetterService";

jest.mock("../services/deadLetterService", () => ({
  getDeadLetter: jest.fn(),
  getDeadLetterMetrics: jest.fn(),
  getDeadLetters: jest.fn(),
}));

const styleProps = {
  cardStyle: {},
  cardHeaderStyle: {},
  cardTitleStyle: {},
  cardSubtitleStyle: {},
  filterLabelStyle: {},
  selectStyle: {},
  userRole: "analyst",
};

const sampleMetrics = {
  total: 4,
  open: 2,
  retrying: 1,
  retried: 0,
  dismissed: 1,
  active: 3,
  oldest_active_at: "2026-05-10T12:00:00Z",
  by_status: { open: 2, retrying: 1, retried: 0, dismissed: 1 },
  by_source_type: { playbook_execution: 3, notification_delivery: 1 },
  by_failure_class: { adapter_failed: 2, timeout: 1 },
};

const listRow = {
  id: 7,
  status: "open",
  source_type: "playbook_execution",
  source_id: 99,
  failure_class: "adapter_failed",
  retry_count: 0,
  created_at: "2026-05-10T10:00:00Z",
};

const detailRow = {
  ...listRow,
  execution_id: 42,
  incident_id: 5,
  alert_id: 10,
  playbook_id: "pb_test",
  step_index: 1,
  action_name: "notify_slack",
  retryable: false,
  error_message: "failed at [REDACTED_URL]",
  payload_json: {
    safe: "kept",
    nested: {},
    callback: "[REDACTED_URL]",
  },
  first_failed_at: "2026-05-10T09:00:00Z",
  last_failed_at: "2026-05-10T10:00:00Z",
};

const detailRowNoLinks = {
  id: 8,
  status: "dismissed",
  source_type: "approval",
  source_id: 12,
  failure_class: "timeout",
  retry_count: 1,
  created_at: "2026-05-09T10:00:00Z",
  execution_id: null,
  incident_id: null,
  alert_id: null,
  playbook_id: null,
  step_index: null,
  action_name: null,
  retryable: false,
  error_message: "approval expired",
  payload_json: {},
};

beforeEach(() => {
  jest.clearAllMocks();
  getDeadLetterMetrics.mockResolvedValue(sampleMetrics);
  getDeadLetters.mockResolvedValue({ items: [listRow], limit: 100, offset: 0 });
  getDeadLetter.mockResolvedValue(detailRow);
});

test("renders loading then list", async () => {
  getDeadLetters.mockImplementation(
    () =>
      new Promise((resolve) => {
        setTimeout(() => resolve({ items: [listRow], limit: 100, offset: 0 }), 40);
      })
  );

  render(<DeadLettersPanel {...styleProps} />);

  expect(screen.getByText(/loading dead letters/i)).toBeInTheDocument();
  expect(screen.getByRole("note")).toHaveTextContent(/operational review only/i);

  expect(await screen.findByText("99")).toBeInTheDocument();
  expect(screen.getByTitle("View dead letter 7")).toBeInTheDocument();
});

test("renders metric cards", async () => {
  render(<DeadLettersPanel {...styleProps} />);

  await waitFor(() => {
    const metricValues = screen.getAllByRole("strong").map((node) => node.textContent);
    expect(metricValues).toEqual(expect.arrayContaining(["2", "1", "0", "1"]));
  });
  expect(screen.getByText(/oldest active dead letter/i)).toBeInTheDocument();
});

test("filters call service with correct params", async () => {
  render(<DeadLettersPanel {...styleProps} />);

  await screen.findByText("99");

  getDeadLetters.mockClear();
  getDeadLetters.mockResolvedValue({ items: [], limit: 100, offset: 0 });

  await userEvent.selectOptions(
    screen.getByLabelText(/filter dead letters by status/i),
    "open"
  );

  await waitFor(() => {
    expect(getDeadLetters).toHaveBeenCalledWith({ status: "open" });
  });

  getDeadLetters.mockClear();

  await userEvent.selectOptions(
    screen.getByLabelText(/filter dead letters by source type/i),
    "playbook_execution"
  );

  await waitFor(() => {
    expect(getDeadLetters).toHaveBeenCalledWith({
      status: "open",
      source_type: "playbook_execution",
    });
  });

  getDeadLetters.mockClear();

  await userEvent.selectOptions(
    screen.getByLabelText(/filter dead letters by failure class/i),
    "adapter_failed"
  );

  await waitFor(() => {
    expect(getDeadLetters).toHaveBeenCalledWith({
      status: "open",
      source_type: "playbook_execution",
      failure_class: "adapter_failed",
    });
  });
});

test("selecting row shows detail", async () => {
  render(<DeadLettersPanel {...styleProps} />);

  await screen.findByText("99");

  await userEvent.click(screen.getByTitle("View dead letter 7"));

  expect(await screen.findByText(/dead letter #7/i)).toBeInTheDocument();
  expect(getDeadLetter).toHaveBeenCalledWith(7);
  expect(screen.getByText(/view in soar playbooks/i)).toBeInTheDocument();
  expect(screen.getByText(/view in soar incidents/i)).toBeInTheDocument();
  expect(screen.getByText(/index 1, action notify_slack/i)).toBeInTheDocument();
});

test("empty state", async () => {
  getDeadLetters.mockResolvedValue({ items: [], limit: 100, offset: 0 });

  render(<DeadLettersPanel {...styleProps} />);

  expect(
    await screen.findByText(/no dead letters found \(no filters applied\)/i)
  ).toBeInTheDocument();
});

test("error state", async () => {
  getDeadLetterMetrics.mockRejectedValueOnce(new Error("Metrics unavailable"));

  render(<DeadLettersPanel {...styleProps} />);

  expect(await screen.findByText(/error: metrics unavailable/i)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();

  getDeadLetterMetrics.mockResolvedValueOnce(sampleMetrics);
  getDeadLetters.mockResolvedValueOnce({ items: [listRow], limit: 100, offset: 0 });

  await userEvent.click(screen.getByRole("button", { name: /retry/i }));

  expect(await screen.findByText("99")).toBeInTheDocument();
});

test("detail fetch error shows inline error", async () => {
  render(<DeadLettersPanel {...styleProps} />);

  await screen.findByText("99");

  getDeadLetter.mockRejectedValueOnce(new Error("Detail failed"));

  await userEvent.click(screen.getByTitle("View dead letter 7"));

  expect(await screen.findByText(/detail failed/i)).toBeInTheDocument();
});

test("safe payload rendering", async () => {
  render(<DeadLettersPanel {...styleProps} />);

  await screen.findByText("99");
  await userEvent.click(screen.getByTitle("View dead letter 7"));

  expect(await screen.findByText(/payload \(redacted\)/i)).toBeInTheDocument();
  expect(screen.getByText("safe")).toBeInTheDocument();
  expect(screen.getByText("kept")).toBeInTheDocument();
  expect(screen.getByText("[REDACTED_URL]")).toBeInTheDocument();
  expect(screen.getByText(/failed at \[REDACTED_URL\]/i)).toBeInTheDocument();
  expect(screen.queryByText(/hooks\.slack/i)).not.toBeInTheDocument();
});

test("linked context section omitted when all ids are null", async () => {
  getDeadLetters.mockResolvedValue({
    items: [{ ...listRow, id: 8, source_id: 12 }],
    limit: 100,
    offset: 0,
  });
  getDeadLetter.mockResolvedValue(detailRowNoLinks);

  render(<DeadLettersPanel {...styleProps} />);

  await screen.findByTitle("View dead letter 8");
  await userEvent.click(screen.getByTitle("View dead letter 8"));

  expect(await screen.findByText(/dead letter #8/i)).toBeInTheDocument();
  expect(screen.queryByText(/linked context/i)).not.toBeInTheDocument();
  expect(screen.queryByText(/view in soar playbooks/i)).not.toBeInTheDocument();
});

test("does not render dismiss or retry action buttons", async () => {
  render(<DeadLettersPanel {...styleProps} />);

  await screen.findByText("99");
  await userEvent.click(screen.getByTitle("View dead letter 7"));
  await screen.findByText(/dead letter #7/i);

  expect(screen.queryByRole("button", { name: /dismiss/i })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /retry request/i })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /retry execute/i })).not.toBeInTheDocument();
});
