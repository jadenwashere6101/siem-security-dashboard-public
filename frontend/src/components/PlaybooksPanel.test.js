import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import PlaybooksPanel from "./PlaybooksPanel";
import {
  getPlaybook,
  getPlaybookExecution,
  listPlaybookExecutions,
  listPlaybooks,
} from "../services/playbookService";

jest.mock("../services/playbookService", () => ({
  listPlaybooks: jest.fn(),
  getPlaybook: jest.fn(),
  listPlaybookExecutions: jest.fn(),
  getPlaybookExecution: jest.fn(),
}));

const styleProps = {
  cardStyle: {},
  cardHeaderStyle: {},
  cardTitleStyle: {},
  cardSubtitleStyle: {},
  filterWrapperStyle: {},
  filterLabelStyle: {},
  selectStyle: {},
};

const defRow = {
  id: "pb_one",
  name: "Test playbook",
  description: "d",
  enabled: true,
  trigger_config: { min_severity: "HIGH" },
  steps: [{ action: "monitor", params: {} }],
  created_at: "2026-05-09T10:00:00Z",
  updated_at: "2026-05-09T11:00:00Z",
};

const execRow = {
  id: 42,
  playbook_id: "pb_one",
  alert_id: null,
  incident_id: null,
  status: "pending",
  started_at: null,
  completed_at: null,
  last_completed_step: null,
  steps_log: [],
  created_at: "2026-05-09T12:00:00Z",
};

beforeEach(() => {
  jest.clearAllMocks();
});

test("shows loading then definitions after load", async () => {
  listPlaybooks.mockImplementation(
    () =>
      new Promise((resolve) => {
        setTimeout(() => resolve({ items: [defRow], limit: 50, enabled: null }), 30);
      })
  );
  listPlaybookExecutions.mockResolvedValue({ items: [], limit: 50 });

  render(<PlaybooksPanel {...styleProps} />);

  expect(screen.getByText(/loading playbook definitions/i)).toBeInTheDocument();

  expect(await screen.findByText("pb_one")).toBeInTheDocument();
  expect(screen.getByText("Test playbook")).toBeInTheDocument();
});

test("renders executions after switching panel", async () => {
  listPlaybooks.mockResolvedValue({ items: [defRow], limit: 50, enabled: null });
  listPlaybookExecutions.mockResolvedValue({ items: [execRow], limit: 50 });

  render(<PlaybooksPanel {...styleProps} />);

  expect(await screen.findByText("pb_one")).toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: /^executions$/i }));

  expect(await screen.findByText("42")).toBeInTheDocument();
  expect(screen.getByRole("columnheader", { name: /status/i })).toBeInTheDocument();
});

test("definition empty state when no items", async () => {
  listPlaybooks.mockResolvedValue({ items: [], limit: 50, enabled: null });
  listPlaybookExecutions.mockResolvedValue({ items: [], limit: 50 });

  render(<PlaybooksPanel {...styleProps} />);

  expect(
    await screen.findByText(/no playbook definitions found/i)
  ).toBeInTheDocument();
});

test("execution empty state when no items", async () => {
  listPlaybooks.mockResolvedValue({ items: [defRow], limit: 50 });
  listPlaybookExecutions.mockResolvedValue({ items: [], limit: 50 });

  render(<PlaybooksPanel {...styleProps} />);
  await screen.findByText("pb_one");
  await userEvent.click(screen.getByRole("button", { name: /^executions$/i }));

  expect(
    await screen.findByText(/no playbook execution records found/i)
  ).toBeInTheDocument();
});

test("definition load error", async () => {
  listPlaybooks.mockRejectedValue(new Error("network down"));
  listPlaybookExecutions.mockResolvedValue({ items: [], limit: 50 });

  render(<PlaybooksPanel {...styleProps} />);

  expect(await screen.findByText(/network down/i)).toBeInTheDocument();
});

test("execution load error", async () => {
  listPlaybooks.mockResolvedValue({ items: [defRow], limit: 50 });
  listPlaybookExecutions.mockRejectedValue(new Error("exec fail"));

  render(<PlaybooksPanel {...styleProps} />);
  await screen.findByText("pb_one");
  await userEvent.click(screen.getByRole("button", { name: /^executions$/i }));

  expect(await screen.findByText(/exec fail/i)).toBeInTheDocument();
});

test("enabled filter calls listPlaybooks with expected params", async () => {
  listPlaybooks.mockResolvedValue({ items: [], limit: 50, enabled: true });
  listPlaybookExecutions.mockResolvedValue({ items: [], limit: 50 });

  render(<PlaybooksPanel {...styleProps} />);
  await waitFor(() => expect(listPlaybooks).toHaveBeenCalled());

  const select = screen.getByLabelText(/enabled filter/i);
  await userEvent.selectOptions(select, "enabled");

  await waitFor(() => {
    expect(listPlaybooks).toHaveBeenCalledWith(
      expect.objectContaining({ enabled: true, limit: 50 })
    );
  });
});

test("execution status filter calls listPlaybookExecutions with status", async () => {
  listPlaybooks.mockResolvedValue({ items: [defRow], limit: 50 });
  listPlaybookExecutions.mockResolvedValue({ items: [], limit: 50 });

  render(<PlaybooksPanel {...styleProps} />);
  await screen.findByText("pb_one");
  await userEvent.click(screen.getByRole("button", { name: /^executions$/i }));

  const statusSelect = await screen.findByLabelText(/^status$/i);
  await userEvent.selectOptions(statusSelect, "running");

  await waitFor(() => {
    expect(listPlaybookExecutions).toHaveBeenCalledWith(
      expect.objectContaining({ status: "running", limit: 50 })
    );
  });
});

test("view definition calls getPlaybook and shows read-only JSON", async () => {
  listPlaybooks.mockResolvedValue({ items: [defRow], limit: 50 });
  listPlaybookExecutions.mockResolvedValue({ items: [], limit: 50 });
  getPlaybook.mockResolvedValue({
    ...defRow,
    trigger_config: { alert_type: "x" },
    steps: [{ action: "monitor" }],
  });

  render(<PlaybooksPanel {...styleProps} />);
  await screen.findByText("pb_one");

  const viewButtons = screen.getAllByRole("button", { name: /^view$/i });
  await userEvent.click(viewButtons[0]);

  await waitFor(() => {
    expect(getPlaybook).toHaveBeenCalledWith("pb_one");
  });

  expect(screen.getByText(/definition detail/i)).toBeInTheDocument();
  await waitFor(() => {
    expect(screen.getByText(/alert_type/, { exact: false })).toBeInTheDocument();
  });
});

test("view execution calls getPlaybookExecution", async () => {
  listPlaybooks.mockResolvedValue({ items: [defRow], limit: 50 });
  listPlaybookExecutions.mockResolvedValue({ items: [execRow], limit: 50 });
  getPlaybookExecution.mockResolvedValue({
    ...execRow,
    steps_log: [{ step_index: 0, status: "pending" }],
  });

  render(<PlaybooksPanel {...styleProps} />);
  await screen.findByText("pb_one");
  await userEvent.click(screen.getByRole("button", { name: /^executions$/i }));
  await screen.findByText("42");

  const viewButtons = screen.getAllByRole("button", { name: /^view$/i });
  await userEvent.click(viewButtons[viewButtons.length - 1]);

  await waitFor(() => {
    expect(getPlaybookExecution).toHaveBeenCalledWith(42);
  });
  expect(screen.getByText(/execution detail/i)).toBeInTheDocument();
});

test("refresh triggers additional read-only GET calls", async () => {
  listPlaybooks.mockResolvedValue({ items: [defRow], limit: 50 });
  listPlaybookExecutions.mockResolvedValue({ items: [], limit: 50 });

  render(<PlaybooksPanel {...styleProps} />);
  await screen.findByText("pb_one");

  const initialDef = listPlaybooks.mock.calls.length;
  const initialExec = listPlaybookExecutions.mock.calls.length;

  await userEvent.click(screen.getByRole("button", { name: /^refresh$/i }));

  await waitFor(() => {
    expect(listPlaybooks.mock.calls.length).toBeGreaterThan(initialDef);
    expect(listPlaybookExecutions.mock.calls.length).toBeGreaterThan(initialExec);
  });
});

test("does not render run, retry, cancel, or delete controls", async () => {
  listPlaybooks.mockResolvedValue({ items: [defRow], limit: 50 });
  listPlaybookExecutions.mockResolvedValue({ items: [execRow], limit: 50 });

  render(<PlaybooksPanel {...styleProps} />);
  await screen.findByText("pb_one");

  expect(screen.queryByRole("button", { name: /run simulation/i })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /^retry$/i })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /^cancel$/i })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /delete/i })).not.toBeInTheDocument();
});

test("shows visibility-only notice", async () => {
  listPlaybooks.mockResolvedValue({ items: [], limit: 50 });
  listPlaybookExecutions.mockResolvedValue({ items: [], limit: 50 });

  render(<PlaybooksPanel {...styleProps} />);

  expect(
    await screen.findByText(/playbooks are visible only; execution is not enabled yet/i)
  ).toBeInTheDocument();
});
