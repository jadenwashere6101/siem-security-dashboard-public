import React from "react";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import SoarMetricsDashboard, { REFRESH_INTERVAL_MS } from "./SoarMetricsDashboard";
import { getDeadLetterMetrics } from "../services/deadLetterService";
import {
  getApprovalMetrics,
  getIncidentMetrics,
  getNotificationDeliveryMetrics,
  getPlaybookMetrics,
} from "../services/metricsService";
import { loadSoarQueueStatus } from "../services/soarQueueService";

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

    // Dead Letter and others resolved — no loading, no alert
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

    // Dashboard header is still present
    expect(screen.getByText("SOAR Metrics Dashboard")).toBeInTheDocument();
    // All five error alerts shown
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

    // Successful sections: no loading, no error
    const pbSection = screen.getByRole("region", { name: "Playbook Metrics" });
    expect(within(pbSection).queryByRole("alert")).not.toBeInTheDocument();
    expect(within(pbSection).queryByLabelText("Loading Playbook Metrics")).not.toBeInTheDocument();

    const approvalSection = screen.getByRole("region", { name: "Approval Metrics" });
    expect(within(approvalSection).queryByRole("alert")).not.toBeInTheDocument();

    // Failed sections have exactly one error alert each
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
    // Analyst: queue section is not rendered — no queue loading indicator should appear
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

    // Flush the initial useEffect: fetchAll fires and all promises resolve
    await act(async () => {});

    expect(getPlaybookMetrics).toHaveBeenCalledTimes(1);

    // Advance clock to fire the interval callback
    act(() => {
      jest.advanceTimersByTime(REFRESH_INTERVAL_MS);
    });

    // Flush promises from the second fetchAll
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

    // Still only one call — interval was cleared on unmount
    expect(getPlaybookMetrics).toHaveBeenCalledTimes(1);
  });
});
