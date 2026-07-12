import React from "react";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import SourceHealthPanel from "./SourceHealthPanel";
import { loadSourceHealth } from "../services/sourceHealthService";
import { SOURCE_METADATA } from "../utils/sourceMetadata";

jest.mock("../services/sourceHealthService", () => ({ loadSourceHealth: jest.fn() }));

const makePayload = ({ allNeverSeen = false } = {}) => ({
  generated_at: "2026-07-12T15:00:00+00:00",
  windows: { last_hour_start: "2026-07-12T14:00:00+00:00", today_start: "2026-07-12T00:00:00+00:00", timezone: "UTC" },
  sources: SOURCE_METADATA.map((item, index) => ({
    source: item.source,
    source_type: item.sourceType,
    display_label: item.displayLabel,
    last_event_at: allNeverSeen || index === 2 ? null : `2026-07-12T14:5${index}:00+00:00`,
    events_last_hour: allNeverSeen ? 0 : index + 1,
    events_today: allNeverSeen ? 0 : (index + 1) * 10,
    total_events: allNeverSeen ? 0 : (index + 1) * 100,
    ever_seen: !allNeverSeen && index !== 2,
  })),
});

beforeEach(() => {
  jest.clearAllMocks();
  jest.useFakeTimers();
});
afterEach(() => { jest.clearAllTimers(); jest.useRealTimers(); });

test("renders six sources in canonical order without client aggregation", async () => {
  loadSourceHealth.mockResolvedValue(makePayload());
  render(<SourceHealthPanel displaySettings={{ timezoneMode: "utc" }} onOpenLiveLogs={() => {}} />);
  expect(screen.getByText(/loading source activity/i)).toBeInTheDocument();
  const grid = await screen.findByTestId("source-health-grid");
  expect(within(grid).getAllByRole("article").map((node) => node.dataset.source)).toEqual(
    SOURCE_METADATA.map((item) => item.source)
  );
  expect(screen.getByText("600")).toBeInTheDocument();
  expect(screen.getByText("Never seen")).toBeInTheDocument();
  expect(screen.getByText("pfsense / firewall")).toBeInTheDocument();
});

test("shows all-never-seen state while keeping all entries", async () => {
  loadSourceHealth.mockResolvedValue(makePayload({ allNeverSeen: true }));
  render(<SourceHealthPanel onOpenLiveLogs={() => {}} />);
  expect(await screen.findByText(/no recognized source has stored an event yet/i)).toBeInTheDocument();
  expect(screen.getAllByText("Never seen")).toHaveLength(6);
  expect(screen.getAllByText("0").length).toBeGreaterThanOrEqual(6);
});

test("supports initial error, manual refresh, and recovery", async () => {
  loadSourceHealth.mockRejectedValueOnce(new Error("API unavailable")).mockResolvedValueOnce(makePayload());
  render(<SourceHealthPanel onOpenLiveLogs={() => {}} />);
  expect(await screen.findByRole("alert")).toHaveTextContent("API unavailable");
  await userEvent.click(screen.getByRole("button", { name: "Refresh" }));
  expect(await screen.findByTestId("source-health-grid")).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test("uses one polling timer, refreshes, preserves focus and scroll, and cleans up", async () => {
  loadSourceHealth.mockResolvedValue(makePayload());
  const scrollSpy = jest.spyOn(window, "scrollTo").mockImplementation(() => {});
  const { unmount } = render(<SourceHealthPanel pollIntervalMs={5000} onOpenLiveLogs={() => {}} />);
  await screen.findByTestId("source-health-grid");
  const refreshButton = screen.getByRole("button", { name: "Refresh" });
  refreshButton.focus();
  expect(jest.getTimerCount()).toBe(1);
  await act(async () => { jest.advanceTimersByTime(5000); await Promise.resolve(); });
  await waitFor(() => expect(loadSourceHealth).toHaveBeenCalledTimes(2));
  expect(refreshButton).toHaveFocus();
  expect(scrollSpy).not.toHaveBeenCalled();
  unmount();
  expect(jest.getTimerCount()).toBe(0);
  scrollSpy.mockRestore();
});

test("does not schedule polling when automatic refresh is disabled", async () => {
  loadSourceHealth.mockResolvedValue(makePayload());
  render(<SourceHealthPanel pollIntervalMs={0} onOpenLiveLogs={() => {}} />);
  await screen.findByTestId("source-health-grid");
  expect(jest.getTimerCount()).toBe(0);
});

test("routes every accessible Live Logs action to canonical destination", async () => {
  loadSourceHealth.mockResolvedValue(makePayload());
  const onOpenLiveLogs = jest.fn();
  render(<SourceHealthPanel onOpenLiveLogs={onOpenLiveLogs} />);
  await screen.findByTestId("source-health-grid");
  for (const item of SOURCE_METADATA) {
    await userEvent.click(screen.getByRole("button", { name: `Open ${item.displayLabel} Live Logs` }));
    expect(onOpenLiveLogs).toHaveBeenLastCalledWith(item.liveLogsDestination);
  }
});

test("does not introduce inferred source-state wording", async () => {
  loadSourceHealth.mockResolvedValue(makePayload());
  const { container } = render(<SourceHealthPanel onOpenLiveLogs={() => {}} />);
  await screen.findByTestId("source-health-grid");
  expect(container.textContent).not.toMatch(/\b(healthy|stale|offline|connected|degraded)\b/i);
});
