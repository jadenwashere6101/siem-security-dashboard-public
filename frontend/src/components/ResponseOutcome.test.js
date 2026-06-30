import { render, screen, within } from "@testing-library/react";

import { ResponseOutcomeBadge, ResponseOutcomeSummary } from "./ResponseOutcome";
import {
  EXECUTION_MODES,
  EXECUTION_STATES,
  REASON_CODES,
  formatOutcomeStatus,
  outcomeColor,
  outcomeLabel,
  reasonCodeExplanation,
} from "../utils/responseOutcomeDisplay";

const baseOutcome = {
  decision_id: 10,
  alert_id: 101,
  queue_id: 202,
  playbook_execution_id: 303,
  approval_request_id: 404,
  notification_delivery_attempt_id: 505,
  selected_action: "block_ip",
  decision_source: "manual",
  execution_actor: "manual",
  execution_mode: "simulation",
  execution_state: "succeeded",
  external_executed: false,
  tracking_recorded: false,
  simulated: true,
  reason_code: "simulation_mode",
  outcome_summary: "Simulation completed without enforcement.",
};

describe("response outcome display utilities", () => {
  test("outcomeLabel returns Observed only for null input", () => {
    expect(outcomeLabel(null)).toBe("Observed only");
  });

  test.each([
    ["observed", "Observed only"],
    ["simulation", "Simulated"],
    ["tracking_only", "Tracking only"],
    ["real", "Real executed"],
  ])("outcomeLabel covers execution mode %s", (executionMode, expected) => {
    expect(
      outcomeLabel({
        ...baseOutcome,
        execution_mode: executionMode,
        execution_state: "succeeded",
        external_executed: executionMode === "real",
        tracking_recorded: executionMode === "tracking_only",
        simulated: executionMode === "simulation",
      })
    ).toBe(expected);
  });

  test.each([
    ["observed", "Observed only"],
    ["selected", "Selected"],
    ["queued", "Queued"],
    ["awaiting_approval", "Awaiting approval"],
    ["running", "Running"],
    ["skipped", "Skipped"],
    ["blocked", "Blocked by approval"],
    ["succeeded", "Simulated"],
    ["failed", "Failed"],
  ])("outcomeLabel covers execution state %s", (executionState, expected) => {
    expect(
      outcomeLabel({
        ...baseOutcome,
        execution_mode: "simulation",
        execution_state: executionState,
        simulated: true,
      })
    ).toBe(expected);
  });

  test("outcomeLabel gives canonical boolean flags priority for mode labels", () => {
    expect(
      outcomeLabel({
        ...baseOutcome,
        execution_mode: "real",
        external_executed: true,
        simulated: false,
      })
    ).toBe("Real executed");
    expect(
      outcomeLabel({
        ...baseOutcome,
        execution_mode: "observed",
        execution_state: "succeeded",
        tracking_recorded: true,
        simulated: false,
      })
    ).toBe("Tracking only");
    expect(
      outcomeLabel({
        ...baseOutcome,
        execution_mode: "observed",
        execution_state: "succeeded",
        simulated: true,
      })
    ).toBe("Simulated");
  });

  test.each(REASON_CODES)("reason code %s has a display explanation", (reasonCode) => {
    expect(reasonCodeExplanation(reasonCode)).toEqual(expect.any(String));
    expect(reasonCodeExplanation(reasonCode).length).toBeGreaterThan(0);
    expect(outcomeLabel({ ...baseOutcome, reason_code: reasonCode })).toBe("Simulated");
  });

  test.each([
    [null, "neutral"],
    [{ ...baseOutcome, execution_mode: "observed", execution_state: "observed", simulated: false }, "neutral"],
    [{ ...baseOutcome, execution_mode: "simulation", simulated: true }, "info"],
    [
      {
        ...baseOutcome,
        execution_mode: "tracking_only",
        tracking_recorded: true,
        simulated: false,
      },
      "warning",
    ],
    [
      {
        ...baseOutcome,
        execution_mode: "real",
        external_executed: true,
        simulated: false,
      },
      "success",
    ],
    [{ ...baseOutcome, execution_state: "awaiting_approval" }, "warning"],
    [{ ...baseOutcome, execution_state: "blocked" }, "danger"],
    [{ ...baseOutcome, execution_state: "skipped" }, "neutral"],
    [{ ...baseOutcome, execution_state: "failed" }, "danger"],
  ])("outcomeColor maps canonical condition to %s", (outcome, expected) => {
    expect(outcomeColor(outcome)).toBe(expected);
  });

  test("formatOutcomeStatus uses qualified composite labels", () => {
    expect(formatOutcomeStatus(baseOutcome)).toBe("Simulated succeeded");
    expect(
      formatOutcomeStatus({
        ...baseOutcome,
        execution_mode: "tracking_only",
        tracking_recorded: true,
        simulated: false,
      })
    ).toBe("Tracking-only recorded");
    expect(
      formatOutcomeStatus({
        ...baseOutcome,
        execution_mode: "real",
        external_executed: true,
        simulated: false,
      })
    ).toBe("Real executed");
  });
});

describe("ResponseOutcomeBadge", () => {
  test("renders the canonical label and tone", () => {
    render(<ResponseOutcomeBadge outcome={baseOutcome} />);

    const badge = screen.getByText("Simulated");
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveAttribute("data-outcome-tone", "info");
  });

  test("renders an aria-label with mode and state for non-null outcomes", () => {
    render(<ResponseOutcomeBadge outcome={baseOutcome} />);

    expect(screen.getByLabelText(/Response outcome: Simulated/i)).toHaveAttribute(
      "aria-label",
      expect.stringContaining("mode simulation")
    );
    expect(screen.getByLabelText(/Response outcome: Simulated/i)).toHaveAttribute(
      "aria-label",
      expect.stringContaining("state succeeded")
    );
  });

  test("handles null outcome without crashing", () => {
    render(<ResponseOutcomeBadge outcome={null} />);

    expect(screen.getByText("Observed only")).toBeInTheDocument();
    expect(screen.getByLabelText(/no canonical outcome recorded/i)).toBeInTheDocument();
  });

  test.each(EXECUTION_MODES.flatMap((mode) => EXECUTION_STATES.map((state) => [mode, state])))(
    "has a non-empty aria-label for mode %s and state %s",
    (executionMode, executionState) => {
      render(
        <ResponseOutcomeBadge
          outcome={{
            ...baseOutcome,
            execution_mode: executionMode,
            execution_state: executionState,
            external_executed: executionMode === "real" && executionState === "succeeded",
            tracking_recorded: executionMode === "tracking_only" && executionState === "succeeded",
            simulated: executionMode === "simulation",
          }}
        />
      );

      expect(screen.getByLabelText(/Response outcome:/i).getAttribute("aria-label")).not.toBe("");
    }
  );
});

describe("ResponseOutcomeSummary", () => {
  test("renders all canonical fields for a non-null outcome", () => {
    render(<ResponseOutcomeSummary outcome={baseOutcome} />);

    expect(screen.getByText("Block Ip")).toBeInTheDocument();
    expect(screen.getAllByText("Manual")).toHaveLength(2);
    expect(screen.getByText("Simulation completed without enforcement.")).toBeInTheDocument();
    expect(screen.getByText("Simulation mode completed without real provider or local enforcement.")).toBeInTheDocument();

    const evidence = screen.getByLabelText("Execution evidence");
    expect(within(evidence).getByText("No real execution confirmed")).toBeInTheDocument();
    expect(within(evidence).getByText("No tracking-only record created")).toBeInTheDocument();
    expect(within(evidence).getByText("Simulation completed without enforcement")).toBeInTheDocument();
  });

  test("renders a non-empty no-history state for null outcome", () => {
    render(<ResponseOutcomeSummary outcome={null} />);

    expect(screen.getByLabelText("Response outcome summary")).toHaveTextContent(
      "No response outcome recorded."
    );
  });

  test("renders related ids when requested", () => {
    render(<ResponseOutcomeSummary outcome={baseOutcome} showRelated />);

    const related = screen.getByLabelText("Related response outcome identifiers");
    expect(within(related).getByText("101")).toBeInTheDocument();
    expect(within(related).getByText("202")).toBeInTheDocument();
    expect(within(related).getByText("303")).toBeInTheDocument();
    expect(within(related).getByText("404")).toBeInTheDocument();
    expect(within(related).getByText("505")).toBeInTheDocument();
  });

  test("does not infer outcome from legacy fields when canonical outcome is null", () => {
    render(<ResponseOutcomeSummary outcome={null} />);

    expect(screen.getByText("No response outcome recorded.")).toBeInTheDocument();
    expect(screen.queryByText("Block Ip")).not.toBeInTheDocument();
  });

  test("does not render unqualified executed wording", () => {
    const { container } = render(<ResponseOutcomeSummary outcome={baseOutcome} showRelated />);
    const text = container.textContent || "";

    expect(text).not.toMatch(/(^|[^A-Za-z])executed($|[^A-Za-z])/);
  });
});

describe("canonical outcome count utilities", () => {
  const {
    buildCanonicalStepOutcomeLabels,
    canonicalOutcomeCountSections,
    hasCanonicalOutcomeCounts,
    isTrackingOnlyOutcome,
    mergeCanonicalOutcomeCounts,
    outcomeCountEntryLabel,
  } = require("../utils/responseOutcomeDisplay");

  test("mergeCanonicalOutcomeCounts sums grouped counts", () => {
    const merged = mergeCanonicalOutcomeCounts(
      { execution_mode: { simulation: 2 } },
      { execution_mode: { simulation: 3, real: 1 } }
    );

    expect(merged.execution_mode.simulation).toBe(5);
    expect(merged.execution_mode.real).toBe(1);
  });

  test("hasCanonicalOutcomeCounts detects non-zero groups", () => {
    expect(hasCanonicalOutcomeCounts(null)).toBe(false);
    expect(hasCanonicalOutcomeCounts({ execution_mode: { simulation: 0 } })).toBe(false);
    expect(hasCanonicalOutcomeCounts({ execution_mode: { simulation: 1 } })).toBe(true);
  });

  test("canonicalOutcomeCountSections uses outcomeLabel-derived entry labels", () => {
    const sections = canonicalOutcomeCountSections({
      execution_mode: { simulation: 4, real: 1 },
      external_executed: { true: 1, false: 4 },
    });

    expect(sections[0].entries.map((entry) => entry.label)).toEqual(
      expect.arrayContaining(["Simulated", "Real executed"])
    );
    expect(outcomeCountEntryLabel("external_executed", "true")).toBe("Real executed");
  });

  test("buildCanonicalStepOutcomeLabels maps first outcome per step index", () => {
    const labels = buildCanonicalStepOutcomeLabels([
      {
        playbook_step_index: 0,
        execution_mode: "simulation",
        execution_state: "succeeded",
        simulated: true,
      },
      {
        playbook_step_index: 0,
        execution_mode: "real",
        execution_state: "succeeded",
        external_executed: true,
      },
      {
        playbook_step_index: 2,
        execution_mode: "tracking_only",
        execution_state: "succeeded",
        tracking_recorded: true,
      },
    ]);

    expect(labels[0]).toBe("Simulated");
    expect(labels[2]).toBe("Tracking only");
    expect(labels[1]).toBeUndefined();
  });

  test("isTrackingOnlyOutcome recognizes tracking-only canonical outcomes", () => {
    expect(
      isTrackingOnlyOutcome({
        execution_mode: "tracking_only",
        tracking_recorded: true,
      })
    ).toBe(true);
    expect(isTrackingOnlyOutcome({ execution_mode: "simulation", simulated: true })).toBe(false);
  });
});
