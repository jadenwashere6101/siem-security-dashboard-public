import React from "react";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import DeadLettersPanel from "./DeadLettersPanel";
import {
  dismissDeadLetter,
  executeDeadLetterRetry,
  getDeadLetter,
  getDeadLetterMetrics,
  getDeadLetters,
  requestDeadLetterRetry,
} from "../services/deadLetterService";
import { loadSoarOperationsSummary } from "../services/soarOperationsService";

jest.mock("../services/deadLetterService", () => ({
  dismissDeadLetter: jest.fn(),
  executeDeadLetterRetry: jest.fn(),
  getDeadLetter: jest.fn(),
  getDeadLetterMetrics: jest.fn(),
  getDeadLetters: jest.fn(),
  requestDeadLetterRetry: jest.fn(),
}));

jest.mock("../services/soarOperationsService", () => ({
  loadSoarOperationsSummary: jest.fn(),
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

const summaryFixture = {
  window_hours: 24,
  counts: {
    running_playbooks: 1,
    awaiting_approval_playbooks: 1,
    active_playbooks: 2,
    pending_approvals: 1,
    recently_expired_denied: 2,
    failed_executions: 1,
    actionable_dead_letters: 2,
  },
  running_playbooks: {
    count: 2,
    running_count: 1,
    awaiting_approval_count: 1,
    items: [
      {
        execution_id: 42,
        playbook_id: "pb_test",
        status: "running",
        alert_id: 10,
        created_at: "2026-05-10T10:00:00Z",
        completed_at: null,
      },
    ],
  },
  pending_approvals: {
    count: 1,
    items: [
      {
        approval_id: 301,
        status: "pending",
        action: "block_ip",
        risk_level: "high",
        incident_id: 5,
        alert_id: 10,
        playbook_execution_id: 42,
        created_at: "2026-05-10T10:15:00Z",
      },
    ],
  },
  recently_expired_denied: {
    count: 2,
    window_hours: 24,
    items: [
      {
        approval_id: 302,
        status: "expired",
        action: "block_ip",
        risk_level: "medium",
        incident_id: 5,
        alert_id: 10,
        playbook_execution_id: 42,
        execution_status: "not_actioned",
        expires_at: "2026-05-10T11:00:00Z",
      },
      {
        approval_id: 303,
        status: "denied",
        action: "block_ip",
        risk_level: "high",
        incident_id: 6,
        alert_id: 11,
        playbook_execution_id: 43,
        execution_status: "not_actioned",
        decided_at: "2026-05-10T11:10:00Z",
      },
    ],
  },
  failed_executions: {
    count: 1,
    items: [
      {
        execution_id: 55,
        playbook_id: "pb_test",
        status: "failed",
        alert_id: 12,
        completed_at: "2026-05-10T11:20:00Z",
        failure_reason: "Adapter failed",
      },
    ],
  },
  actionable_dead_letters: {
    count: 2,
    open_count: 2,
    items: [
      {
        dead_letter_id: 7,
        status: "open",
        source_type: "approval",
        failure_class: "approval_expired",
        created_at: "2026-05-10T10:30:00Z",
        classification: { kind: "expected_expiration", label: "Expected expiration" },
      },
      {
        dead_letter_id: 8,
        status: "open",
        source_type: "playbook_execution",
        failure_class: "adapter_failed",
        created_at: "2026-05-10T10:40:00Z",
        classification: { kind: "system_failure", label: "System failure" },
      },
    ],
  },
  legacy_expected_backlog: {
    open_count: 1,
    review_mode: "individual_reason_logged_dismissal_only",
  },
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
  retryable: true,
  error_message: "failed at [REDACTED_URL]",
  payload_json: {
    safe: "kept",
    nested: {},
    callback: "[REDACTED_URL]",
  },
  first_failed_at: "2026-05-10T09:00:00Z",
  last_failed_at: "2026-05-10T10:00:00Z",
};

const retryingPlaybookRow = {
  ...detailRow,
  status: "retrying",
  retry_requested_at: "2026-05-10T11:00:00Z",
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
  loadSoarOperationsSummary.mockResolvedValue(summaryFixture);
  getDeadLetterMetrics.mockResolvedValue(sampleMetrics);
  getDeadLetters.mockResolvedValue({ items: [listRow], limit: 100, offset: 0 });
  getDeadLetter.mockResolvedValue(detailRow);
  dismissDeadLetter.mockResolvedValue({ ...detailRow, status: "dismissed" });
  executeDeadLetterRetry.mockResolvedValue({
    dead_letter: { ...retryingPlaybookRow, status: "retried" },
    new_execution_id: 77,
    message: "New pending playbook retry execution created. No steps have run.",
  });
  requestDeadLetterRetry.mockResolvedValue({
    ...detailRow,
    status: "retrying",
    retry_requested_at: "2026-05-10T11:00:00Z",
  });
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
  expect(screen.getByRole("note")).toHaveTextContent(/does not execute playbooks/i);
  expect(screen.getByRole("note")).toHaveTextContent(/Real workflow review/i);

  expect(await screen.findByText("99")).toBeInTheDocument();
  expect(screen.getByTitle("View dead letter 7")).toBeInTheDocument();
  expect(screen.getByRole("region", { name: /running playbooks/i })).toBeInTheDocument();
});

test("renders metric cards", async () => {
  render(<DeadLettersPanel {...styleProps} />);

  await waitFor(() => {
    expect(screen.getAllByText("2").length).toBeGreaterThan(0);
    expect(screen.getAllByText("1").length).toBeGreaterThan(0);
    expect(screen.getAllByText("0").length).toBeGreaterThan(0);
  });
  expect(screen.getByText(/oldest active dead letter/i)).toBeInTheDocument();
});

test("renders SOAR operations summary cards and historical backlog note", async () => {
  render(<DeadLettersPanel {...styleProps} />);

  expect(await screen.findByRole("region", { name: /pending approvals/i })).toBeInTheDocument();
  expect(screen.getByText(/historical expected-approval backlog: 1 open dead letters/i)).toBeInTheDocument();
  expect(screen.getByText(/expired or denied approvals now end as/i)).toBeInTheDocument();
  expect(screen.getByText(/expected expiration/i)).toBeInTheDocument();
  expect(screen.getAllByText(/system failure/i).length).toBeGreaterThan(0);
});

test("summary strip navigation uses existing playbook and alert handlers", async () => {
  const onOpenPlaybookExecution = jest.fn();
  const onOpenResponseRegistry = jest.fn();
  const onOpenPendingApprovals = jest.fn();
  const onOpenPlaybooks = jest.fn();

  render(
    <DeadLettersPanel
      {...styleProps}
      onOpenPlaybookExecution={onOpenPlaybookExecution}
      onOpenResponseRegistry={onOpenResponseRegistry}
      onOpenPendingApprovals={onOpenPendingApprovals}
      onOpenPlaybooks={onOpenPlaybooks}
    />
  );

  expect(await screen.findByRole("button", { name: /open soar playbooks/i })).toBeInTheDocument();

  await userEvent.click(screen.getAllByRole("button", { name: "Execution #42" })[0]);
  expect(onOpenPlaybookExecution).toHaveBeenCalledWith(42);

  await userEvent.click(screen.getAllByRole("button", { name: "Alert #10" })[0]);
  expect(onOpenResponseRegistry).toHaveBeenCalledWith({
    relatedAlertId: 10,
    relatedIncidentId: 5,
  });

  await userEvent.click(screen.getByRole("button", { name: /open soar approvals/i }));
  expect(onOpenPendingApprovals).toHaveBeenCalled();

  await userEvent.click(screen.getAllByRole("button", { name: /open soar playbooks/i })[0]);
  expect(onOpenPlaybooks).toHaveBeenCalled();
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

  const viewButton = screen.getByTitle("View dead letter 7");
  await userEvent.click(viewButton);

  expect(await screen.findByText(/failed at \[REDACTED_URL\]/i)).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Dead Letter Detail" })).toHaveFocus();
  expect(screen.getByLabelText("Dead letter list and selected dead letter detail")).toHaveClass(
    "master-detail-layout--open"
  );
  expect(getDeadLetter).toHaveBeenCalledWith(7);
  expect(screen.getByText(/linked context/i)).toBeInTheDocument();
  expect(screen.getByText("#42")).toBeInTheDocument();
  expect(screen.getByText("#10")).toBeInTheDocument();
  expect(screen.getByText(/index 1, action notify_slack/i)).toBeInTheDocument();
  expect(screen.getByRole("complementary", { name: "Selected dead letter detail" })).toBeVisible();

  await userEvent.click(screen.getByRole("button", { name: "Close" }));
  expect(viewButton).toHaveFocus();
});

test("empty state", async () => {
  getDeadLetters.mockResolvedValue({ items: [], limit: 100, offset: 0 });

  render(<DeadLettersPanel {...styleProps} />);

  expect(
    await screen.findByText(/no dead letters found \(no filters applied\)/i)
  ).toBeInTheDocument();
});

test("empty state handles null items response", async () => {
  getDeadLetters.mockResolvedValue({ items: null, limit: 100, offset: 0 });

  render(<DeadLettersPanel {...styleProps} />);

  expect(
    await screen.findByText(/no dead letters found \(no filters applied\)/i)
  ).toBeInTheDocument();
});

test("failure class filter resets when metrics no longer include selected class", async () => {
  getDeadLetterMetrics
    .mockResolvedValueOnce(sampleMetrics)
    .mockResolvedValueOnce({
      ...sampleMetrics,
      by_failure_class: { timeout: 1 },
    });
  getDeadLetters.mockResolvedValue({ items: [listRow], limit: 100, offset: 0 });

  render(<DeadLettersPanel {...styleProps} />);

  await screen.findByText("99");
  await userEvent.selectOptions(
    screen.getByLabelText(/filter dead letters by failure class/i),
    "adapter_failed"
  );

  await waitFor(() => {
    expect(screen.getByLabelText(/filter dead letters by failure class/i)).toHaveValue(
      "adapter_failed"
    );
  });

  await userEvent.click(screen.getByRole("button", { name: /^refresh$/i }));

  await waitFor(() => {
    expect(screen.getByLabelText(/filter dead letters by failure class/i)).toHaveValue("all");
  });
});

test("error state", async () => {
  loadSoarOperationsSummary.mockRejectedValueOnce(new Error("Summary unavailable"));

  render(<DeadLettersPanel {...styleProps} />);

  expect(await screen.findByText(/error: summary unavailable/i)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();

  loadSoarOperationsSummary.mockResolvedValueOnce(summaryFixture);
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
  expect(screen.queryByRole("button", { name: /open execution/i })).not.toBeInTheDocument();
});

test("analyst sees dismiss and retry-request actions for open dead letter", async () => {
  render(<DeadLettersPanel {...styleProps} />);

  await screen.findByText("99");
  await userEvent.click(screen.getByTitle("View dead letter 7"));
  await screen.findByText(/failed at \[REDACTED_URL\]/i);

  expect(await screen.findByRole("button", { name: /^dismiss$/i })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /retry request/i })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /retry execute/i })).not.toBeInTheDocument();
});

test("retry actions are hidden when dead letter is not retryable", async () => {
  getDeadLetter.mockResolvedValue({ ...detailRow, retryable: false });

  render(<DeadLettersPanel {...styleProps} userRole="super_admin" />);

  await screen.findByText("99");
  await userEvent.click(screen.getByTitle("View dead letter 7"));
  await screen.findByText(/failed at \[REDACTED_URL\]/i);

  expect(await screen.findByRole("button", { name: /^dismiss$/i })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /retry request/i })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /retry execute/i })).not.toBeInTheDocument();
});

test("super_admin sees dismiss and retry-request actions for open dead letter", async () => {
  render(<DeadLettersPanel {...styleProps} userRole="super_admin" />);

  await screen.findByText("99");
  await userEvent.click(screen.getByTitle("View dead letter 7"));
  await screen.findByText(/failed at \[REDACTED_URL\]/i);

  expect(await screen.findByRole("button", { name: /^dismiss$/i })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /retry request/i })).toBeInTheDocument();
});

test("viewer does not see dismiss or retry-request actions", async () => {
  render(<DeadLettersPanel {...styleProps} userRole="viewer" />);

  await screen.findByText("99");
  await userEvent.click(screen.getByTitle("View dead letter 7"));
  await screen.findByText(/failed at \[REDACTED_URL\]/i);

  expect(screen.queryByRole("button", { name: /^dismiss$/i })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /retry request/i })).not.toBeInTheDocument();
  expect(screen.queryByText(/review actions/i)).not.toBeInTheDocument();
});

test("dismiss flow calls service with comment and preserves selected detail", async () => {
  getDeadLetters
    .mockResolvedValueOnce({ items: [listRow], limit: 100, offset: 0 })
    .mockResolvedValueOnce({
      items: [{ ...listRow, status: "dismissed" }],
      limit: 100,
      offset: 0,
    });

  render(<DeadLettersPanel {...styleProps} />);

  await screen.findByText("99");
  await userEvent.click(screen.getByTitle("View dead letter 7"));
  await screen.findByRole("button", { name: /^dismiss$/i });

  await userEvent.click(await screen.findByRole("button", { name: /^dismiss$/i }));
  expect(screen.getByLabelText(/dismiss comment or reason/i)).toBeInTheDocument();

  await userEvent.type(screen.getByLabelText(/dismiss comment or reason/i), "Reviewed");
  await userEvent.click(screen.getByRole("button", { name: /confirm dismiss/i }));

  await waitFor(() => {
    expect(dismissDeadLetter).toHaveBeenCalledWith(7, { comment: "Reviewed" });
  });
  expect(await screen.findByText(/dead letter dismissed/i)).toBeInTheDocument();
  expect(screen.getByText(/failed at \[REDACTED_URL\]/i)).toBeInTheDocument();
  await waitFor(() => {
    expect(getDeadLetters).toHaveBeenCalledTimes(2);
  });
});

test("retry-request flow calls service and updates status copy", async () => {
  getDeadLetters
    .mockResolvedValueOnce({ items: [listRow], limit: 100, offset: 0 })
    .mockResolvedValueOnce({
      items: [{ ...listRow, status: "retrying" }],
      limit: 100,
      offset: 0,
    });

  render(<DeadLettersPanel {...styleProps} />);

  await screen.findByText("99");
  await userEvent.click(screen.getByTitle("View dead letter 7"));
  await screen.findByRole("button", { name: /retry request/i });

  await userEvent.click(await screen.findByRole("button", { name: /retry request/i }));

  await waitFor(() => {
    expect(requestDeadLetterRetry).toHaveBeenCalledWith(7);
  });
  expect(
    await screen.findByText(/retry request recorded\. no playbook steps were executed/i)
  ).toBeInTheDocument();
  expect(screen.getByText(/retry requested at/i)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /retry request/i })).not.toBeInTheDocument();
});

test("retry-request is hidden for non-open statuses", async () => {
  getDeadLetters.mockResolvedValue({
    items: [{ ...listRow, status: "retrying" }],
    limit: 100,
    offset: 0,
  });
  getDeadLetter.mockResolvedValue({ ...detailRow, status: "retrying" });

  render(<DeadLettersPanel {...styleProps} />);

  await screen.findByText("99");
  await userEvent.click(screen.getByTitle("View dead letter 7"));
  await screen.findByText(/failed at \[REDACTED_URL\]/i);

  expect(await screen.findByRole("button", { name: /^dismiss$/i })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /retry request/i })).not.toBeInTheDocument();

  cleanup();
  jest.clearAllMocks();
  loadSoarOperationsSummary.mockResolvedValue(summaryFixture);
  getDeadLetterMetrics.mockResolvedValue(sampleMetrics);
  getDeadLetters.mockResolvedValue({
    items: [{ ...listRow, status: "retried" }],
    limit: 100,
    offset: 0,
  });
  getDeadLetter.mockResolvedValue({ ...detailRow, status: "retried" });

  render(<DeadLettersPanel {...styleProps} />);

  await screen.findByTitle("View dead letter 7");
  await userEvent.click(screen.getByTitle("View dead letter 7"));
  await screen.findByText(/failed at \[REDACTED_URL\]/i);

  expect(screen.queryByRole("button", { name: /retry request/i })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /^dismiss$/i })).not.toBeInTheDocument();
});

test("action buttons are disabled while retry request is in flight", async () => {
  let resolveRetry;
  requestDeadLetterRetry.mockImplementation(
    () =>
      new Promise((resolve) => {
        resolveRetry = resolve;
      })
  );

  render(<DeadLettersPanel {...styleProps} />);

  await screen.findByText("99");
  await userEvent.click(screen.getByTitle("View dead letter 7"));
  await screen.findByRole("button", { name: /retry request/i });

  await userEvent.click(await screen.findByRole("button", { name: /retry request/i }));

  expect(await screen.findByRole("button", { name: /^dismiss$/i })).toBeDisabled();
  expect(screen.getByRole("button", { name: /requesting/i })).toBeDisabled();

  resolveRetry({
    ...detailRow,
    status: "retrying",
    retry_requested_at: "2026-05-10T11:00:00Z",
  });

  expect(await screen.findByText(/retry request recorded/i)).toBeInTheDocument();
});

test("dismiss conflict error stays inline and keeps confirmation open", async () => {
  dismissDeadLetter.mockRejectedValueOnce(
    new Error("Dead letter cannot be dismissed from its current status.")
  );

  render(<DeadLettersPanel {...styleProps} />);

  await screen.findByText("99");
  await userEvent.click(screen.getByTitle("View dead letter 7"));
  await screen.findByText(/failed at \[REDACTED_URL\]/i);

  await userEvent.click(await screen.findByRole("button", { name: /^dismiss$/i }));
  await userEvent.type(screen.getByLabelText(/dismiss comment or reason/i), "Already retried");
  await userEvent.click(screen.getByRole("button", { name: /confirm dismiss/i }));

  expect(
    await screen.findByText(/dead letter cannot be dismissed from its current status/i)
  ).toBeInTheDocument();
  expect(screen.getByLabelText(/dismiss comment or reason/i)).toHaveValue("Already retried");
  expect(screen.getByText(/failed at \[REDACTED_URL\]/i)).toBeInTheDocument();
});

test("super_admin sees retry-execute for retrying playbook_execution dead letter", async () => {
  getDeadLetters.mockResolvedValue({
    items: [{ ...listRow, status: "retrying" }],
    limit: 100,
    offset: 0,
  });
  getDeadLetter.mockResolvedValue(retryingPlaybookRow);

  render(<DeadLettersPanel {...styleProps} userRole="super_admin" />);

  await screen.findByText("99");
  await userEvent.click(screen.getByTitle("View dead letter 7"));

  expect(await screen.findByRole("button", { name: /^retry execute$/i })).toBeInTheDocument();
  expect(
    screen.getByText(/creates a new pending playbook execution only/i)
  ).toBeInTheDocument();
  expect(screen.getByText(/does not run steps immediately/i)).toBeInTheDocument();
});

test("super_admin retry-execute is hidden for non-retryable retrying dead letter", async () => {
  getDeadLetters.mockResolvedValue({
    items: [{ ...listRow, status: "retrying" }],
    limit: 100,
    offset: 0,
  });
  getDeadLetter.mockResolvedValue({ ...retryingPlaybookRow, retryable: false });

  render(<DeadLettersPanel {...styleProps} userRole="super_admin" />);

  await screen.findByText("99");
  await userEvent.click(screen.getByTitle("View dead letter 7"));
  await screen.findByText(/failed at \[REDACTED_URL\]/i);

  expect(screen.queryByRole("button", { name: /^retry execute$/i })).not.toBeInTheDocument();
});

test("analyst and viewer do not see retry-execute", async () => {
  getDeadLetters.mockResolvedValue({
    items: [{ ...listRow, status: "retrying" }],
    limit: 100,
    offset: 0,
  });
  getDeadLetter.mockResolvedValue(retryingPlaybookRow);

  render(<DeadLettersPanel {...styleProps} userRole="analyst" />);

  await screen.findByText("99");
  await userEvent.click(screen.getByTitle("View dead letter 7"));
  await screen.findByText(/failed at \[REDACTED_URL\]/i);
  expect(screen.queryByRole("button", { name: /retry execute/i })).not.toBeInTheDocument();

  cleanup();
  jest.clearAllMocks();
  loadSoarOperationsSummary.mockResolvedValue(summaryFixture);
  getDeadLetterMetrics.mockResolvedValue(sampleMetrics);
  getDeadLetters.mockResolvedValue({
    items: [{ ...listRow, status: "retrying" }],
    limit: 100,
    offset: 0,
  });
  getDeadLetter.mockResolvedValue(retryingPlaybookRow);

  render(<DeadLettersPanel {...styleProps} userRole="viewer" />);

  await screen.findByText("99");
  await userEvent.click(screen.getByTitle("View dead letter 7"));
  await screen.findByText(/failed at \[REDACTED_URL\]/i);
  expect(screen.queryByRole("button", { name: /retry execute/i })).not.toBeInTheDocument();
});

test("retry-execute is hidden for unsupported source types", async () => {
  getDeadLetters.mockResolvedValue({
    items: [{ ...listRow, status: "retrying", source_type: "notification_delivery" }],
    limit: 100,
    offset: 0,
  });
  getDeadLetter.mockResolvedValue({
    ...retryingPlaybookRow,
    source_type: "notification_delivery",
  });

  render(<DeadLettersPanel {...styleProps} userRole="super_admin" />);

  await screen.findByText("99");
  await userEvent.click(screen.getByTitle("View dead letter 7"));
  await screen.findByText(/failed at \[REDACTED_URL\]/i);

  expect(screen.queryByRole("button", { name: /retry execute/i })).not.toBeInTheDocument();
});

test("retry-execute button is disabled until checkbox and RETRY phrase", async () => {
  getDeadLetters.mockResolvedValue({
    items: [{ ...listRow, status: "retrying" }],
    limit: 100,
    offset: 0,
  });
  getDeadLetter.mockResolvedValue(retryingPlaybookRow);

  render(<DeadLettersPanel {...styleProps} userRole="super_admin" />);

  await screen.findByText("99");
  await userEvent.click(screen.getByTitle("View dead letter 7"));
  await screen.findByRole("button", { name: /^retry execute$/i });

  const button = await screen.findByRole("button", { name: /^retry execute$/i });
  expect(button).toBeDisabled();

  await userEvent.click(await screen.findByRole("checkbox"));
  expect(button).toBeDisabled();

  await userEvent.type(
    screen.getByLabelText(/retry execute confirmation phrase/i),
    "RETRY"
  );
  expect(button).toBeEnabled();
});

test("retry-execute calls service, shows new execution id, and refreshes", async () => {
  getDeadLetters
    .mockResolvedValueOnce({
      items: [{ ...listRow, status: "retrying" }],
      limit: 100,
      offset: 0,
    })
    .mockResolvedValueOnce({
      items: [{ ...listRow, status: "retried" }],
      limit: 100,
      offset: 0,
    });
  getDeadLetter
    .mockResolvedValueOnce(retryingPlaybookRow)
    .mockResolvedValueOnce({ ...retryingPlaybookRow, status: "retried" });

  render(<DeadLettersPanel {...styleProps} userRole="super_admin" />);

  await screen.findByText("99");
  await userEvent.click(screen.getByTitle("View dead letter 7"));
  await screen.findByRole("button", { name: /^retry execute$/i });

  await userEvent.click(await screen.findByRole("checkbox"));
  await userEvent.type(
    screen.getByLabelText(/retry execute confirmation phrase/i),
    "RETRY"
  );
  await userEvent.click(screen.getByRole("button", { name: /^retry execute$/i }));

  await waitFor(() => {
    expect(executeDeadLetterRetry).toHaveBeenCalledWith(7);
  });
  expect(await screen.findByText(/new pending execution #77 created/i)).toBeInTheDocument();
  expect(screen.getByText(/scripts\/run_playbook_executor_once\.py/i)).toBeInTheDocument();
  expect(screen.getByText(/failed at \[REDACTED_URL\]/i)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /^retry execute$/i })).not.toBeInTheDocument();
  await waitFor(() => {
    expect(getDeadLetters).toHaveBeenCalledTimes(2);
    expect(getDeadLetterMetrics).toHaveBeenCalledTimes(2);
    expect(getDeadLetter).toHaveBeenCalledTimes(2);
  });
});

test("retry-execute conflict error is displayed without changing status", async () => {
  getDeadLetters.mockResolvedValue({
    items: [{ ...listRow, status: "retrying" }],
    limit: 100,
    offset: 0,
  });
  getDeadLetter.mockResolvedValue(retryingPlaybookRow);
  executeDeadLetterRetry.mockRejectedValueOnce(
    new Error("Dead letter must be retrying before retry execution.")
  );

  render(<DeadLettersPanel {...styleProps} userRole="super_admin" />);

  await screen.findByText("99");
  await userEvent.click(screen.getByTitle("View dead letter 7"));
  await screen.findByRole("button", { name: /^retry execute$/i });

  await userEvent.click(await screen.findByRole("checkbox"));
  await userEvent.type(
    screen.getByLabelText(/retry execute confirmation phrase/i),
    "RETRY"
  );
  await userEvent.click(screen.getByRole("button", { name: /^retry execute$/i }));

  expect(
    await screen.findByText(/dead letter must be retrying before retry execution/i)
  ).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /^retry execute$/i })).toBeEnabled();
  expect(screen.getByText(/retry requested at/i)).toBeInTheDocument();
});
