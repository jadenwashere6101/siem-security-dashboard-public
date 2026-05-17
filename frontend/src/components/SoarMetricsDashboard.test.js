import React from "react";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import SoarMetricsDashboard, {
  formatRelativeTime,
  REFRESH_INTERVAL_MS,
} from "./SoarMetricsDashboard";
import { getDeadLetterMetrics } from "../services/deadLetterService";
import {
  getApprovalMetrics,
  getIncidentMetrics,
  getNotificationDeliveryMetrics,
  getPlaybookMetrics,
} from "../services/metricsService";
import { loadSoarQueueStatus } from "../services/soarQueueService";

jest.mock("recharts", () => {
  const React = require("react");
  return {
    BarChart: ({ children }) =>
      React.createElement("div", { "data-testid": "bar-chart" }, children),
    Bar: () => null,
    XAxis: () => null,
    YAxis: () => null,
    Tooltip: () => null,
    ResponsiveContainer: ({ children }) =>
      React.createElement("div", null, children),
    Cell: () => null,
  };
});

jest.mock("../services/metricsService", () => ({
  getPlaybookMetrics: jest.fn(),
  getNotificationDeliveryMetrics: jest.fn(),
  getIncidentMetrics: jest.fn(),
  getApprovalMetrics: jest.fn(),
}));

jest.mock("../services/deadLetterService", () => ({
  getDeadLetterMetrics: jest.fn(),
}));

jest.mock("../services/soarQueueService", () => ({
  loadSoarQueueStatus: jest.fn(),
  loadRecentSoarQueueItems: jest.fn(),
  loadSoarQueueItem: jest.fn(),
  runSoarWorkerOnce: jest.fn(),
}));

const styleProps = {
  cardStyle: {},
  cardHeaderStyle: {},
  cardTitleStyle: {},
  cardSubtitleStyle: {},
};

const analystProps = { ...styleProps, userRole: "analyst" };
const adminProps = { ...styleProps, userRole: "super_admin" };

const emptyData = {};

function mockAllResolved() {
  getPlaybookMetrics.mockResolvedValue(emptyData);
  getDeadLetterMetrics.mockResolvedValue(emptyData);
  getNotificationDeliveryMetrics.mockResolvedValue(emptyData);
  getIncidentMetrics.mockResolvedValue(emptyData);
  getApprovalMetrics.mockResolvedValue(emptyData);
  loadSoarQueueStatus.mockResolvedValue(emptyData);
}

// --- Fixture data for section content tests ---

const playbookFixture = {
  total_executions: 42,
  recent: { success: 10, failed: 3 },
  approval_gated: { awaiting_approval: 2 },
  stale_running_count: 1,
  by_status: {
    pending: 5,
    running: 2,
    awaiting_approval: 2,
    success: 28,
    failed: 3,
    abandoned: 0,
  },
  by_playbook_id: [
    {
      playbook_id: "pb-alpha",
      total: 20,
      by_status: {
        pending: 1,
        running: 1,
        awaiting_approval: 0,
        success: 15,
        failed: 3,
        abandoned: 0,
      },
    },
    {
      playbook_id: "pb-beta",
      total: 22,
      by_status: {
        pending: 4,
        running: 1,
        awaiting_approval: 2,
        success: 13,
        failed: 0,
        abandoned: 0,
      },
    },
  ],
};

const deadLetterFixture = {
  open: 3,
  retrying: 1,
  oldest_active_at: "2026-05-15T10:00:00Z",
  by_status: { open: 3, retrying: 1, retried: 2, dismissed: 0 },
  by_failure_class: { timeout: 4, validation_error: 2 },
};

const notificationFixture = {
  total_delivery_attempts: 150,
  recent: { success: 45, failed: 5, timeout: 0, blocked: 2 },
  by_mode: { simulation: 100, real: 50 },
  by_provider: { slack: 80, teams: 50 },
  circuit_breaker_state_counts: { closed: 2, open: 0, half_open: 1 },
};

const incidentFixture = {
  by_status: { open: 5, investigating: 3, resolved: 10, closed: 2 },
  by_severity: { CRITICAL: 2, HIGH: 5, MEDIUM: 8, LOW: 3 },
  open_high_critical: 7,
};

const approvalFixture = {
  pending_count: 4,
  by_status: { pending: 4, approved: 12, denied: 2, expired: 1 },
};

const queueFixture = {
  counts: {
    pending: 3,
    running: 1,
    awaiting_approval: 0,
    success: 10,
    failed: 2,
    skipped: 0,
  },
  generated_at: "2026-05-17T12:00:00Z",
};

function mockAllFixtures() {
  getPlaybookMetrics.mockResolvedValue(playbookFixture);
  getDeadLetterMetrics.mockResolvedValue(deadLetterFixture);
  getNotificationDeliveryMetrics.mockResolvedValue(notificationFixture);
  getIncidentMetrics.mockResolvedValue(incidentFixture);
  getApprovalMetrics.mockResolvedValue(approvalFixture);
  loadSoarQueueStatus.mockResolvedValue(queueFixture);
}

describe("SoarMetricsDashboard", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  // --- Section rendering ---

  test("renders five section headings for analyst role", async () => {
    mockAllResolved();
    render(<SoarMetricsDashboard {...analystProps} />);
    expect(screen.getByRole("region", { name: "Playbook Metrics" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Dead Letter Metrics" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Notification Delivery Metrics" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Incident Metrics" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Approval Metrics" })).toBeInTheDocument();
  });

  test("renders SOAR Queue Health section for super_admin", () => {
    mockAllResolved();
    render(<SoarMetricsDashboard {...adminProps} />);
    expect(screen.getByRole("region", { name: "SOAR Queue Health" })).toBeInTheDocument();
  });

  test("does not render SOAR Queue Health section for analyst", () => {
    mockAllResolved();
    render(<SoarMetricsDashboard {...analystProps} />);
    expect(
      screen.queryByRole("region", { name: "SOAR Queue Health" })
    ).not.toBeInTheDocument();
  });

  test("renders panel title and Refresh now button", () => {
    mockAllResolved();
    render(<SoarMetricsDashboard {...analystProps} />);
    expect(screen.getByText("SOAR Metrics Dashboard")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Refresh now" })).toBeInTheDocument();
  });

  test("shows last refreshed timestamp after data loads", async () => {
    mockAllResolved();
    render(<SoarMetricsDashboard {...analystProps} />);
    await waitFor(() => {
      expect(screen.getByText(/Last refreshed:/)).toBeInTheDocument();
    });
  });

  // --- Loading states ---

  test("shows per-section loading indicator on initial render", () => {
    getPlaybookMetrics.mockReturnValue(new Promise(() => {}));
    getDeadLetterMetrics.mockReturnValue(new Promise(() => {}));
    getNotificationDeliveryMetrics.mockReturnValue(new Promise(() => {}));
    getIncidentMetrics.mockReturnValue(new Promise(() => {}));
    getApprovalMetrics.mockReturnValue(new Promise(() => {}));

    render(<SoarMetricsDashboard {...analystProps} />);

    expect(screen.getByLabelText("Loading Playbook Metrics")).toBeInTheDocument();
    expect(screen.getByLabelText("Loading Dead Letter Metrics")).toBeInTheDocument();
    expect(screen.getByLabelText("Loading Notification Delivery Metrics")).toBeInTheDocument();
    expect(screen.getByLabelText("Loading Incident Metrics")).toBeInTheDocument();
    expect(screen.getByLabelText("Loading Approval Metrics")).toBeInTheDocument();
  });

  test("clears all loading indicators after successful data load", async () => {
    mockAllResolved();
    render(<SoarMetricsDashboard {...analystProps} />);
    await waitFor(() => {
      expect(
        screen.queryByLabelText("Loading Playbook Metrics")
      ).not.toBeInTheDocument();
      expect(
        screen.queryByLabelText("Loading Dead Letter Metrics")
      ).not.toBeInTheDocument();
      expect(
        screen.queryByLabelText("Loading Notification Delivery Metrics")
      ).not.toBeInTheDocument();
      expect(
        screen.queryByLabelText("Loading Incident Metrics")
      ).not.toBeInTheDocument();
      expect(
        screen.queryByLabelText("Loading Approval Metrics")
      ).not.toBeInTheDocument();
    });
  });

  // --- Per-section error isolation ---

  test("shows error in one section without affecting other sections", async () => {
    getPlaybookMetrics.mockRejectedValue(new Error("Playbook load failed"));
    getDeadLetterMetrics.mockResolvedValue(emptyData);
    getNotificationDeliveryMetrics.mockResolvedValue(emptyData);
    getIncidentMetrics.mockResolvedValue(emptyData);
    getApprovalMetrics.mockResolvedValue(emptyData);

    render(<SoarMetricsDashboard {...analystProps} />);

    await waitFor(() => {
      expect(screen.getByText("Playbook load failed")).toBeInTheDocument();
    });

    expect(
      screen.queryByLabelText("Loading Dead Letter Metrics")
    ).not.toBeInTheDocument();
    const dlSection = screen.getByRole("region", { name: "Dead Letter Metrics" });
    expect(within(dlSection).queryByRole("alert")).not.toBeInTheDocument();

    const notifSection = screen.getByRole("region", { name: "Notification Delivery Metrics" });
    expect(within(notifSection).queryByRole("alert")).not.toBeInTheDocument();
  });

  test("shows errors independently when multiple sections fail", async () => {
    getPlaybookMetrics.mockRejectedValue(new Error("Playbook error"));
    getDeadLetterMetrics.mockRejectedValue(new Error("Dead letter error"));
    getNotificationDeliveryMetrics.mockResolvedValue(emptyData);
    getIncidentMetrics.mockResolvedValue(emptyData);
    getApprovalMetrics.mockResolvedValue(emptyData);

    render(<SoarMetricsDashboard {...analystProps} />);

    await waitFor(() => {
      expect(screen.getByText("Playbook error")).toBeInTheDocument();
      expect(screen.getByText("Dead letter error")).toBeInTheDocument();
    });

    const notifSection = screen.getByRole("region", { name: "Notification Delivery Metrics" });
    expect(within(notifSection).queryByRole("alert")).not.toBeInTheDocument();
    expect(
      screen.queryByLabelText("Loading Notification Delivery Metrics")
    ).not.toBeInTheDocument();
  });

  test("does not crash when all sections fail", async () => {
    getPlaybookMetrics.mockRejectedValue(new Error("e1"));
    getDeadLetterMetrics.mockRejectedValue(new Error("e2"));
    getNotificationDeliveryMetrics.mockRejectedValue(new Error("e3"));
    getIncidentMetrics.mockRejectedValue(new Error("e4"));
    getApprovalMetrics.mockRejectedValue(new Error("e5"));

    render(<SoarMetricsDashboard {...analystProps} />);

    await waitFor(() => {
      expect(screen.getByText("e1")).toBeInTheDocument();
      expect(screen.getByText("e5")).toBeInTheDocument();
    });

    expect(screen.getByText("SOAR Metrics Dashboard")).toBeInTheDocument();
    expect(screen.getAllByRole("alert")).toHaveLength(5);
  });

  // --- Promise.allSettled partial failure ---

  test("Promise.allSettled: successful sections render while failed sections show errors", async () => {
    getPlaybookMetrics.mockResolvedValue(emptyData);
    getDeadLetterMetrics.mockRejectedValue(new Error("dl failed"));
    getNotificationDeliveryMetrics.mockResolvedValue(emptyData);
    getIncidentMetrics.mockRejectedValue(new Error("incident failed"));
    getApprovalMetrics.mockResolvedValue(emptyData);

    render(<SoarMetricsDashboard {...analystProps} />);

    await waitFor(() => {
      expect(screen.getByText("dl failed")).toBeInTheDocument();
      expect(screen.getByText("incident failed")).toBeInTheDocument();
    });

    const pbSection = screen.getByRole("region", { name: "Playbook Metrics" });
    expect(within(pbSection).queryByRole("alert")).not.toBeInTheDocument();
    expect(within(pbSection).queryByLabelText("Loading Playbook Metrics")).not.toBeInTheDocument();

    const approvalSection = screen.getByRole("region", { name: "Approval Metrics" });
    expect(within(approvalSection).queryByRole("alert")).not.toBeInTheDocument();

    const dlSection = screen.getByRole("region", { name: "Dead Letter Metrics" });
    expect(within(dlSection).getByRole("alert")).toBeInTheDocument();

    const incidentSection = screen.getByRole("region", { name: "Incident Metrics" });
    expect(within(incidentSection).getByRole("alert")).toBeInTheDocument();
  });

  // --- Role gating for queue ---

  test("does not call loadSoarQueueStatus for analyst", async () => {
    mockAllResolved();
    render(<SoarMetricsDashboard {...analystProps} />);
    await waitFor(() => {
      expect(getPlaybookMetrics).toHaveBeenCalled();
    });
    expect(loadSoarQueueStatus).not.toHaveBeenCalled();
  });

  test("calls loadSoarQueueStatus for super_admin", async () => {
    mockAllResolved();
    render(<SoarMetricsDashboard {...adminProps} />);
    await waitFor(() => {
      expect(loadSoarQueueStatus).toHaveBeenCalled();
    });
  });

  test("SOAR Queue Health section loading clears for analyst without a fetch", async () => {
    mockAllResolved();
    render(<SoarMetricsDashboard {...analystProps} />);
    await waitFor(() => {
      expect(getPlaybookMetrics).toHaveBeenCalled();
    });
    expect(
      screen.queryByLabelText("Loading SOAR Queue Health")
    ).not.toBeInTheDocument();
  });

  // --- Manual refresh ---

  test("Refresh now button triggers a second fetch of all sections", async () => {
    mockAllResolved();
    render(<SoarMetricsDashboard {...analystProps} />);
    await waitFor(() => {
      expect(getPlaybookMetrics).toHaveBeenCalledTimes(1);
    });

    await userEvent.click(screen.getByRole("button", { name: "Refresh now" }));

    await waitFor(() => {
      expect(getPlaybookMetrics).toHaveBeenCalledTimes(2);
      expect(getDeadLetterMetrics).toHaveBeenCalledTimes(2);
      expect(getNotificationDeliveryMetrics).toHaveBeenCalledTimes(2);
      expect(getIncidentMetrics).toHaveBeenCalledTimes(2);
      expect(getApprovalMetrics).toHaveBeenCalledTimes(2);
    });
  });

  test("Refresh now button clears section errors before re-fetching", async () => {
    getPlaybookMetrics
      .mockRejectedValueOnce(new Error("First load failed"))
      .mockResolvedValue(emptyData);
    getDeadLetterMetrics.mockResolvedValue(emptyData);
    getNotificationDeliveryMetrics.mockResolvedValue(emptyData);
    getIncidentMetrics.mockResolvedValue(emptyData);
    getApprovalMetrics.mockResolvedValue(emptyData);

    render(<SoarMetricsDashboard {...analystProps} />);

    await waitFor(() => {
      expect(screen.getByText("First load failed")).toBeInTheDocument();
    });

    await userEvent.click(screen.getByRole("button", { name: "Refresh now" }));

    await waitFor(() => {
      expect(screen.queryByText("First load failed")).not.toBeInTheDocument();
    });
  });

  // --- Interval setup and cleanup ---

  test("registers setInterval on mount with REFRESH_INTERVAL_MS", () => {
    mockAllResolved();
    const spy = jest.spyOn(global, "setInterval");
    render(<SoarMetricsDashboard {...analystProps} />);
    expect(spy).toHaveBeenCalledWith(expect.any(Function), REFRESH_INTERVAL_MS);
    spy.mockRestore();
  });

  test("calls clearInterval on unmount", async () => {
    mockAllResolved();
    const clearSpy = jest.spyOn(global, "clearInterval");
    const { unmount } = render(<SoarMetricsDashboard {...analystProps} />);
    await waitFor(() => expect(getPlaybookMetrics).toHaveBeenCalled());
    unmount();
    expect(clearSpy).toHaveBeenCalled();
    clearSpy.mockRestore();
  });

  // --- Auto-refresh via fake timers ---

  test("auto-refresh calls all service functions again after REFRESH_INTERVAL_MS", async () => {
    jest.useFakeTimers();
    mockAllResolved();

    render(<SoarMetricsDashboard {...analystProps} />);

    await act(async () => {});

    expect(getPlaybookMetrics).toHaveBeenCalledTimes(1);

    act(() => {
      jest.advanceTimersByTime(REFRESH_INTERVAL_MS);
    });

    await act(async () => {});

    expect(getPlaybookMetrics).toHaveBeenCalledTimes(2);
    expect(getDeadLetterMetrics).toHaveBeenCalledTimes(2);
    expect(getIncidentMetrics).toHaveBeenCalledTimes(2);
    expect(getApprovalMetrics).toHaveBeenCalledTimes(2);
  });

  test("interval does not fire after unmount", async () => {
    jest.useFakeTimers();
    mockAllResolved();

    const { unmount } = render(<SoarMetricsDashboard {...analystProps} />);
    await act(async () => {});

    expect(getPlaybookMetrics).toHaveBeenCalledTimes(1);

    unmount();

    act(() => {
      jest.advanceTimersByTime(REFRESH_INTERVAL_MS);
    });
    await act(async () => {});

    expect(getPlaybookMetrics).toHaveBeenCalledTimes(1);
  });

  // --- Section content rendering ---

  describe("Playbook Metrics section", () => {
    test("renders metric cards with values from fixture data", async () => {
      mockAllFixtures();
      render(<SoarMetricsDashboard {...analystProps} />);
      const section = screen.getByRole("region", { name: "Playbook Metrics" });
      await waitFor(() => {
        expect(within(section).getByText("42")).toBeInTheDocument();
      });
      expect(within(section).getByText("10")).toBeInTheDocument();
      expect(within(section).getByText("3")).toBeInTheDocument();
      expect(within(section).getByText("2")).toBeInTheDocument();
      expect(within(section).getByText("1")).toBeInTheDocument();
    });

    test("renders stale_running_count card when field is present in data", async () => {
      mockAllFixtures();
      render(<SoarMetricsDashboard {...analystProps} />);
      const section = screen.getByRole("region", { name: "Playbook Metrics" });
      await waitFor(() => {
        expect(within(section).getByText("Stale Running")).toBeInTheDocument();
      });
    });

    test("omits stale_running_count card when field is absent from data", async () => {
      const { stale_running_count: _omit, ...withoutStale } = playbookFixture;
      getPlaybookMetrics.mockResolvedValue(withoutStale);
      getDeadLetterMetrics.mockResolvedValue(emptyData);
      getNotificationDeliveryMetrics.mockResolvedValue(emptyData);
      getIncidentMetrics.mockResolvedValue(emptyData);
      getApprovalMetrics.mockResolvedValue(emptyData);

      render(<SoarMetricsDashboard {...analystProps} />);
      const section = await screen.findByRole("region", { name: "Playbook Metrics" });
      expect(within(section).queryByText("Stale Running")).not.toBeInTheDocument();
    });

    test("renders chart container when by_status has non-zero counts", async () => {
      mockAllFixtures();
      render(<SoarMetricsDashboard {...analystProps} />);
      const section = await screen.findByRole("region", { name: "Playbook Metrics" });
      expect(within(section).getByTestId("chart-container")).toBeInTheDocument();
    });

    test("renders empty state text when by_status is all zeros", async () => {
      getPlaybookMetrics.mockResolvedValue({
        by_status: {
          pending: 0,
          running: 0,
          awaiting_approval: 0,
          success: 0,
          failed: 0,
          abandoned: 0,
        },
      });
      getDeadLetterMetrics.mockResolvedValue(emptyData);
      getNotificationDeliveryMetrics.mockResolvedValue(emptyData);
      getIncidentMetrics.mockResolvedValue(emptyData);
      getApprovalMetrics.mockResolvedValue(emptyData);

      render(<SoarMetricsDashboard {...analystProps} />);
      const section = await screen.findByRole("region", { name: "Playbook Metrics" });
      expect(within(section).getByText("No executions recorded.")).toBeInTheDocument();
    });

    test("renders simulation notice", async () => {
      mockAllFixtures();
      render(<SoarMetricsDashboard {...analystProps} />);
      const section = await screen.findByRole("region", { name: "Playbook Metrics" });
      expect(within(section).getByRole("note")).toBeInTheDocument();
    });

    test("collapsible table toggle is rendered when rows exist", async () => {
      mockAllFixtures();
      render(<SoarMetricsDashboard {...analystProps} />);
      const section = await screen.findByRole("region", { name: "Playbook Metrics" });
      const toggle = within(section).getByRole("button", { name: /Per-Playbook Breakdown/ });
      expect(toggle).toBeInTheDocument();
      expect(toggle).toHaveAttribute("aria-expanded", "false");
    });

    test("clicking toggle expands the per-playbook breakdown table", async () => {
      mockAllFixtures();
      render(<SoarMetricsDashboard {...analystProps} />);
      const section = await screen.findByRole("region", { name: "Playbook Metrics" });
      const toggle = within(section).getByRole("button", { name: /Per-Playbook Breakdown/ });
      await userEvent.click(toggle);
      expect(toggle).toHaveAttribute("aria-expanded", "true");
      expect(within(section).getByText("pb-alpha")).toBeInTheDocument();
      expect(within(section).getByText("pb-beta")).toBeInTheDocument();
    });

    test("playbook breakdown table is hidden by default", async () => {
      mockAllFixtures();
      render(<SoarMetricsDashboard {...analystProps} />);
      await screen.findByRole("region", { name: "Playbook Metrics" });
      expect(screen.queryByLabelText("Playbook breakdown table")).not.toBeInTheDocument();
    });

    test("does not render table toggle when by_playbook_id is absent", async () => {
      getPlaybookMetrics.mockResolvedValue({ total_executions: 5 });
      getDeadLetterMetrics.mockResolvedValue(emptyData);
      getNotificationDeliveryMetrics.mockResolvedValue(emptyData);
      getIncidentMetrics.mockResolvedValue(emptyData);
      getApprovalMetrics.mockResolvedValue(emptyData);

      render(<SoarMetricsDashboard {...analystProps} />);
      await screen.findByRole("region", { name: "Playbook Metrics" });
      expect(
        screen.queryByRole("button", { name: /Per-Playbook Breakdown/ })
      ).not.toBeInTheDocument();
    });
  });

  describe("Dead Letter Metrics section", () => {
    test("renders open and retrying metric card labels", async () => {
      mockAllFixtures();
      render(<SoarMetricsDashboard {...analystProps} />);
      const section = await screen.findByRole("region", { name: "Dead Letter Metrics" });
      expect(within(section).getByText("Open")).toBeInTheDocument();
      expect(within(section).getByText("Retrying")).toBeInTheDocument();
    });

    test("renders chart container when by_status has non-zero counts", async () => {
      mockAllFixtures();
      render(<SoarMetricsDashboard {...analystProps} />);
      const section = await screen.findByRole("region", { name: "Dead Letter Metrics" });
      expect(within(section).getByTestId("chart-container")).toBeInTheDocument();
    });

    test("renders failure class table rows from fixture data", async () => {
      mockAllFixtures();
      render(<SoarMetricsDashboard {...analystProps} />);
      const section = await screen.findByRole("region", { name: "Dead Letter Metrics" });
      expect(within(section).getByText("timeout")).toBeInTheDocument();
      expect(within(section).getByText("validation_error")).toBeInTheDocument();
    });

    test("shows no failures message when by_failure_class is absent", async () => {
      getPlaybookMetrics.mockResolvedValue(emptyData);
      getDeadLetterMetrics.mockResolvedValue({ open: 0, retrying: 0 });
      getNotificationDeliveryMetrics.mockResolvedValue(emptyData);
      getIncidentMetrics.mockResolvedValue(emptyData);
      getApprovalMetrics.mockResolvedValue(emptyData);

      render(<SoarMetricsDashboard {...analystProps} />);
      const section = await screen.findByRole("region", { name: "Dead Letter Metrics" });
      expect(within(section).getByText("No failures recorded.")).toBeInTheDocument();
    });

    test("shows empty state when by_status is all zeros", async () => {
      getPlaybookMetrics.mockResolvedValue(emptyData);
      getDeadLetterMetrics.mockResolvedValue({
        by_status: { open: 0, retrying: 0, retried: 0, dismissed: 0 },
      });
      getNotificationDeliveryMetrics.mockResolvedValue(emptyData);
      getIncidentMetrics.mockResolvedValue(emptyData);
      getApprovalMetrics.mockResolvedValue(emptyData);

      render(<SoarMetricsDashboard {...analystProps} />);
      const section = await screen.findByRole("region", { name: "Dead Letter Metrics" });
      expect(within(section).getByText("No dead letters recorded.")).toBeInTheDocument();
    });

    test("shows None for Oldest Active when oldest_active_at is absent", async () => {
      getPlaybookMetrics.mockResolvedValue(emptyData);
      getDeadLetterMetrics.mockResolvedValue({ open: 0, retrying: 0 });
      getNotificationDeliveryMetrics.mockResolvedValue(emptyData);
      getIncidentMetrics.mockResolvedValue(emptyData);
      getApprovalMetrics.mockResolvedValue(emptyData);

      render(<SoarMetricsDashboard {...analystProps} />);
      const section = await screen.findByRole("region", { name: "Dead Letter Metrics" });
      expect(within(section).getByText("None")).toBeInTheDocument();
    });
  });

  describe("Notification Delivery Metrics section", () => {
    test("renders total, success, and failed+blocked metric card labels", async () => {
      mockAllFixtures();
      render(<SoarMetricsDashboard {...analystProps} />);
      const section = await screen.findByRole("region", {
        name: "Notification Delivery Metrics",
      });
      expect(within(section).getByText("Total Attempts")).toBeInTheDocument();
      expect(within(section).getByText("150")).toBeInTheDocument();
      expect(within(section).getByText("45")).toBeInTheDocument();
      expect(within(section).getByText("7")).toBeInTheDocument(); // failed(5) + blocked(2)
    });

    test("renders simulation/real combined card value", async () => {
      mockAllFixtures();
      render(<SoarMetricsDashboard {...analystProps} />);
      const section = await screen.findByRole("region", {
        name: "Notification Delivery Metrics",
      });
      expect(within(section).getByText("100 / 50")).toBeInTheDocument();
    });

    test("renders mode breakdown metric cards", async () => {
      mockAllFixtures();
      render(<SoarMetricsDashboard {...analystProps} />);
      const section = await screen.findByRole("region", {
        name: "Notification Delivery Metrics",
      });
      expect(within(section).getByText("Mode: simulation")).toBeInTheDocument();
      expect(within(section).getByText("Mode: real")).toBeInTheDocument();
    });

    test("renders notification operational notice", async () => {
      mockAllFixtures();
      render(<SoarMetricsDashboard {...analystProps} />);
      const section = await screen.findByRole("region", {
        name: "Notification Delivery Metrics",
      });
      expect(within(section).getByRole("note")).toBeInTheDocument();
    });

    test("renders provider chart when providers have data", async () => {
      mockAllFixtures();
      render(<SoarMetricsDashboard {...analystProps} />);
      const section = await screen.findByRole("region", {
        name: "Notification Delivery Metrics",
      });
      expect(within(section).getByTestId("chart-container")).toBeInTheDocument();
    });

    test("renders empty state when no provider breakdown available", async () => {
      getPlaybookMetrics.mockResolvedValue(emptyData);
      getDeadLetterMetrics.mockResolvedValue(emptyData);
      getNotificationDeliveryMetrics.mockResolvedValue({ total_delivery_attempts: 0 });
      getIncidentMetrics.mockResolvedValue(emptyData);
      getApprovalMetrics.mockResolvedValue(emptyData);

      render(<SoarMetricsDashboard {...analystProps} />);
      const section = await screen.findByRole("region", {
        name: "Notification Delivery Metrics",
      });
      expect(
        within(section).getByText("No provider breakdown available.")
      ).toBeInTheDocument();
    });
  });

  describe("Incident Metrics section", () => {
    test("renders open+investigating, resolved+closed, and open critical/high cards", async () => {
      mockAllFixtures();
      render(<SoarMetricsDashboard {...analystProps} />);
      const section = await screen.findByRole("region", { name: "Incident Metrics" });
      expect(within(section).getByText("Open + Investigating")).toBeInTheDocument();
      expect(within(section).getByText("8")).toBeInTheDocument(); // 5 + 3
      expect(within(section).getByText("12")).toBeInTheDocument(); // 10 + 2
      expect(within(section).getByText("7")).toBeInTheDocument(); // open_high_critical
    });

    test("renders both status and severity chart containers", async () => {
      mockAllFixtures();
      render(<SoarMetricsDashboard {...analystProps} />);
      const section = await screen.findByRole("region", { name: "Incident Metrics" });
      const charts = within(section).getAllByTestId("chart-container");
      expect(charts).toHaveLength(2);
    });

    test("renders empty state when incident status counts are all zero", async () => {
      getPlaybookMetrics.mockResolvedValue(emptyData);
      getDeadLetterMetrics.mockResolvedValue(emptyData);
      getNotificationDeliveryMetrics.mockResolvedValue(emptyData);
      getIncidentMetrics.mockResolvedValue({
        by_status: { open: 0, investigating: 0, resolved: 0, closed: 0 },
        by_severity: { CRITICAL: 1, HIGH: 0, MEDIUM: 0, LOW: 0 },
      });
      getApprovalMetrics.mockResolvedValue(emptyData);

      render(<SoarMetricsDashboard {...analystProps} />);
      const section = await screen.findByRole("region", { name: "Incident Metrics" });
      expect(within(section).getByText("No incidents recorded.")).toBeInTheDocument();
    });
  });

  describe("Approval Metrics section", () => {
    test("renders pending, approved, denied, and expired card labels", async () => {
      mockAllFixtures();
      render(<SoarMetricsDashboard {...analystProps} />);
      const section = await screen.findByRole("region", { name: "Approval Metrics" });
      expect(within(section).getByText("Pending")).toBeInTheDocument();
      expect(within(section).getByText("Approved")).toBeInTheDocument();
      expect(within(section).getByText("Denied")).toBeInTheDocument();
      expect(within(section).getByText("Expired")).toBeInTheDocument();
    });

    test("uses pending_count for the pending card value", async () => {
      mockAllFixtures();
      render(<SoarMetricsDashboard {...analystProps} />);
      const section = await screen.findByRole("region", { name: "Approval Metrics" });
      expect(within(section).getByText("4")).toBeInTheDocument();
    });

    test("falls back to by_status.pending when pending_count is absent", async () => {
      getPlaybookMetrics.mockResolvedValue(emptyData);
      getDeadLetterMetrics.mockResolvedValue(emptyData);
      getNotificationDeliveryMetrics.mockResolvedValue(emptyData);
      getIncidentMetrics.mockResolvedValue(emptyData);
      getApprovalMetrics.mockResolvedValue({
        by_status: { pending: 7, approved: 0, denied: 0, expired: 0 },
      });

      render(<SoarMetricsDashboard {...analystProps} />);
      const section = await screen.findByRole("region", { name: "Approval Metrics" });
      expect(within(section).getByText("7")).toBeInTheDocument();
    });

    test("renders empty state when all approval status counts are zero", async () => {
      getPlaybookMetrics.mockResolvedValue(emptyData);
      getDeadLetterMetrics.mockResolvedValue(emptyData);
      getNotificationDeliveryMetrics.mockResolvedValue(emptyData);
      getIncidentMetrics.mockResolvedValue(emptyData);
      getApprovalMetrics.mockResolvedValue({
        by_status: { pending: 0, approved: 0, denied: 0, expired: 0 },
      });

      render(<SoarMetricsDashboard {...analystProps} />);
      const section = await screen.findByRole("region", { name: "Approval Metrics" });
      expect(within(section).getByText("No approvals recorded.")).toBeInTheDocument();
    });
  });

  describe("SOAR Queue Health section (super_admin only)", () => {
    test("renders queue metric card labels with fixture data", async () => {
      mockAllFixtures();
      render(<SoarMetricsDashboard {...adminProps} />);
      const section = await screen.findByRole("region", { name: "SOAR Queue Health" });
      expect(within(section).getByText("Pending")).toBeInTheDocument();
      expect(within(section).getByText("Running")).toBeInTheDocument();
      expect(within(section).getByText("Failed")).toBeInTheDocument();
      expect(within(section).getByText("3")).toBeInTheDocument(); // pending count
    });

    test("renders queue snapshot timestamp", async () => {
      mockAllFixtures();
      render(<SoarMetricsDashboard {...adminProps} />);
      const section = await screen.findByRole("region", { name: "SOAR Queue Health" });
      expect(within(section).getByLabelText("Queue snapshot timestamp")).toBeInTheDocument();
      expect(within(section).getByText(/Queue snapshot as of/)).toBeInTheDocument();
    });

    test("renders chart container when queue counts have non-zero values", async () => {
      mockAllFixtures();
      render(<SoarMetricsDashboard {...adminProps} />);
      const section = await screen.findByRole("region", { name: "SOAR Queue Health" });
      expect(within(section).getByTestId("chart-container")).toBeInTheDocument();
    });

    test("renders empty queue state when all counts are zero", async () => {
      getPlaybookMetrics.mockResolvedValue(emptyData);
      getDeadLetterMetrics.mockResolvedValue(emptyData);
      getNotificationDeliveryMetrics.mockResolvedValue(emptyData);
      getIncidentMetrics.mockResolvedValue(emptyData);
      getApprovalMetrics.mockResolvedValue(emptyData);
      loadSoarQueueStatus.mockResolvedValue({
        counts: {
          pending: 0,
          running: 0,
          awaiting_approval: 0,
          success: 0,
          failed: 0,
          skipped: 0,
        },
      });

      render(<SoarMetricsDashboard {...adminProps} />);
      const section = await screen.findByRole("region", { name: "SOAR Queue Health" });
      expect(within(section).getByText("No queue entries recorded.")).toBeInTheDocument();
    });
  });

  // --- formatRelativeTime unit tests ---

  describe("formatRelativeTime helper", () => {
    const NOW_MS = new Date("2026-05-17T12:00:00Z").getTime();

    beforeEach(() => {
      jest.spyOn(Date, "now").mockReturnValue(NOW_MS);
    });

    afterEach(() => {
      jest.restoreAllMocks();
    });

    test("returns null for null input", () => {
      expect(formatRelativeTime(null)).toBeNull();
    });

    test("returns null for undefined input", () => {
      expect(formatRelativeTime(undefined)).toBeNull();
    });

    test("returns the original value for an invalid ISO string", () => {
      expect(formatRelativeTime("not-a-date")).toBe("not-a-date");
    });

    test("returns just now for a timestamp less than 2 minutes ago", () => {
      const ts = new Date(NOW_MS - 60_000).toISOString();
      expect(formatRelativeTime(ts)).toBe("just now");
    });

    test("returns X minutes ago for a timestamp within the hour", () => {
      const ts = new Date(NOW_MS - 10 * 60_000).toISOString();
      expect(formatRelativeTime(ts)).toBe("10 minutes ago");
    });

    test("returns 1 hour ago without plural s", () => {
      const ts = new Date(NOW_MS - 61 * 60_000).toISOString();
      expect(formatRelativeTime(ts)).toBe("1 hour ago");
    });

    test("returns X hours ago for a timestamp within 24 hours", () => {
      const ts = new Date(NOW_MS - 3 * 60 * 60_000).toISOString();
      expect(formatRelativeTime(ts)).toBe("3 hours ago");
    });

    test("returns X days ago for a timestamp older than 24 hours", () => {
      const ts = new Date(NOW_MS - 2 * 24 * 60 * 60_000).toISOString();
      expect(formatRelativeTime(ts)).toBe("2 days ago");
    });
  });

  // --- Null and missing field handling ---

  describe("null and missing field handling", () => {
    test("renders without crashing when all section data is empty objects", async () => {
      mockAllResolved();
      render(<SoarMetricsDashboard {...analystProps} />);
      await waitFor(() => {
        expect(screen.queryByLabelText("Loading Playbook Metrics")).not.toBeInTheDocument();
        expect(screen.queryByLabelText("Loading Dead Letter Metrics")).not.toBeInTheDocument();
      });
      expect(screen.getByText("SOAR Metrics Dashboard")).toBeInTheDocument();
    });

    test("handles null oldest_active_at by showing None", async () => {
      getPlaybookMetrics.mockResolvedValue(emptyData);
      getDeadLetterMetrics.mockResolvedValue({ oldest_active_at: null });
      getNotificationDeliveryMetrics.mockResolvedValue(emptyData);
      getIncidentMetrics.mockResolvedValue(emptyData);
      getApprovalMetrics.mockResolvedValue(emptyData);

      render(<SoarMetricsDashboard {...analystProps} />);
      const section = screen.getByRole("region", { name: "Dead Letter Metrics" });
      await waitFor(() => {
        expect(within(section).getByText("None")).toBeInTheDocument();
      });
    });

    test("handles missing open_high_critical by falling back to open_high_critical_count", async () => {
      getPlaybookMetrics.mockResolvedValue(emptyData);
      getDeadLetterMetrics.mockResolvedValue(emptyData);
      getNotificationDeliveryMetrics.mockResolvedValue(emptyData);
      getIncidentMetrics.mockResolvedValue({
        by_status: { open: 1, investigating: 0, resolved: 0, closed: 0 },
        by_severity: {},
        open_high_critical_count: 9,
      });
      getApprovalMetrics.mockResolvedValue(emptyData);

      render(<SoarMetricsDashboard {...analystProps} />);
      const section = screen.getByRole("region", { name: "Incident Metrics" });
      await waitFor(() => {
        expect(within(section).getByText("9")).toBeInTheDocument();
      });
    });
  });
});
