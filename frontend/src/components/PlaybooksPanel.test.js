import React from "react";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
  retryExecution,
  abandonExecution,
  resumeExecution,
  listPlaybookSchedules,
  getPlaybookSchedule,
} from "../services/playbookService";
import { listDeadLetters } from "../services/deadLetterService";
import { listNotificationDeliveries } from "../services/notificationDeliveryService";

jest.mock("../services/playbookService", () => ({
  listPlaybooks: jest.fn(),
  getPlaybook: jest.fn(),
  listPlaybookExecutions: jest.fn(),
  getPlaybookExecution: jest.fn(),
  createPlaybookDefinition: jest.fn(),
  updatePlaybookDefinition: jest.fn(),
  setPlaybookDefinitionEnabled: jest.fn(),
  retryExecution: jest.fn(),
  abandonExecution: jest.fn(),
  resumeExecution: jest.fn(),
  listPlaybookSchedules: jest.fn(),
  getPlaybookSchedule: jest.fn(),
}));

jest.mock("../services/notificationDeliveryService", () => ({
  listNotificationDeliveries: jest.fn(),
}));

jest.mock("../services/deadLetterService", () => ({
  listDeadLetters: jest.fn(),
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

const scheduleRow = {
  id: 7,
  playbook_id: "pb_one",
  enabled: true,
  paused: false,
  schedule_expression: "0 */6 * * *",
  missed_run_policy: "skip",
  last_run_at: "2026-05-09T06:00:00Z",
  next_run_at: "2026-05-09T12:00:00Z",
  timezone: "UTC",
  max_catchup_runs: 1,
  max_concurrent_runs: 1,
  created_at: "2026-05-08T12:00:00Z",
  updated_at: "2026-05-09T08:00:00Z",
};

beforeEach(() => {
  jest.clearAllMocks();
  listPlaybookSchedules.mockResolvedValue({ items: [], limit: 50 });
  listNotificationDeliveries.mockResolvedValue({ items: [], limit: 100, offset: 0 });
  listDeadLetters.mockResolvedValue({ items: [], limit: 1, offset: 0 });
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

test("renders metadata-only schedules after switching panel", async () => {
  listPlaybooks.mockResolvedValue({ items: [defRow], limit: 50 });
  listPlaybookExecutions.mockResolvedValue({ items: [], limit: 50 });
  listPlaybookSchedules.mockResolvedValue({ items: [scheduleRow], limit: 50 });

  render(<PlaybooksPanel {...styleProps} />);
  await screen.findByText("pb_one");
  await userEvent.click(screen.getByRole("button", { name: /^schedules$/i }));

  expect(await screen.findByText(/schedules are metadata-only/i)).toBeInTheDocument();
  expect(screen.getByRole("columnheader", { name: /^missed-run policy$/i })).toBeInTheDocument();
  expect(screen.getByText("7")).toBeInTheDocument();
  expect(screen.getByText("0 */6 * * *")).toBeInTheDocument();
  expect(screen.getByText("skip")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /create|edit|delete|pause|resume|run now/i })).not.toBeInTheDocument();
});

test("schedule empty state when no metadata exists", async () => {
  listPlaybooks.mockResolvedValue({ items: [defRow], limit: 50 });
  listPlaybookExecutions.mockResolvedValue({ items: [], limit: 50 });
  listPlaybookSchedules.mockResolvedValue({ items: [], limit: 50 });

  render(<PlaybooksPanel {...styleProps} />);
  await screen.findByText("pb_one");
  await userEvent.click(screen.getByRole("button", { name: /^schedules$/i }));

  expect(await screen.findByText(/no playbook schedules found/i)).toBeInTheDocument();
});

test("schedule load error does not break definitions", async () => {
  listPlaybooks.mockResolvedValue({ items: [defRow], limit: 50 });
  listPlaybookExecutions.mockResolvedValue({ items: [], limit: 50 });
  listPlaybookSchedules.mockRejectedValue(new Error("schedule fail"));

  render(<PlaybooksPanel {...styleProps} />);
  expect(await screen.findByText("pb_one")).toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: /^schedules$/i }));
  expect(await screen.findByText(/schedule fail/i)).toBeInTheDocument();
});

test("view schedule calls getPlaybookSchedule and shows allowlisted detail", async () => {
  listPlaybooks.mockResolvedValue({ items: [defRow], limit: 50 });
  listPlaybookExecutions.mockResolvedValue({ items: [], limit: 50 });
  listPlaybookSchedules.mockResolvedValue({ items: [scheduleRow], limit: 50 });
  getPlaybookSchedule.mockResolvedValue({
    ...scheduleRow,
    last_success_at: "2026-05-09T06:05:00Z",
    last_failure_at: null,
    last_scheduled_execution_id: 55,
    metadata: {
      owner: "secops",
      ticket_id: "SOAR-12",
      secret_token: "do-not-render",
    },
  });

  render(<PlaybooksPanel {...styleProps} userRole="super_admin" />);
  await screen.findByText("pb_one");
  await userEvent.click(screen.getByRole("button", { name: /^schedules$/i }));
  await screen.findByText("0 */6 * * *");

  const viewButtons = screen.getAllByRole("button", { name: /^view$/i });
  await userEvent.click(viewButtons[viewButtons.length - 1]);

  await waitFor(() => {
    expect(getPlaybookSchedule).toHaveBeenCalledWith(7);
  });
  expect(await screen.findByText(/schedule detail/i)).toBeInTheDocument();
  expect(screen.getByText(/metadata-only schedule visibility/i)).toBeInTheDocument();
  expect(screen.getByText(/^schedule expression$/i)).toBeInTheDocument();
  expect(screen.getByText(/^safe metadata$/i)).toBeInTheDocument();
  expect(screen.getByText("secops")).toBeInTheDocument();
  expect(screen.getByText("SOAR-12")).toBeInTheDocument();
  expect(screen.queryByText(/do-not-render/i)).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /create|edit|delete|pause|resume|run now/i })).not.toBeInTheDocument();
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

test("execution detail fetches notification deliveries and renders safe fields", async () => {
  listPlaybooks.mockResolvedValue({ items: [defRow], limit: 50 });
  listPlaybookExecutions.mockResolvedValue({ items: [execRow], limit: 50 });
  getPlaybookExecution.mockResolvedValue({
    ...execRow,
    steps_log: [],
  });
  listNotificationDeliveries.mockResolvedValue({
    items: [
      {
        id: 7,
        correlation_id: "corr-xyz",
        idempotency_key: "idem-1",
        provider: "slack",
        mode: "simulation",
        status: "success",
        playbook_execution_id: 42,
        playbook_step_index: 0,
        incident_id: null,
        approval_request_id: null,
        alert_id: null,
        adapter_name: "slack",
        action: "send_message",
        requested_at: "2026-05-09T12:00:00Z",
        started_at: "2026-05-09T12:00:01Z",
        completed_at: "2026-05-09T12:00:02Z",
        created_at: "2026-05-09T12:00:02Z",
        failure_code: null,
        failure_message: null,
        timeout_seconds: 30,
        circuit_breaker_state: "closed",
        metadata: { channel_label: "#soc" },
      },
    ],
    limit: 50,
    offset: 0,
  });

  render(<PlaybooksPanel {...styleProps} />);
  await screen.findByText("pb_one");
  await userEvent.click(screen.getByRole("button", { name: /^executions$/i }));
  await screen.findByText("42");
  const viewButtons = screen.getAllByRole("button", { name: /^view$/i });
  await userEvent.click(viewButtons[viewButtons.length - 1]);

  await waitFor(() => {
    expect(listNotificationDeliveries).toHaveBeenCalledWith({
      playbook_execution_id: 42,
      limit: 50,
    });
  });

  expect(screen.getByText(/notification delivery history/i)).toBeInTheDocument();
  expect(screen.getByText(/operational evidence only/i)).toBeInTheDocument();
  expect(screen.getByText(/delivery #7/i)).toBeInTheDocument();
  expect(screen.getByText("corr-xyz")).toBeInTheDocument();
  expect(screen.getByText(/slack \/ simulation/i)).toBeInTheDocument();
  expect(screen.getByText(/send_message/i)).toBeInTheDocument();
  expect(screen.getByText(/^closed$/i)).toBeInTheDocument();
  expect(screen.getByText("30")).toBeInTheDocument();
  expect(screen.getByText("#soc")).toBeInTheDocument();
});

test("execution detail fetches and renders linked dead letter summary", async () => {
  listPlaybooks.mockResolvedValue({ items: [defRow], limit: 50 });
  listPlaybookExecutions.mockResolvedValue({ items: [execRow], limit: 50 });
  getPlaybookExecution.mockResolvedValue({ ...execRow, status: "failed", steps_log: [] });
  listDeadLetters.mockResolvedValue({
    items: [
      {
        id: 11,
        status: "open",
        failure_class: "adapter_failed",
        source_type: "playbook_execution",
        retry_count: 2,
        created_at: "2026-05-09T12:05:00Z",
      },
    ],
    limit: 1,
    offset: 0,
  });

  render(<PlaybooksPanel {...styleProps} />);
  await screen.findByText("pb_one");
  await userEvent.click(screen.getByRole("button", { name: /^executions$/i }));
  await screen.findByText("42");

  const viewButtons = screen.getAllByRole("button", { name: /^view$/i });
  await userEvent.click(viewButtons[viewButtons.length - 1]);

  await waitFor(() => {
    expect(listDeadLetters).toHaveBeenCalledWith({
      execution_id: 42,
      limit: 1,
    });
  });

  expect(await screen.findByText(/dead letter review/i)).toBeInTheDocument();
  expect(screen.getByText(/dead letter #11/i)).toBeInTheDocument();
  expect(screen.getByText("adapter_failed")).toBeInTheDocument();
  expect(screen.getByText("playbook_execution")).toBeInTheDocument();
  expect(screen.getByText("2")).toBeInTheDocument();
  expect(screen.getByText(/soar operations \/ dead letters panel/i)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /dismiss|retry request|retry execute/i })).not.toBeInTheDocument();
});

test("execution detail omits dead letter section when none exist", async () => {
  listPlaybooks.mockResolvedValue({ items: [defRow], limit: 50 });
  listPlaybookExecutions.mockResolvedValue({ items: [execRow], limit: 50 });
  getPlaybookExecution.mockResolvedValue({ ...execRow, steps_log: [] });
  listDeadLetters.mockResolvedValue({ items: [], limit: 1, offset: 0 });

  render(<PlaybooksPanel {...styleProps} />);
  await screen.findByText("pb_one");
  await userEvent.click(screen.getByRole("button", { name: /^executions$/i }));
  await screen.findByText("42");

  const viewButtons = screen.getAllByRole("button", { name: /^view$/i });
  await userEvent.click(viewButtons[viewButtons.length - 1]);

  await waitFor(() => {
    expect(listDeadLetters).toHaveBeenCalledWith({
      execution_id: 42,
      limit: 1,
    });
  });
  expect(screen.queryByText(/dead letter review/i)).not.toBeInTheDocument();
});

test("dead letter fetch failure does not break execution detail", async () => {
  listPlaybooks.mockResolvedValue({ items: [defRow], limit: 50 });
  listPlaybookExecutions.mockResolvedValue({ items: [execRow], limit: 50 });
  getPlaybookExecution.mockResolvedValue({ ...execRow, alert_id: 99, steps_log: [] });
  listDeadLetters.mockRejectedValue(new Error("Dead letters unavailable"));

  render(<PlaybooksPanel {...styleProps} />);
  await screen.findByText("pb_one");
  await userEvent.click(screen.getByRole("button", { name: /^executions$/i }));
  await screen.findByText("42");

  const viewButtons = screen.getAllByRole("button", { name: /^view$/i });
  await userEvent.click(viewButtons[viewButtons.length - 1]);

  expect(await screen.findByText(/^execution id$/i)).toBeInTheDocument();
  expect(screen.getByText("99")).toBeInTheDocument();
  expect(await screen.findByText(/dead letter lookup unavailable/i)).toBeInTheDocument();
  expect(screen.getByText(/dead letters unavailable/i)).toBeInTheDocument();
});

test("execution detail renders worker lease and recovery fields when present", async () => {
  listPlaybooks.mockResolvedValue({ items: [defRow], limit: 50 });
  listPlaybookExecutions.mockResolvedValue({ items: [execRow], limit: 50 });
  getPlaybookExecution.mockResolvedValue({
    ...execRow,
    steps_log: [],
    lease_owner: "host:123:abc",
    lease_acquired_at: "2026-05-09T12:01:00Z",
    lease_heartbeat_at: "2026-05-09T12:02:00Z",
    lease_expires_at: "2026-05-09T12:03:00Z",
    recovery_count: 3,
  });

  render(<PlaybooksPanel {...styleProps} />);
  await screen.findByText("pb_one");
  await userEvent.click(screen.getByRole("button", { name: /^executions$/i }));
  await screen.findByText("42");

  const viewButtons = screen.getAllByRole("button", { name: /^view$/i });
  await userEvent.click(viewButtons[viewButtons.length - 1]);

  expect(await screen.findByText(/worker lease \/ recovery/i)).toBeInTheDocument();
  expect(screen.getByText(/^lease owner$/i)).toBeInTheDocument();
  expect(screen.getByText("host:123:abc")).toBeInTheDocument();
  expect(screen.getByText(/^lease acquired$/i)).toBeInTheDocument();
  expect(screen.getByText(/^lease heartbeat$/i)).toBeInTheDocument();
  expect(screen.getByText(/^lease expires$/i)).toBeInTheDocument();
  expect(screen.getByText(/^recovery count$/i)).toBeInTheDocument();
  expect(screen.getByText("3")).toBeInTheDocument();
});

test("execution detail hides worker lease section when lease fields are absent", async () => {
  listPlaybooks.mockResolvedValue({ items: [defRow], limit: 50 });
  listPlaybookExecutions.mockResolvedValue({ items: [execRow], limit: 50 });
  getPlaybookExecution.mockResolvedValue({ ...execRow, steps_log: [] });

  render(<PlaybooksPanel {...styleProps} />);
  await screen.findByText("pb_one");
  await userEvent.click(screen.getByRole("button", { name: /^executions$/i }));
  await screen.findByText("42");

  const viewButtons = screen.getAllByRole("button", { name: /^view$/i });
  await userEvent.click(viewButtons[viewButtons.length - 1]);

  expect(await screen.findByText(/^execution id$/i)).toBeInTheDocument();
  expect(screen.queryByText(/worker lease \/ recovery/i)).not.toBeInTheDocument();
});

test("execution detail still shows core fields when notification deliveries fail to load", async () => {
  listPlaybooks.mockResolvedValue({ items: [defRow], limit: 50 });
  listPlaybookExecutions.mockResolvedValue({ items: [execRow], limit: 50 });
  getPlaybookExecution.mockResolvedValue({
    ...execRow,
    alert_id: 99,
    steps_log: [],
  });
  listNotificationDeliveries.mockRejectedValue(new Error("Delivery service unavailable"));

  render(<PlaybooksPanel {...styleProps} />);
  await screen.findByText("pb_one");
  await userEvent.click(screen.getByRole("button", { name: /^executions$/i }));
  await screen.findByText("42");
  const viewButtons = screen.getAllByRole("button", { name: /^view$/i });
  await userEvent.click(viewButtons[viewButtons.length - 1]);

  expect(await screen.findByText("Delivery service unavailable")).toBeInTheDocument();
  expect(screen.getByText(/^execution id$/i)).toBeInTheDocument();
  expect(screen.getByText("99")).toBeInTheDocument();
});

test("execution detail omits unsafe delivery metadata keys from UI", async () => {
  listPlaybooks.mockResolvedValue({ items: [defRow], limit: 50 });
  listPlaybookExecutions.mockResolvedValue({ items: [execRow], limit: 50 });
  getPlaybookExecution.mockResolvedValue({ ...execRow, steps_log: [] });
  listNotificationDeliveries.mockResolvedValue({
    items: [
      {
        id: 8,
        correlation_id: "c8",
        idempotency_key: "i8",
        provider: "teams",
        mode: "real",
        status: "failed",
        playbook_execution_id: 42,
        playbook_step_index: null,
        incident_id: null,
        approval_request_id: null,
        alert_id: null,
        adapter_name: "teams",
        action: "send_message",
        requested_at: "2026-05-09T12:00:00Z",
        started_at: null,
        completed_at: "2026-05-09T12:00:05Z",
        created_at: "2026-05-09T12:00:05Z",
        failure_code: "network_error",
        failure_message: "bad https://hooks.example.test/x",
        timeout_seconds: null,
        circuit_breaker_state: "open",
        metadata: {
          ok: true,
          slack_webhook_url: "https://hooks.slack.com/secret",
        },
      },
    ],
    limit: 50,
    offset: 0,
  });

  render(<PlaybooksPanel {...styleProps} />);
  await screen.findByText("pb_one");
  await userEvent.click(screen.getByRole("button", { name: /^executions$/i }));
  await screen.findByText("42");
  const viewButtons = screen.getAllByRole("button", { name: /^view$/i });
  await userEvent.click(viewButtons[viewButtons.length - 1]);

  await waitFor(() => {
    expect(screen.getByText(/delivery #8/i)).toBeInTheDocument();
  });
  expect(screen.queryByText(/slack_webhook_url/i)).not.toBeInTheDocument();
  expect(screen.queryByText(/hooks\.slack\.com/i)).not.toBeInTheDocument();
  expect(screen.getByText("[REDACTED_URL]")).toBeInTheDocument();
  expect(screen.getByText(/teams \/ real/i)).toBeInTheDocument();
  expect(screen.getByText("Safe metadata")).toBeInTheDocument();
  expect(screen.getByText("Yes")).toBeInTheDocument();
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

test("execution detail renders adapter-backed simulated output", async () => {
  listPlaybooks.mockResolvedValue({ items: [defRow], limit: 50 });
  listPlaybookExecutions.mockResolvedValue({
    items: [{ ...execRow, status: "success" }],
    limit: 50,
  });
  getPlaybookExecution.mockResolvedValue({
    ...execRow,
    status: "success",
    steps_log: [
      {
        step_index: 0,
        action: "notify_slack",
        status: "success",
        simulated: true,
        executed: false,
        message: "Simulated adapter action completed.",
        output: {
          simulated: true,
          executed: false,
          adapter_result: {
            adapter: "slack",
            action: "send_message",
            mode: "simulation",
            simulated: true,
            executed: false,
            success: true,
            message: "Simulated slack action.",
            metadata: { delivery: "not_sent", channel: "#secops" },
          },
        },
      },
      {
        step_index: 1,
        action: "block_ip",
        status: "success",
        simulated: true,
        executed: false,
        output: {
          simulated: true,
          executed: false,
          adapter_result: {
            adapter: "firewall",
            action: "block_ip",
            mode: "simulation",
            simulated: true,
            executed: false,
            success: true,
            message: "Simulated firewall action.",
            metadata: { mutation: "none", target: "203.0.113.10" },
          },
        },
      },
    ],
  });

  render(<PlaybooksPanel {...styleProps} />);
  await screen.findByText("pb_one");
  await userEvent.click(screen.getByRole("button", { name: /^executions$/i }));
  await screen.findByText("42");

  const viewButtons = screen.getAllByRole("button", { name: /^view$/i });
  await userEvent.click(viewButtons[viewButtons.length - 1]);

  expect(await screen.findAllByText(/simulated adapter output/i)).toHaveLength(2);
  expect(screen.getAllByText(/^adapter$/i).length).toBeGreaterThan(0);
  expect(screen.getByText("slack")).toBeInTheDocument();
  expect(screen.getByText("firewall")).toBeInTheDocument();
  expect(screen.getAllByText(/^adapter action$/i).length).toBeGreaterThan(0);
  expect(screen.getByText("send_message")).toBeInTheDocument();
  expect(screen.getAllByText("block_ip").length).toBeGreaterThan(0);
  expect(screen.getAllByText(/^success$/i).length).toBeGreaterThan(0);
  expect(screen.getAllByText(/^simulated$/i).length).toBeGreaterThan(0);
  expect(screen.getAllByText(/^executed$/i).length).toBeGreaterThan(0);
  expect(screen.getAllByText(/^yes$/i).length).toBeGreaterThan(0);
  expect(screen.getAllByText(/^no$/i).length).toBeGreaterThan(0);
  expect(screen.getByText("Simulated slack action.")).toBeInTheDocument();
  expect(screen.getByText("Simulated firewall action.")).toBeInTheDocument();
  expect(screen.getAllByText(/^metadata$/i).length).toBeGreaterThan(0);
  expect(screen.getByText(/^delivery$/i)).toBeInTheDocument();
  expect(screen.getByText("not_sent")).toBeInTheDocument();
  expect(screen.getByText(/^mutation$/i)).toBeInTheDocument();
  expect(screen.getByText("none")).toBeInTheDocument();
  expect(screen.queryByText(/real firewall/i)).not.toBeInTheDocument();
  expect(screen.queryByText(/real remediation/i)).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /run|retry|cancel|resume|approve|deny/i })).not.toBeInTheDocument();
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

test("execution detail highlights awaiting approval gate context", async () => {
  listPlaybooks.mockResolvedValue({ items: [defRow], limit: 50 });
  listPlaybookExecutions.mockResolvedValue({
    items: [{ ...execRow, status: "awaiting_approval" }],
    limit: 50,
  });
  getPlaybookExecution.mockResolvedValue({
    ...execRow,
    status: "awaiting_approval",
    steps_log: [
      {
        step_index: 0,
        action: "require_approval",
        status: "awaiting_approval",
        event: "approval_requested",
        mode: "simulation",
        simulated: true,
        executed: false,
        approval_request_id: 901,
        approval_status: "pending",
        risk_level: "high",
        message: "Approval requested before simulated containment.",
      },
    ],
  });

  render(<PlaybooksPanel {...styleProps} />);
  await screen.findByText("pb_one");
  await userEvent.click(screen.getByRole("button", { name: /^executions$/i }));
  await screen.findByText("42");

  const viewButtons = screen.getAllByRole("button", { name: /^view$/i });
  await userEvent.click(viewButtons[viewButtons.length - 1]);

  expect(
    await screen.findByText(
      "Approval-gated simulation paused; no later steps will run until approval."
    )
  ).toBeInTheDocument();
  expect(screen.getByText("Approval requested")).toBeInTheDocument();
  expect(screen.getByText("require_approval")).toBeInTheDocument();
  expect(screen.getByText(/^approval request id$/i)).toBeInTheDocument();
  expect(screen.getAllByText("901").length).toBeGreaterThan(0);
  expect(screen.getByText(/^approval status$/i)).toBeInTheDocument();
  expect(screen.getAllByText("pending").length).toBeGreaterThan(0);
  expect(screen.getByText(/^risk level$/i)).toBeInTheDocument();
  expect(screen.getAllByText("high").length).toBeGreaterThan(0);
  expect(screen.getByText(/^simulated$/i)).toBeInTheDocument();
  expect(screen.getAllByText(/^yes$/i).length).toBeGreaterThan(0);
  expect(screen.getByText(/^executed$/i)).toBeInTheDocument();
  expect(screen.getAllByText(/^no$/i).length).toBeGreaterThan(0);
  expect(screen.queryByRole("button", { name: /approve|deny|resume|run|retry|cancel/i })).not.toBeInTheDocument();
});

test("execution detail labels approval resume timeline events", async () => {
  listPlaybooks.mockResolvedValue({ items: [defRow], limit: 50 });
  listPlaybookExecutions.mockResolvedValue({
    items: [{ ...execRow, status: "success" }],
    limit: 50,
  });
  getPlaybookExecution.mockResolvedValue({
    ...execRow,
    status: "success",
    steps_log: [
      {
        step_index: 0,
        action: "require_approval",
        status: "success",
        event: "approval_approved",
        simulated: true,
        executed: false,
        approval_request_id: 902,
        approval_status: "approved",
        risk_level: "critical",
      },
      {
        step_index: 0,
        action: "require_approval",
        status: "success",
        event: "approval_resumed",
        simulated: true,
        executed: false,
        approval_request_id: 902,
        approval_status: "approved",
      },
    ],
  });

  render(<PlaybooksPanel {...styleProps} />);
  await screen.findByText("pb_one");
  await userEvent.click(screen.getByRole("button", { name: /^executions$/i }));
  await screen.findByText("42");

  const viewButtons = screen.getAllByRole("button", { name: /^view$/i });
  await userEvent.click(viewButtons[viewButtons.length - 1]);

  expect(await screen.findByText("Approval approved")).toBeInTheDocument();
  expect(screen.getByText("Simulation resumed")).toBeInTheDocument();
  expect(screen.getAllByText("approved").length).toBeGreaterThan(0);
  expect(screen.queryByText(/no later steps will run until approval/i)).not.toBeInTheDocument();
});

test("execution detail labels denied expired skipped and aborted approval outcomes", async () => {
  listPlaybooks.mockResolvedValue({ items: [defRow], limit: 50 });
  listPlaybookExecutions.mockResolvedValue({
    items: [{ ...execRow, status: "failed" }],
    limit: 50,
  });
  getPlaybookExecution.mockResolvedValue({
    ...execRow,
    status: "failed",
    steps_log: [
      {
        step_index: 0,
        action: "require_approval",
        status: "failed",
        event: "approval_denied",
        simulated: true,
        executed: false,
        approval_status: "denied",
        risk_level: "critical",
      },
      {
        step_index: 1,
        action: "block_ip",
        status: "skipped",
        event: "skipped_after_approval_gate",
        simulated: true,
        executed: false,
        output: { skip_reason: "approval_denied" },
      },
      {
        step_index: 2,
        action: "require_approval",
        status: "failed",
        event: "approval_expired",
        simulated: true,
        executed: false,
        approval_status: "expired",
      },
      {
        step_index: 3,
        action: "notify_owner",
        status: "aborted",
        simulated: true,
        executed: false,
        reason: "approval_expired",
      },
    ],
  });

  render(<PlaybooksPanel {...styleProps} />);
  await screen.findByText("pb_one");
  await userEvent.click(screen.getByRole("button", { name: /^executions$/i }));
  await screen.findByText("42");

  const viewButtons = screen.getAllByRole("button", { name: /^view$/i });
  await userEvent.click(viewButtons[viewButtons.length - 1]);

  expect(await screen.findByText("Approval denied")).toBeInTheDocument();
  expect(screen.getByText("Skipped after approval gate")).toBeInTheDocument();
  expect(screen.getByText("Approval expired")).toBeInTheDocument();
  expect(screen.getByText("Aborted")).toBeInTheDocument();
  expect(screen.getAllByText(/^skip reason$/i).length).toBeGreaterThan(0);
  expect(screen.getAllByText("approval_denied").length).toBeGreaterThan(0);
  expect(screen.getAllByText("expired").length).toBeGreaterThan(0);
  expect(screen.getAllByText(/^no$/i).length).toBeGreaterThan(0);
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

test("super admin sees valid simulation controls by execution state", async () => {
  listPlaybooks.mockResolvedValue({ items: [defRow], limit: 50 });
  listPlaybookExecutions.mockResolvedValue({
    items: [
      { ...execRow, id: 41, status: "failed" },
      { ...execRow, id: 42, status: "abandoned" },
      { ...execRow, id: 43, status: "pending" },
      { ...execRow, id: 44, status: "running" },
      { ...execRow, id: 45, status: "awaiting_approval" },
      { ...execRow, id: 46, status: "success" },
    ],
    limit: 50,
  });

  render(<PlaybooksPanel {...styleProps} userRole="super_admin" />);
  await screen.findByText("pb_one");
  await userEvent.click(screen.getByRole("button", { name: /^executions$/i }));

  expect(await screen.findAllByRole("button", { name: /^retry simulation$/i })).toHaveLength(2);
  expect(screen.getAllByRole("button", { name: /^abandon$/i })).toHaveLength(3);
  expect(screen.getByRole("button", { name: /^resume simulation$/i })).toBeInTheDocument();
});

test("retry simulation control calls service and refreshes executions", async () => {
  listPlaybooks.mockResolvedValue({ items: [defRow], limit: 50 });
  listPlaybookExecutions.mockResolvedValue({ items: [{ ...execRow, status: "failed" }], limit: 50 });
  retryExecution.mockResolvedValue({ new_execution_id: 99, status: "pending" });

  render(<PlaybooksPanel {...styleProps} userRole="super_admin" />);
  await screen.findByText("pb_one");
  await userEvent.click(screen.getByRole("button", { name: /^executions$/i }));

  await userEvent.click(await screen.findByRole("button", { name: /^retry simulation$/i }));

  await waitFor(() => {
    expect(retryExecution).toHaveBeenCalledWith(42);
  });
  expect(listPlaybookExecutions.mock.calls.length).toBeGreaterThan(1);
});

test("abandon simulation control requires confirmation", async () => {
  listPlaybooks.mockResolvedValue({ items: [defRow], limit: 50 });
  listPlaybookExecutions.mockResolvedValue({ items: [execRow], limit: 50 });
  abandonExecution.mockResolvedValue({ outcome: "abandoned" });
  const confirmSpy = jest.spyOn(window, "confirm").mockReturnValue(true);

  try {
    render(<PlaybooksPanel {...styleProps} userRole="super_admin" />);
    await screen.findByText("pb_one");
    await userEvent.click(screen.getByRole("button", { name: /^executions$/i }));

    await userEvent.click(await screen.findByRole("button", { name: /^abandon$/i }));

    await waitFor(() => {
      expect(abandonExecution).toHaveBeenCalledWith(42);
    });
    expect(confirmSpy).toHaveBeenCalledWith(
      "Abandon this execution? It will stop and cannot be resumed."
    );
  } finally {
    confirmSpy.mockRestore();
  }
});

test("resume simulation control calls service", async () => {
  listPlaybooks.mockResolvedValue({ items: [defRow], limit: 50 });
  listPlaybookExecutions.mockResolvedValue({
    items: [{ ...execRow, status: "awaiting_approval" }],
    limit: 50,
  });
  resumeExecution.mockResolvedValue({ status: "pending" });

  render(<PlaybooksPanel {...styleProps} userRole="super_admin" />);
  await screen.findByText("pb_one");
  await userEvent.click(screen.getByRole("button", { name: /^executions$/i }));

  await userEvent.click(await screen.findByRole("button", { name: /^resume simulation$/i }));

  await waitFor(() => {
    expect(resumeExecution).toHaveBeenCalledWith(42);
  });
});

test("control action error is shown per row", async () => {
  listPlaybooks.mockResolvedValue({ items: [defRow], limit: 50 });
  listPlaybookExecutions.mockResolvedValue({ items: [{ ...execRow, status: "failed" }], limit: 50 });
  retryExecution.mockRejectedValue(new Error("active execution already exists"));

  render(<PlaybooksPanel {...styleProps} userRole="super_admin" />);
  await screen.findByText("pb_one");
  await userEvent.click(screen.getByRole("button", { name: /^executions$/i }));

  await userEvent.click(await screen.findByRole("button", { name: /^retry simulation$/i }));

  expect(await screen.findByText(/active execution already exists/i)).toBeInTheDocument();
});

test("shows visibility-only notice", async () => {
  listPlaybooks.mockResolvedValue({ items: [], limit: 50 });
  listPlaybookExecutions.mockResolvedValue({ items: [], limit: 50 });

  render(<PlaybooksPanel {...styleProps} userRole="analyst" />);

  expect(
    await screen.findByText(/simulation-only playbook controls/i)
  ).toBeInTheDocument();
  expect(screen.getByText(/analyst users have read-only access/i)).toBeInTheDocument();
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
  fireEvent.change(triggerInput, { target: { value: '["not", "an", "object"]' } });

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
  fireEvent.change(stepsInput, { target: { value: '{"not": "an array"}' } });

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
