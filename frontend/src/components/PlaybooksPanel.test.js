import React from "react";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import PlaybooksPanel from "./PlaybooksPanel";
import {
  getPlaybook,
  getPlaybookExecution,
  listPlaybookExecutions,
  listPlaybooks,
  createPlaybookDefinition,
  updatePlaybookDefinition,
  setPlaybookDefinitionEnabled,
} from "../services/playbookService";

jest.mock("../services/playbookService", () => ({
  listPlaybooks: jest.fn(),
  getPlaybook: jest.fn(),
  listPlaybookExecutions: jest.fn(),
  getPlaybookExecution: jest.fn(),
  createPlaybookDefinition: jest.fn(),
  updatePlaybookDefinition: jest.fn(),
  setPlaybookDefinitionEnabled: jest.fn(),
}));

const styleProps = {
  cardStyle: {},
  cardHeaderStyle: {},
  cardTitleStyle: {},
  cardSubtitleStyle: {},
  filterWrapperStyle: {},
  filterLabelStyle: {},
  selectStyle: {},
  userRole: "analyst",
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

test("execution detail shows context fields and pending empty timeline", async () => {
  listPlaybooks.mockResolvedValue({ items: [defRow], limit: 50 });
  listPlaybookExecutions.mockResolvedValue({ items: [execRow], limit: 50 });
  getPlaybookExecution.mockResolvedValue({
    ...execRow,
    alert_id: 123,
    incident_id: 456,
    last_completed_step: null,
    steps_log: [],
  });

  render(<PlaybooksPanel {...styleProps} />);
  await screen.findByText("pb_one");
  await userEvent.click(screen.getByRole("button", { name: /^executions$/i }));
  await screen.findByText("42");

  const viewButtons = screen.getAllByRole("button", { name: /^view$/i });
  await userEvent.click(viewButtons[viewButtons.length - 1]);

  expect(await screen.findByText(/pending simulation; no steps have been consumed yet/i)).toBeInTheDocument();
  expect(screen.getByText(/no simulated steps have run yet/i)).toBeInTheDocument();
  expect(screen.getAllByText(/^playbook id$/i).length).toBeGreaterThan(0);
  expect(screen.getAllByText("pb_one").length).toBeGreaterThan(0);
  expect(screen.getByText(/^alert id$/i)).toBeInTheDocument();
  expect(screen.getByText("123")).toBeInTheDocument();
  expect(screen.getByText(/^incident id$/i)).toBeInTheDocument();
  expect(screen.getByText("456")).toBeInTheDocument();
  expect(screen.getByText(/^last completed step$/i)).toBeInTheDocument();
});

test("execution detail renders simulated steps_log as timeline cards", async () => {
  listPlaybooks.mockResolvedValue({ items: [defRow], limit: 50 });
  listPlaybookExecutions.mockResolvedValue({ items: [{ ...execRow, status: "success" }], limit: 50 });
  getPlaybookExecution.mockResolvedValue({
    ...execRow,
    status: "success",
    alert_id: 777,
    incident_id: null,
    started_at: "2026-05-09T12:01:00Z",
    completed_at: "2026-05-09T12:02:00Z",
    last_completed_step: 1,
    steps_log: [
      {
        step_index: 0,
        action: "enrich_alert",
        status: "success",
        mode: "simulation",
        simulated: true,
        executed: false,
        started_at: "2026-05-09T12:01:01Z",
        completed_at: "2026-05-09T12:01:02Z",
        message: "Simulated enrichment completed.",
      },
      {
        step_index: 1,
        action: "notify_owner",
        status: "skipped",
        simulated: true,
        executed: false,
        result: { message: "Notification suppressed in simulation." },
      },
    ],
  });

  render(<PlaybooksPanel {...styleProps} />);
  await screen.findByText("pb_one");
  await userEvent.click(screen.getByRole("button", { name: /^executions$/i }));
  await screen.findByText("42");

  const viewButtons = screen.getAllByRole("button", { name: /^view$/i });
  await userEvent.click(viewButtons[viewButtons.length - 1]);

  expect(await screen.findByText(/simulation completed successfully/i)).toBeInTheDocument();
  expect(screen.getByText(/step timeline/i)).toBeInTheDocument();
  expect(screen.getByText("Step 1")).toBeInTheDocument();
  expect(screen.getByText("enrich_alert")).toBeInTheDocument();
  expect(screen.getByText("Simulated enrichment completed.")).toBeInTheDocument();
  expect(screen.getByText("Step 2")).toBeInTheDocument();
  expect(screen.getByText("notify_owner")).toBeInTheDocument();
  expect(screen.getAllByText(/notification suppressed in simulation/i).length).toBeGreaterThan(0);

  const firstStep = screen.getByText("enrich_alert").closest("div");
  expect(firstStep).toBeTruthy();
  expect(within(firstStep.parentElement).getByText(/^simulated$/i)).toBeInTheDocument();
  expect(within(firstStep.parentElement).getAllByText(/^yes$/i).length).toBeGreaterThan(0);
  expect(within(firstStep.parentElement).getByText(/^executed$/i)).toBeInTheDocument();
  expect(within(firstStep.parentElement).getAllByText(/^no$/i).length).toBeGreaterThan(0);
});

test("execution detail shows failed step errors without mutation controls", async () => {
  listPlaybooks.mockResolvedValue({ items: [defRow], limit: 50 });
  listPlaybookExecutions.mockResolvedValue({ items: [{ ...execRow, status: "failed" }], limit: 50 });
  getPlaybookExecution.mockResolvedValue({
    ...execRow,
    status: "failed",
    steps_log: [
      {
        step_index: 0,
        action: "unsupported_action",
        status: "failed",
        simulated: true,
        executed: false,
        error_code: "unsupported_action",
        error: { message: "Unsupported simulated step action." },
      },
    ],
  });

  render(<PlaybooksPanel {...styleProps} />);
  await screen.findByText("pb_one");
  await userEvent.click(screen.getByRole("button", { name: /^executions$/i }));
  await screen.findByText("42");

  const viewButtons = screen.getAllByRole("button", { name: /^view$/i });
  await userEvent.click(viewButtons[viewButtons.length - 1]);

  expect(await screen.findByText(/simulation failed before completing all steps/i)).toBeInTheDocument();
  expect(screen.getByText("unsupported_action")).toBeInTheDocument();
  expect(screen.getByText(/error code: unsupported_action/i)).toBeInTheDocument();
  expect(screen.getAllByText(/unsupported simulated step action/i).length).toBeGreaterThan(0);
  expect(screen.queryByRole("button", { name: /run|retry|cancel/i })).not.toBeInTheDocument();
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

  render(<PlaybooksPanel {...styleProps} userRole="analyst" />);
  await screen.findByText("pb_one");

  expect(screen.queryByRole("button", { name: /run simulation/i })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /^retry$/i })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /^cancel$/i })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /delete/i })).not.toBeInTheDocument();
});

test("shows visibility-only notice", async () => {
  listPlaybooks.mockResolvedValue({ items: [], limit: 50 });
  listPlaybookExecutions.mockResolvedValue({ items: [], limit: 50 });

  render(<PlaybooksPanel {...styleProps} userRole="analyst" />);

  expect(
    await screen.findByText(/playbooks are visible only; execution is not enabled yet/i)
  ).toBeInTheDocument();
});

// Super admin mutation control tests
test("super admin sees New Definition button", async () => {
  listPlaybooks.mockResolvedValue({ items: [defRow], limit: 50 });
  listPlaybookExecutions.mockResolvedValue({ items: [], limit: 50 });

  render(<PlaybooksPanel {...styleProps} userRole="super_admin" />);
  await screen.findByText("pb_one");

  expect(screen.getByRole("button", { name: /\+ New Definition/i })).toBeInTheDocument();
});

test("analyst does not see New Definition button", async () => {
  listPlaybooks.mockResolvedValue({ items: [defRow], limit: 50 });
  listPlaybookExecutions.mockResolvedValue({ items: [], limit: 50 });

  render(<PlaybooksPanel {...styleProps} userRole="analyst" />);
  await screen.findByText("pb_one");

  expect(screen.queryByRole("button", { name: /\+ New Definition/i })).not.toBeInTheDocument();
});

test("super admin sees Edit and Enable/Disable buttons for each definition", async () => {
  listPlaybooks.mockResolvedValue({ items: [defRow], limit: 50 });
  listPlaybookExecutions.mockResolvedValue({ items: [], limit: 50 });

  render(<PlaybooksPanel {...styleProps} userRole="super_admin" />);
  await screen.findByText("pb_one");

  expect(screen.getByRole("button", { name: /^Edit$/i })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /^Disable$/i })).toBeInTheDocument();
});

test("analyst does not see Edit or Enable/Disable buttons", async () => {
  listPlaybooks.mockResolvedValue({ items: [defRow], limit: 50 });
  listPlaybookExecutions.mockResolvedValue({ items: [], limit: 50 });

  render(<PlaybooksPanel {...styleProps} userRole="analyst" />);
  await screen.findByText("pb_one");

  expect(screen.queryByRole("button", { name: /^Edit$/i })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /^Disable$/i })).not.toBeInTheDocument();
});

test("super admin can open and close create form", async () => {
  listPlaybooks.mockResolvedValue({ items: [], limit: 50 });
  listPlaybookExecutions.mockResolvedValue({ items: [], limit: 50 });

  render(<PlaybooksPanel {...styleProps} userRole="super_admin" />);

  const newDefButton = await screen.findByRole("button", { name: /\+ New Definition/i });
  await userEvent.click(newDefButton);

  expect(
    screen.getByText(/create new playbook definition/i)
  ).toBeInTheDocument();
  expect(screen.getByLabelText(/^ID \(required\)/i)).toBeInTheDocument();
  expect(screen.getByLabelText(/^Name \(required\)/i)).toBeInTheDocument();

  const closeButton = screen.getByRole("button", { name: /✕/i });
  await userEvent.click(closeButton);

  expect(
    screen.queryByText(/create new playbook definition/i)
  ).not.toBeInTheDocument();
});

test("super admin can open edit form with existing values", async () => {
  listPlaybooks.mockResolvedValue({ items: [defRow], limit: 50 });
  listPlaybookExecutions.mockResolvedValue({ items: [], limit: 50 });

  render(<PlaybooksPanel {...styleProps} userRole="super_admin" />);
  await screen.findByText("pb_one");

  const editButton = screen.getByRole("button", { name: /^Edit$/i });
  await userEvent.click(editButton);

  expect(
    screen.getByText(/edit playbook definition/i)
  ).toBeInTheDocument();

  const idInput = screen.getByLabelText(/^ID \(read-only\)/i);
  expect(idInput).toHaveValue("pb_one");
  expect(idInput).toBeDisabled();

  const nameInput = screen.getByLabelText(/^Name \(required\)/i);
  expect(nameInput).toHaveValue("Test playbook");
});

test("form validates required ID on create", async () => {
  listPlaybooks.mockResolvedValue({ items: [], limit: 50 });
  listPlaybookExecutions.mockResolvedValue({ items: [], limit: 50 });

  render(<PlaybooksPanel {...styleProps} userRole="super_admin" />);

  const newDefButton = await screen.findByRole("button", { name: /\+ New Definition/i });
  await userEvent.click(newDefButton);

  const nameInput = screen.getByLabelText(/^Name \(required\)/i);
  await userEvent.clear(nameInput);
  await userEvent.type(nameInput, "Test");

  const createButton = screen.getByRole("button", { name: /^Create$/i });
  await userEvent.click(createButton);

  expect(
    screen.getByText(/ID is required for creating a definition/i)
  ).toBeInTheDocument();
  expect(createPlaybookDefinition).not.toHaveBeenCalled();
});

test("form validates ID format on create", async () => {
  listPlaybooks.mockResolvedValue({ items: [], limit: 50 });
  listPlaybookExecutions.mockResolvedValue({ items: [], limit: 50 });

  render(<PlaybooksPanel {...styleProps} userRole="super_admin" />);

  const newDefButton = await screen.findByRole("button", { name: /\+ New Definition/i });
  await userEvent.click(newDefButton);

  const idInput = screen.getByLabelText(/^ID \(required\)/i);
  await userEvent.type(idInput, "Invalid ID!");

  const nameInput = screen.getByLabelText(/^Name \(required\)/i);
  await userEvent.type(nameInput, "Test");

  const createButton = screen.getByRole("button", { name: /^Create$/i });
  await userEvent.click(createButton);

  expect(
    screen.getByText(/ID must contain only lowercase letters, digits, underscores, and hyphens/i)
  ).toBeInTheDocument();
  expect(createPlaybookDefinition).not.toHaveBeenCalled();
});

test("form validates required name", async () => {
  listPlaybooks.mockResolvedValue({ items: [], limit: 50 });
  listPlaybookExecutions.mockResolvedValue({ items: [], limit: 50 });

  render(<PlaybooksPanel {...styleProps} userRole="super_admin" />);

  const newDefButton = await screen.findByRole("button", { name: /\+ New Definition/i });
  await userEvent.click(newDefButton);

  const idInput = screen.getByLabelText(/^ID \(required\)/i);
  await userEvent.type(idInput, "test_pb");

  const createButton = screen.getByRole("button", { name: /^Create$/i });
  await userEvent.click(createButton);

  expect(
    screen.getByText(/Name is required/i)
  ).toBeInTheDocument();
  expect(createPlaybookDefinition).not.toHaveBeenCalled();
});

test("form validates trigger JSON must be object", async () => {
  listPlaybooks.mockResolvedValue({ items: [], limit: 50 });
  listPlaybookExecutions.mockResolvedValue({ items: [], limit: 50 });

  render(<PlaybooksPanel {...styleProps} userRole="super_admin" />);

  const newDefButton = await screen.findByRole("button", { name: /\+ New Definition/i });
  await userEvent.click(newDefButton);

  const idInput = screen.getByLabelText(/^ID \(required\)/i);
  await userEvent.type(idInput, "test_pb");

  const nameInput = screen.getByLabelText(/^Name \(required\)/i);
  await userEvent.type(nameInput, "Test");

  const triggerInput = screen.getByLabelText(/^Trigger Config/i);
  await userEvent.clear(triggerInput);
  await userEvent.type(triggerInput, '["not", "an", "object"]');

  const createButton = screen.getByRole("button", { name: /^Create$/i });
  await userEvent.click(createButton);

  // Validation should prevent the service call
  await waitFor(() => {
    expect(createPlaybookDefinition).not.toHaveBeenCalled();
  });
  
  // Form should still be visible with error
  expect(screen.getByText(/create new playbook definition/i)).toBeInTheDocument();
});

test("form validates steps JSON must be array", async () => {
  listPlaybooks.mockResolvedValue({ items: [], limit: 50 });
  listPlaybookExecutions.mockResolvedValue({ items: [], limit: 50 });

  render(<PlaybooksPanel {...styleProps} userRole="super_admin" />);

  const newDefButton = await screen.findByRole("button", { name: /\+ New Definition/i });
  await userEvent.click(newDefButton);

  const idInput = screen.getByLabelText(/^ID \(required\)/i);
  await userEvent.type(idInput, "test_pb");

  const nameInput = screen.getByLabelText(/^Name \(required\)/i);
  await userEvent.type(nameInput, "Test");

  const stepsInput = screen.getByLabelText(/^Steps/i);
  await userEvent.clear(stepsInput);
  await userEvent.type(stepsInput, '{"not": "an array"}');

  const createButton = screen.getByRole("button", { name: /^Create$/i });
  await userEvent.click(createButton);

  // Validation should prevent the service call
  await waitFor(() => {
    expect(createPlaybookDefinition).not.toHaveBeenCalled();
  });
  
  // Form should still be visible with error
  expect(screen.getByText(/create new playbook definition/i)).toBeInTheDocument();
});

test("super admin can submit valid create form", async () => {
  listPlaybooks.mockResolvedValue({ items: [], limit: 50 });
  listPlaybookExecutions.mockResolvedValue({ items: [], limit: 50 });
  createPlaybookDefinition.mockResolvedValue({ id: "new_pb", name: "New playbook" });
  listPlaybooks.mockResolvedValueOnce({ items: [], limit: 50 });
  listPlaybooks.mockResolvedValueOnce({
    items: [{ id: "new_pb", name: "New playbook" }],
    limit: 50,
  });

  render(<PlaybooksPanel {...styleProps} userRole="super_admin" />);

  const newDefButton = await screen.findByRole("button", { name: /\+ New Definition/i });
  await userEvent.click(newDefButton);

  const idInput = screen.getByLabelText(/^ID \(required\)/i);
  await userEvent.type(idInput, "new_pb");

  const nameInput = screen.getByLabelText(/^Name \(required\)/i);
  await userEvent.type(nameInput, "New playbook");

  const createButton = screen.getByRole("button", { name: /^Create$/i });
  await userEvent.click(createButton);

  await waitFor(() => {
    expect(createPlaybookDefinition).toHaveBeenCalledWith(
      expect.objectContaining({
        id: "new_pb",
        name: "New playbook",
      })
    );
  });
});

test("super admin can submit valid edit form", async () => {
  listPlaybooks.mockResolvedValue({ items: [defRow], limit: 50 });
  listPlaybookExecutions.mockResolvedValue({ items: [], limit: 50 });
  updatePlaybookDefinition.mockResolvedValue({ id: "pb_one", name: "Updated" });
  listPlaybooks.mockResolvedValueOnce({ items: [defRow], limit: 50 });
  listPlaybooks.mockResolvedValueOnce({
    items: [{ ...defRow, name: "Updated" }],
    limit: 50,
  });

  render(<PlaybooksPanel {...styleProps} userRole="super_admin" />);
  await screen.findByText("pb_one");

  const editButton = screen.getByRole("button", { name: /^Edit$/i });
  await userEvent.click(editButton);

  const nameInput = screen.getByLabelText(/^Name \(required\)/i);
  await userEvent.clear(nameInput);
  await userEvent.type(nameInput, "Updated");

  const updateButton = screen.getByRole("button", { name: /^Update$/i });
  await userEvent.click(updateButton);

  await waitFor(() => {
    expect(updatePlaybookDefinition).toHaveBeenCalledWith(
      "pb_one",
      expect.objectContaining({
        name: "Updated",
      })
    );
  });
});

test("super admin can toggle definition enabled status", async () => {
  listPlaybooks.mockResolvedValue({ items: [defRow], limit: 50 });
  listPlaybookExecutions.mockResolvedValue({ items: [], limit: 50 });
  setPlaybookDefinitionEnabled.mockResolvedValue({ id: "pb_one", enabled: false });
  listPlaybooks.mockResolvedValueOnce({ items: [defRow], limit: 50 });
  listPlaybooks.mockResolvedValueOnce({
    items: [{ ...defRow, enabled: false }],
    limit: 50,
  });

  render(<PlaybooksPanel {...styleProps} userRole="super_admin" />);
  await screen.findByText("pb_one");

  const disableButton = screen.getByRole("button", { name: /^Disable$/i });
  await userEvent.click(disableButton);

  await waitFor(() => {
    expect(setPlaybookDefinitionEnabled).toHaveBeenCalledWith("pb_one", false);
  });
});

test("shows success message after successful create", async () => {
  listPlaybooks.mockResolvedValue({ items: [], limit: 50 });
  listPlaybookExecutions.mockResolvedValue({ items: [], limit: 50 });
  createPlaybookDefinition.mockResolvedValue({ id: "new_pb", name: "New playbook" });
  listPlaybooks.mockResolvedValueOnce({ items: [], limit: 50 });
  listPlaybooks.mockResolvedValueOnce({
    items: [{ id: "new_pb", name: "New playbook" }],
    limit: 50,
  });

  render(<PlaybooksPanel {...styleProps} userRole="super_admin" />);

  const newDefButton = await screen.findByRole("button", { name: /\+ New Definition/i });
  await userEvent.click(newDefButton);

  const idInput = screen.getByLabelText(/^ID \(required\)/i);
  await userEvent.type(idInput, "new_pb");

  const nameInput = screen.getByLabelText(/^Name \(required\)/i);
  await userEvent.type(nameInput, "New playbook");

  const createButton = screen.getByRole("button", { name: /^Create$/i });
  await userEvent.click(createButton);

  await waitFor(() => {
    expect(screen.getByText(/Created playbook "New playbook"/i)).toBeInTheDocument();
  });
});
