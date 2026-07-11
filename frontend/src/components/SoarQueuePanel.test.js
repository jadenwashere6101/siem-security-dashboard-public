import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import SoarQueuePanel from "./SoarQueuePanel";
import {
  loadRecentSoarQueueItems,
  loadSoarQueueItem,
  loadSoarQueueStatus,
  runSoarWorkerOnce,
} from "../services/soarQueueService";

jest.mock("../services/soarQueueService", () => ({
  loadSoarQueueStatus: jest.fn(),
  loadRecentSoarQueueItems: jest.fn(),
  loadSoarQueueItem: jest.fn(),
  runSoarWorkerOnce: jest.fn(),
}));

const statusFixture = {
  counts: {
    pending: 2,
    running: 1,
    awaiting_approval: 1,
    success: 3,
    failed: 1,
    skipped: 4,
  },
  total: 12,
};

const queueRowFixture = {
  id: 101,
  alert_id: null,
  alert_reference: null,
  action: "block_ip",
  status: "pending",
  source_ip: "8.8.8.8",
  retry_count: 1,
  max_retries: 3,
  last_error: null,
  created_at: "2026-05-06T12:00:00Z",
  updated_at: "2026-05-06T12:01:00Z",
};

const simulatedOutcome = {
  decision_id: 501,
  alert_id: null,
  queue_id: 101,
  selected_action: "block_ip",
  decision_source: "queue",
  execution_actor: "queue_worker",
  execution_mode: "simulation",
  execution_state: "succeeded",
  external_executed: false,
  tracking_recorded: false,
  simulated: true,
  reason_code: "simulation_mode",
  outcome_summary: "Simulated queue action completed.",
  soar_correlation_id: "soar-corr-101",
};

const queueDetailFixture = {
  ...queueRowFixture,
  idempotency_key: "queue-idempotency-key-101",
  latest_approval: null,
  approval_events: [],
};

const awaitingApprovalRowFixture = {
  id: 202,
  alert_id: 55,
  alert_reference: { status: "linked", label: "Alert 55" },
  action: "block_ip",
  status: "awaiting_approval",
  source_ip: "203.0.113.5",
  retry_count: 0,
  max_retries: 3,
  last_error: null,
  created_at: "2026-05-08T10:00:00Z",
  updated_at: "2026-05-08T10:01:00Z",
};

const awaitingApprovalDetailFixture = {
  ...awaitingApprovalRowFixture,
  idempotency_key: "awaiting-idempotency-key-202",
  latest_approval: null,
  approval_events: [],
};

const queueDetailWithApprovalFixture = {
  id: 42,
  alert_id: 10,
  alert_reference: { status: "linked", label: "Alert 10" },
  action: "block_ip",
  status: "awaiting_approval",
  source_ip: "10.0.0.1",
  retry_count: 0,
  max_retries: 3,
  last_error: null,
  created_at: "2026-05-08T09:00:00Z",
  updated_at: "2026-05-08T09:01:00Z",
  idempotency_key: "idem-key-42",
  latest_approval: {
    id: 7,
    status: "pending",
    risk_level: "high",
    created_at: "2026-05-08T09:01:00Z",
    expires_at: "2026-05-08T10:00:00Z",
    decided_at: null,
  },
  approval_events: [],
};

const queueDetailWithoutApprovalFixture = {
  ...queueDetailWithApprovalFixture,
  status: "pending",
  latest_approval: null,
  approval_events: [],
};

const queueDetailWithEventsFixture = {
  id: 42,
  alert_id: 10,
  alert_reference: { status: "linked", label: "Alert 10" },
  action: "block_ip",
  status: "skipped",
  source_ip: "10.0.0.1",
  retry_count: 0,
  max_retries: 3,
  last_error: "approval denied",
  created_at: "2026-05-08T09:00:00Z",
  updated_at: "2026-05-08T09:30:05Z",
  idempotency_key: "idem-key-42",
  latest_approval: {
    id: 7,
    status: "denied",
    risk_level: "high",
    created_at: "2026-05-08T09:01:00Z",
    expires_at: "2026-05-08T10:00:00Z",
    decided_at: "2026-05-08T09:30:00Z",
  },
  approval_events: [
    {
      id: 1,
      approval_request_id: 7,
      event_type: "created",
      actor_user_id: null,
      previous_status: null,
      new_status: "pending",
      comment: null,
      created_at: "2026-05-08T09:01:00Z",
    },
    {
      id: 2,
      approval_request_id: 7,
      event_type: "denied",
      actor_user_id: 3,
      previous_status: "pending",
      new_status: "denied",
      comment: "Too broad",
      created_at: "2026-05-08T09:30:00Z",
    },
  ],
};

const queueDetailNoEventsFixture = {
  id: 43,
  alert_id: 11,
  alert_reference: { status: "linked", label: "Alert 11" },
  action: "block_ip",
  status: "pending",
  source_ip: "10.0.0.2",
  retry_count: 0,
  max_retries: 3,
  last_error: null,
  created_at: "2026-05-08T08:00:00Z",
  updated_at: "2026-05-08T08:00:00Z",
  idempotency_key: "idem-key-43",
  latest_approval: null,
  approval_events: [],
};

const renderPanel = () =>
  render(
    <SoarQueuePanel
      cardStyle={{}}
      cardHeaderStyle={{}}
      cardTitleStyle={{}}
      cardSubtitleStyle={{}}
      filterLabelStyle={{}}
      selectStyle={{}}
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

describe("SoarQueuePanel", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test("shows loading state while initial queue requests are pending", () => {
    const pendingStatus = deferred();
    const pendingRecent = deferred();
    loadSoarQueueStatus.mockReturnValue(pendingStatus.promise);
    loadRecentSoarQueueItems.mockReturnValue(pendingRecent.promise);

    renderPanel();

    expect(screen.getByText("Loading SOAR queue...")).toBeInTheDocument();
  });

  test("shows error state when initial load fails", async () => {
    loadSoarQueueStatus.mockRejectedValue(new Error("Unable to load SOAR queue status"));
    loadRecentSoarQueueItems.mockResolvedValue({ items: [] });

    renderPanel();

    expect(await screen.findByText("Unable to load SOAR queue status")).toBeInTheDocument();
  });

  test("shows empty state when queue has no recent items", async () => {
    loadSoarQueueStatus.mockResolvedValue(statusFixture);
    loadRecentSoarQueueItems.mockResolvedValue({ items: [] });

    renderPanel();

    expect(await screen.findByText("No queued SOAR actions found.")).toBeInTheDocument();
    await waitFor(() =>
      expect(loadRecentSoarQueueItems).toHaveBeenCalledWith({
        limit: 50,
        status: "all",
      })
    );
  });

test("renders queue counts and recent queue rows", async () => {
    loadSoarQueueStatus.mockResolvedValue(statusFixture);
    loadRecentSoarQueueItems.mockResolvedValue({ items: [queueRowFixture] });

    renderPanel();

    expect(await screen.findByText("Recent Queue Items")).toBeInTheDocument();
    expect(screen.getByText("Block Ip")).toBeInTheDocument();
    expect(screen.getByText("8.8.8.8")).toBeInTheDocument();
    expect(screen.getByText("1 / 3")).toBeInTheDocument();
    expect(screen.getAllByText("Pending").length).toBeGreaterThan(0);
  });

  test("renders canonical outcome badges in queue rows", async () => {
    loadSoarQueueStatus.mockResolvedValue(statusFixture);
    loadRecentSoarQueueItems.mockResolvedValue({
      items: [
        { ...queueRowFixture, response_outcome: simulatedOutcome },
        { ...queueRowFixture, id: 102, response_outcome: null },
      ],
    });

    renderPanel();

    expect(await screen.findByText("Recent Queue Items")).toBeInTheDocument();
    expect(screen.getByText("Simulated")).toBeInTheDocument();
    expect(screen.getByText("Observed only")).toBeInTheDocument();
  });

  test("shows awaiting approval count tile", async () => {
    loadSoarQueueStatus.mockResolvedValue(statusFixture);
    loadRecentSoarQueueItems.mockResolvedValue({ items: [] });

    renderPanel();

    await screen.findByText("No queued SOAR actions found.");
    expect(screen.getAllByText("Awaiting Approval").length).toBeGreaterThan(0);
    expect(screen.getAllByText("1").length).toBeGreaterThan(0);
  });

  test("includes awaiting approval status filter option", async () => {
    loadSoarQueueStatus.mockResolvedValue(statusFixture);
    loadRecentSoarQueueItems.mockResolvedValue({ items: [] });

    renderPanel();

    await screen.findByText("No queued SOAR actions found.");
    expect(
      screen.getByRole("option", { name: "Awaiting Approval" })
    ).toBeInTheDocument();
  });

  test("renders awaiting approval badge in queue list", async () => {
    loadSoarQueueStatus.mockResolvedValue(statusFixture);
    loadRecentSoarQueueItems.mockResolvedValue({ items: [awaitingApprovalRowFixture] });

    renderPanel();

    expect(await screen.findByText("Recent Queue Items")).toBeInTheDocument();
    expect(screen.getAllByText("Awaiting Approval").length).toBeGreaterThan(0);
    expect(screen.getByText("203.0.113.5")).toBeInTheDocument();
  });

  test("renders deleted alert when alert_id is null", async () => {
    loadSoarQueueStatus.mockResolvedValue(statusFixture);
    loadRecentSoarQueueItems.mockResolvedValue({ items: [queueRowFixture] });

    renderPanel();

    expect(await screen.findByText("Deleted alert")).toBeInTheDocument();
  });

  test("refreshes recent queue rows when status filter changes", async () => {
    loadSoarQueueStatus.mockResolvedValue(statusFixture);
    loadRecentSoarQueueItems.mockResolvedValue({ items: [queueRowFixture] });

    renderPanel();
    await screen.findByText("Recent Queue Items");

    await userEvent.selectOptions(screen.getByLabelText("Status"), "failed");

    await waitFor(() =>
      expect(loadRecentSoarQueueItems).toHaveBeenCalledWith({
        limit: 50,
        status: "failed",
      })
    );
  });

  test("refreshes recent queue rows when page size changes", async () => {
    loadSoarQueueStatus.mockResolvedValue(statusFixture);
    loadRecentSoarQueueItems.mockResolvedValue({ items: [queueRowFixture] });

    renderPanel();
    await screen.findByText("Recent Queue Items");

    await userEvent.selectOptions(screen.getByLabelText("Rows"), "10");

    await waitFor(() =>
      expect(loadRecentSoarQueueItems).toHaveBeenCalledWith({
        limit: 10,
        status: "all",
      })
    );
  });

  test("manual refresh preserves current status filter and page size", async () => {
    loadSoarQueueStatus.mockResolvedValue(statusFixture);
    loadRecentSoarQueueItems.mockResolvedValue({ items: [queueRowFixture] });

    renderPanel();
    await screen.findByText("Recent Queue Items");

    await userEvent.selectOptions(screen.getByLabelText("Status"), "failed");
    await userEvent.selectOptions(screen.getByLabelText("Rows"), "25");
    await waitFor(() =>
      expect(loadRecentSoarQueueItems).toHaveBeenCalledWith({
        limit: 25,
        status: "failed",
      })
    );

    const refreshButton = screen.getByRole("button", { name: "Refresh" });
    await waitFor(() => expect(refreshButton).not.toBeDisabled());
    const callCountBeforeRefresh = loadRecentSoarQueueItems.mock.calls.length;

    await userEvent.click(refreshButton);

    await waitFor(() =>
      expect(loadRecentSoarQueueItems.mock.calls.length).toBeGreaterThan(
        callCountBeforeRefresh
      )
    );
    expect(loadRecentSoarQueueItems).toHaveBeenLastCalledWith({
      limit: 25,
      status: "failed",
    });
  });

  test("shows filtered empty state while keeping counts visible", async () => {
    loadSoarQueueStatus.mockResolvedValue(statusFixture);
    loadRecentSoarQueueItems
      .mockResolvedValueOnce({ items: [queueRowFixture] })
      .mockResolvedValueOnce({ items: [] });

    renderPanel();
    await screen.findByText("Recent Queue Items");

    await userEvent.selectOptions(screen.getByLabelText("Status"), "failed");

    expect(
      await screen.findByText("No queued SOAR actions found for this filter.")
    ).toBeInTheDocument();
    expect(screen.getByText("Total")).toBeInTheDocument();
  });

  test("shows filtered empty state for awaiting approval filter", async () => {
    loadSoarQueueStatus.mockResolvedValue(statusFixture);
    loadRecentSoarQueueItems
      .mockResolvedValueOnce({ items: [] })
      .mockResolvedValueOnce({ items: [] });

    renderPanel();
    await screen.findByText("No queued SOAR actions found.");

    await userEvent.selectOptions(screen.getByLabelText("Status"), "awaiting_approval");

    expect(
      await screen.findByText("No queued SOAR actions found for this filter.")
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(loadRecentSoarQueueItems).toHaveBeenLastCalledWith({
        limit: 50,
        status: "awaiting_approval",
      })
    );
  });

  test("loads and renders queue item detail from view action", async () => {
    loadSoarQueueStatus.mockResolvedValue(statusFixture);
    loadRecentSoarQueueItems.mockResolvedValue({ items: [queueRowFixture] });
    loadSoarQueueItem.mockResolvedValue(queueDetailFixture);

    renderPanel();
    await screen.findByText("Recent Queue Items");
    expect(screen.queryByText("queue-idempotency-key-101")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "View" }));

    await waitFor(() =>
      expect(loadSoarQueueItem).toHaveBeenCalledWith(queueRowFixture.id)
    );
    expect(await screen.findByText("queue-idempotency-key-101")).toBeInTheDocument();
  });

  test("renders queue detail correlation id and response outcome summary", async () => {
    loadSoarQueueStatus.mockResolvedValue(statusFixture);
    loadRecentSoarQueueItems.mockResolvedValue({
      items: [{ ...queueRowFixture, response_outcome: simulatedOutcome }],
    });
    loadSoarQueueItem.mockResolvedValue({
      ...queueDetailFixture,
      response_outcome: simulatedOutcome,
    });

    renderPanel();
    await screen.findByText("Recent Queue Items");

    await userEvent.click(screen.getByRole("button", { name: "View" }));

    expect(await screen.findByText("SOAR Correlation ID")).toBeInTheDocument();
    expect(screen.getByText("soar-corr-101")).toBeInTheDocument();
    expect(screen.getByText("Response Outcome")).toBeInTheDocument();
    expect(screen.getAllByText("Simulated").length).toBeGreaterThan(0);
    expect(screen.getByText("Simulated queue action completed.")).toBeInTheDocument();
  });

  test("shows approval-waiting note in detail for awaiting approval item", async () => {
    loadSoarQueueStatus.mockResolvedValue(statusFixture);
    loadRecentSoarQueueItems.mockResolvedValue({ items: [awaitingApprovalRowFixture] });
    loadSoarQueueItem.mockResolvedValue(awaitingApprovalDetailFixture);

    renderPanel();
    await screen.findByText("Recent Queue Items");

    await userEvent.click(screen.getByRole("button", { name: "View" }));

    await waitFor(() =>
      expect(loadSoarQueueItem).toHaveBeenCalledWith(awaitingApprovalRowFixture.id)
    );
    expect(
      await screen.findByText(/This action is paused and waiting for approval/)
    ).toBeInTheDocument();
  });

  test("does not show approval-waiting note in detail for non-awaiting item", async () => {
    loadSoarQueueStatus.mockResolvedValue(statusFixture);
    loadRecentSoarQueueItems.mockResolvedValue({ items: [queueRowFixture] });
    loadSoarQueueItem.mockResolvedValue(queueDetailFixture);

    renderPanel();
    await screen.findByText("Recent Queue Items");

    await userEvent.click(screen.getByRole("button", { name: "View" }));

    expect(await screen.findByText("queue-idempotency-key-101")).toBeInTheDocument();
    expect(
      screen.queryByText(/This action is paused and waiting for approval/)
    ).not.toBeInTheDocument();
  });

  test("renders linked approval section when latest approval is present", async () => {
    loadSoarQueueStatus.mockResolvedValue(statusFixture);
    loadRecentSoarQueueItems.mockResolvedValue({
      items: [{ ...awaitingApprovalRowFixture, id: 42 }],
    });
    loadSoarQueueItem.mockResolvedValue(queueDetailWithApprovalFixture);

    renderPanel();
    await screen.findByText("Recent Queue Items");

    await userEvent.click(screen.getByRole("button", { name: "View" }));

    expect(await screen.findByText("Linked Approval")).toBeInTheDocument();
    expect(screen.getByText("#7")).toBeInTheDocument();
  });

  test("does not render linked approval section when latest approval is null", async () => {
    loadSoarQueueStatus.mockResolvedValue(statusFixture);
    loadRecentSoarQueueItems.mockResolvedValue({
      items: [{ ...awaitingApprovalRowFixture, id: 42 }],
    });
    loadSoarQueueItem.mockResolvedValue(queueDetailWithoutApprovalFixture);

    renderPanel();
    await screen.findByText("Recent Queue Items");

    await userEvent.click(screen.getByRole("button", { name: "View" }));

    expect(await screen.findByText("idem-key-42")).toBeInTheDocument();
    expect(screen.queryByText("Linked Approval")).not.toBeInTheDocument();
  });

  test("renders linked approval summary fields", async () => {
    loadSoarQueueStatus.mockResolvedValue(statusFixture);
    loadRecentSoarQueueItems.mockResolvedValue({
      items: [{ ...awaitingApprovalRowFixture, id: 42 }],
    });
    loadSoarQueueItem.mockResolvedValue(queueDetailWithApprovalFixture);

    renderPanel();
    await screen.findByText("Recent Queue Items");

    await userEvent.click(screen.getByRole("button", { name: "View" }));

    expect(await screen.findByText("Approval ID")).toBeInTheDocument();
    expect(screen.getByText("Approval Status")).toBeInTheDocument();
    expect(screen.getByText("Risk")).toBeInTheDocument();
    expect(screen.getByText("Expires")).toBeInTheDocument();
    expect(screen.getByText("Decided")).toBeInTheDocument();
  });

  test("does not render approve or deny controls in queue detail approval context", async () => {
    loadSoarQueueStatus.mockResolvedValue(statusFixture);
    loadRecentSoarQueueItems.mockResolvedValue({
      items: [{ ...awaitingApprovalRowFixture, id: 42 }],
    });
    loadSoarQueueItem.mockResolvedValue(queueDetailWithApprovalFixture);

    renderPanel();
    await screen.findByText("Recent Queue Items");

    await userEvent.click(screen.getByRole("button", { name: "View" }));
    await screen.findByText("Linked Approval");

    expect(screen.queryByRole("button", { name: /approve/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /deny/i })).not.toBeInTheDocument();
  });

  test("execution timeline section always renders", async () => {
    loadSoarQueueStatus.mockResolvedValue(statusFixture);
    loadRecentSoarQueueItems.mockResolvedValue({
      items: [{ ...queueRowFixture, id: 43 }],
    });
    loadSoarQueueItem.mockResolvedValue(queueDetailNoEventsFixture);

    renderPanel();
    await screen.findByText("Recent Queue Items");
    await userEvent.click(screen.getByRole("button", { name: "View" }));

    await waitFor(() =>
      expect(screen.getByText("Execution Timeline")).toBeInTheDocument()
    );
  });

  test("action queued event always renders", async () => {
    loadSoarQueueStatus.mockResolvedValue(statusFixture);
    loadRecentSoarQueueItems.mockResolvedValue({
      items: [{ ...queueRowFixture, id: 43 }],
    });
    loadSoarQueueItem.mockResolvedValue(queueDetailNoEventsFixture);

    renderPanel();
    await screen.findByText("Recent Queue Items");
    await userEvent.click(screen.getByRole("button", { name: "View" }));

    await waitFor(() =>
      expect(screen.getByText("Action queued")).toBeInTheDocument()
    );
  });

  test("approval events render in timeline", async () => {
    loadSoarQueueStatus.mockResolvedValue(statusFixture);
    loadRecentSoarQueueItems.mockResolvedValue({
      items: [{ ...queueRowFixture, id: 42 }],
    });
    loadSoarQueueItem.mockResolvedValue(queueDetailWithEventsFixture);

    renderPanel();
    await screen.findByText("Recent Queue Items");
    await userEvent.click(screen.getByRole("button", { name: "View" }));

    await waitFor(() => {
      expect(screen.getByText("Approval requested")).toBeInTheDocument();
      expect(screen.getByText("Approval denied")).toBeInTheDocument();
    });
  });

  test("decision comment renders as detail text", async () => {
    loadSoarQueueStatus.mockResolvedValue(statusFixture);
    loadRecentSoarQueueItems.mockResolvedValue({
      items: [{ ...queueRowFixture, id: 42 }],
    });
    loadSoarQueueItem.mockResolvedValue(queueDetailWithEventsFixture);

    renderPanel();
    await screen.findByText("Recent Queue Items");
    await userEvent.click(screen.getByRole("button", { name: "View" }));

    await waitFor(() => expect(screen.getByText("Too broad")).toBeInTheDocument());
  });

  test("terminal event renders for skipped item", async () => {
    loadSoarQueueStatus.mockResolvedValue(statusFixture);
    loadRecentSoarQueueItems.mockResolvedValue({
      items: [{ ...queueRowFixture, id: 42 }],
    });
    loadSoarQueueItem.mockResolvedValue(queueDetailWithEventsFixture);

    renderPanel();
    await screen.findByText("Recent Queue Items");
    await userEvent.click(screen.getByRole("button", { name: "View" }));

    await waitFor(() => {
      expect(screen.getByText("Action skipped")).toBeInTheDocument();
      expect(screen.getAllByText("approval denied").length).toBeGreaterThan(0);
    });
  });

  test("no approve or deny button in timeline section", async () => {
    loadSoarQueueStatus.mockResolvedValue(statusFixture);
    loadRecentSoarQueueItems.mockResolvedValue({
      items: [{ ...queueRowFixture, id: 42 }],
    });
    loadSoarQueueItem.mockResolvedValue(queueDetailWithEventsFixture);

    renderPanel();
    await screen.findByText("Recent Queue Items");
    await userEvent.click(screen.getByRole("button", { name: "View" }));
    await screen.findByText("Execution Timeline");

    expect(screen.queryByRole("button", { name: /approve/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /deny/i })).toBeNull();
  });

  test("preserves selected detail when filter changes to empty results", async () => {
    loadSoarQueueStatus.mockResolvedValue(statusFixture);
    loadRecentSoarQueueItems
      .mockResolvedValueOnce({ items: [queueRowFixture] })
      .mockResolvedValueOnce({ items: [] });
    loadSoarQueueItem.mockResolvedValue(queueDetailFixture);

    renderPanel();
    await screen.findByText("Recent Queue Items");
    await userEvent.click(screen.getByRole("button", { name: "View" }));
    expect(await screen.findByText("queue-idempotency-key-101")).toBeInTheDocument();

    await userEvent.selectOptions(screen.getByLabelText("Status"), "failed");

    expect(
      await screen.findByText("No queued SOAR actions found for this filter.")
    ).toBeInTheDocument();
    expect(screen.getByText("queue-idempotency-key-101")).toBeInTheDocument();
  });

  test("shows detail loading state while queue item detail is in flight", async () => {
    loadSoarQueueStatus.mockResolvedValue(statusFixture);
    loadRecentSoarQueueItems.mockResolvedValue({ items: [queueRowFixture] });
    const pendingDetail = deferred();
    loadSoarQueueItem.mockReturnValue(pendingDetail.promise);

    renderPanel();
    await screen.findByText("Recent Queue Items");

    await userEvent.click(screen.getByRole("button", { name: "View" }));

    expect(screen.getByText("Loading queue item details...")).toBeInTheDocument();
  });

  test("shows detail error state when detail fetch fails", async () => {
    loadSoarQueueStatus.mockResolvedValue(statusFixture);
    loadRecentSoarQueueItems.mockResolvedValue({ items: [queueRowFixture] });
    loadSoarQueueItem.mockRejectedValue(new Error("Unable to load SOAR queue item"));

    renderPanel();
    await screen.findByText("Recent Queue Items");

    await userEvent.click(screen.getByRole("button", { name: "View" }));

    expect(await screen.findByText("Unable to load SOAR queue item")).toBeInTheDocument();
  });

  test("disables run simulation batch while request is pending", async () => {
    loadSoarQueueStatus.mockResolvedValue(statusFixture);
    loadRecentSoarQueueItems.mockResolvedValue({ items: [queueRowFixture] });
    const pendingRun = deferred();
    runSoarWorkerOnce.mockReturnValue(pendingRun.promise);

    renderPanel();
    await screen.findByText("Recent Queue Items");

    const runButton = screen.getByRole("button", { name: "Run simulation batch" });
    await userEvent.click(runButton);

    expect(runSoarWorkerOnce).toHaveBeenCalledWith({ batchSize: 10 });
    expect(screen.getByRole("button", { name: "Running..." })).toBeDisabled();
  });

  test("renders successful run summary and refreshes queue data", async () => {
    loadSoarQueueStatus
      .mockResolvedValueOnce(statusFixture)
      .mockResolvedValueOnce(statusFixture);
    loadRecentSoarQueueItems
      .mockResolvedValueOnce({ items: [queueRowFixture] })
      .mockResolvedValueOnce({ items: [queueRowFixture] });
    runSoarWorkerOnce.mockResolvedValue({
      mode: "simulation",
      batch_size: 10,
      summary: { processed: 2, success: 1, failed: 0, skipped: 1, requeued: 0 },
      results: [],
    });

    renderPanel();
    await screen.findByText("Recent Queue Items");

    await userEvent.click(screen.getByRole("button", { name: "Run simulation batch" }));

    expect(await screen.findByText("Last manual simulation batch")).toBeInTheDocument();
    expect(await screen.findByText(/2 queue actions simulated internally/i)).toBeInTheDocument();
    expect(
      screen.getByText(/No notification, provider, firewall, host, or other external execution occurred/i)
    ).toBeInTheDocument();
    expect(screen.getAllByText(/SimulationExecutor/i).length).toBeGreaterThan(0);
    expect(screen.queryByText(/actions executed/i)).not.toBeInTheDocument();
    expect(await screen.findByText("Processed")).toBeInTheDocument();

    await waitFor(() => expect(loadSoarQueueStatus).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(loadRecentSoarQueueItems).toHaveBeenCalledTimes(2));
  });

  test("successful run refresh preserves current filter and page size", async () => {
    loadSoarQueueStatus.mockResolvedValue(statusFixture);
    loadRecentSoarQueueItems.mockResolvedValue({ items: [queueRowFixture] });
    runSoarWorkerOnce.mockResolvedValue({
      mode: "simulation",
      batch_size: 10,
      summary: { processed: 1, success: 1, failed: 0, skipped: 0, requeued: 0 },
      results: [],
    });

    renderPanel();
    await screen.findByText("Recent Queue Items");

    await userEvent.selectOptions(screen.getByLabelText("Status"), "failed");
    await userEvent.selectOptions(screen.getByLabelText("Rows"), "25");
    await waitFor(() =>
      expect(loadRecentSoarQueueItems).toHaveBeenCalledWith({
        limit: 25,
        status: "failed",
      })
    );

    const runButton = screen.getByRole("button", { name: "Run simulation batch" });
    await waitFor(() => expect(runButton).not.toBeDisabled());
    const callCountBeforeRun = loadRecentSoarQueueItems.mock.calls.length;

    await userEvent.click(runButton);

    await waitFor(() =>
      expect(loadRecentSoarQueueItems.mock.calls.length).toBeGreaterThan(
        callCountBeforeRun
      )
    );
    expect(loadRecentSoarQueueItems).toHaveBeenLastCalledWith({
      limit: 25,
      status: "failed",
    });
  });

  test("does not render retry/replay/cancel mutation controls", async () => {
    loadSoarQueueStatus.mockResolvedValue(statusFixture);
    loadRecentSoarQueueItems.mockResolvedValue({ items: [queueRowFixture] });

    renderPanel();
    await screen.findByText("Recent Queue Items");

    expect(screen.queryByRole("button", { name: /retry/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /replay/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /cancel/i })).not.toBeInTheDocument();
  });
});
