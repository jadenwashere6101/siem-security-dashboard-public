import React from "react";
import { act, render, screen, waitFor } from "@testing-library/react";

import LiveLogsPanel from "./LiveLogsPanel";
import { loadLiveLogs } from "../services/liveLogsService";

jest.mock("../services/liveLogsService", () => ({
  loadLiveLogs: jest.fn(),
}));

const styleProps = {
  cardStyle: {},
  cardHeaderStyle: {},
  cardTitleStyle: {},
  cardSubtitleStyle: {},
};

const eventOne = {
  id: 1,
  event_type: "firewall_block",
  severity: "medium",
  source: "pfsense",
  source_ip: "198.51.100.10",
  app_name: "pfsense_filterlog",
  message: "first event",
  created_at: "2026-07-07T10:00:00Z",
};

const eventTwo = {
  ...eventOne,
  id: 2,
  message: "second event",
  created_at: "2026-07-07T10:00:05Z",
};

beforeEach(() => {
  jest.clearAllMocks();
  jest.useFakeTimers();
});

afterEach(() => {
  jest.runOnlyPendingTimers();
  jest.useRealTimers();
});

test("renders loading then populated newest-first rows", async () => {
  loadLiveLogs.mockResolvedValue([eventOne, eventTwo]);

  render(<LiveLogsPanel source="pfsense" {...styleProps} />);

  expect(screen.getByText(/loading live logs/i)).toBeInTheDocument();
  expect(await screen.findByText("second event")).toBeInTheDocument();
  expect(screen.getByText("first event")).toBeInTheDocument();

  const messages = screen.getAllByText(/event$/i).map((node) => node.textContent);
  expect(messages).toEqual(["second event", "first event"]);
  expect(loadLiveLogs).toHaveBeenCalledWith({ source: "pfsense" });
});

test("renders empty state", async () => {
  loadLiveLogs.mockResolvedValue([]);

  render(<LiveLogsPanel source="honeypot" label="Honeypot" {...styleProps} />);

  expect(await screen.findByText(/no live logs found for honeypot/i)).toBeInTheDocument();
});

test("renders error state and keeps polling retry path", async () => {
  loadLiveLogs.mockRejectedValueOnce(new Error("Network failed")).mockResolvedValueOnce([eventOne]);

  render(<LiveLogsPanel source="pfsense" {...styleProps} />);

  expect(await screen.findByText("Network failed")).toBeInTheDocument();

  await act(async () => {
    jest.advanceTimersByTime(5000);
  });

  await waitFor(() => {
    expect(screen.getByText("first event")).toBeInTheDocument();
  });
});

test("polling merges new rows without duplicating existing ids", async () => {
  loadLiveLogs
    .mockResolvedValueOnce([eventOne])
    .mockResolvedValueOnce([eventOne, eventTwo]);

  render(<LiveLogsPanel source="pfsense" {...styleProps} />);

  expect(await screen.findByText("first event")).toBeInTheDocument();

  await act(async () => {
    jest.advanceTimersByTime(5000);
  });

  await waitFor(() => {
    expect(screen.getByText("second event")).toBeInTheDocument();
  });

  expect(screen.getAllByText("first event")).toHaveLength(1);
  expect(loadLiveLogs).toHaveBeenLastCalledWith({ source: "pfsense", afterId: 1 });
});

test("clears polling interval on unmount", async () => {
  loadLiveLogs.mockResolvedValue([eventOne]);
  const clearSpy = jest.spyOn(global, "clearInterval");

  const { unmount } = render(<LiveLogsPanel source="pfsense" {...styleProps} />);
  await screen.findByText("first event");

  unmount();

  expect(clearSpy).toHaveBeenCalled();
});
