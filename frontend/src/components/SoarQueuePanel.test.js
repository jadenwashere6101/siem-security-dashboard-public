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
  counts: { pending: 2, running: 1, success: 3, failed: 1, skipped: 4 },
  total: 11,
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

const queueDetailFixture = {
  ...queueRowFixture,
  idempotency_key: "queue-idempotency-key-101",
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
    expect(await screen.findByText("Batch size used: 10")).toBeInTheDocument();
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
