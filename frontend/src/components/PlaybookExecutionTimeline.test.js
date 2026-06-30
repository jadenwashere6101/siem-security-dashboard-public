import React from "react";
import { render, screen, within } from "@testing-library/react";

import PlaybookExecutionTimeline, {
  normalizeExecutionTimeline,
  parseStepsLog,
  sanitizeTimelineText,
} from "./PlaybookExecutionTimeline";

const baseExecution = {
  id: 42,
  playbook_id: "pb_one",
  status: "success",
  mode: "simulation",
  started_at: "2026-05-18T12:00:00Z",
  completed_at: "2026-05-18T12:01:00Z",
};

test("renders a success execution with flow nodes and summary counts", () => {
  render(
    <PlaybookExecutionTimeline
      execution={{
        ...baseExecution,
        steps_log: [
          {
            step_index: 0,
            action: "enrich_alert",
            status: "success",
            mode: "simulation",
            started_at: "2026-05-18T12:00:01Z",
            completed_at: "2026-05-18T12:00:03Z",
            message: "Enrichment completed.",
          },
          {
            step_index: 1,
            action: "notify_owner",
            status: "success",
            mode: "simulation",
          },
        ],
      }}
    />
  );

  expect(screen.getByText("Execution Visualization")).toBeInTheDocument();
  expect(screen.getByText("pb_one #42")).toBeInTheDocument();
  expect(screen.getAllByText("Success").length).toBeGreaterThan(0);
  expect(screen.getAllByText("Simulation-Safe Execution").length).toBeGreaterThan(0);
  expect(screen.getByText("Execution Safety Model")).toBeInTheDocument();
  expect(screen.getAllByText("Step 1").length).toBeGreaterThan(0);
  expect(screen.getAllByText("enrich_alert").length).toBeGreaterThan(0);
  expect(screen.getByText("Enrichment completed.")).toBeInTheDocument();
  expect(screen.getAllByText("Step 2").length).toBeGreaterThan(0);
  expect(screen.getAllByText("notify_owner").length).toBeGreaterThan(0);
  expect(screen.getByText("2.0 sec")).toBeInTheDocument();
});

test("uses canonical outcome labels from response_outcomes timeline", () => {
  render(
    <PlaybookExecutionTimeline
      execution={{
        ...baseExecution,
        response_outcomes: [
          {
            playbook_step_index: 0,
            execution_mode: "simulation",
            execution_state: "succeeded",
            simulated: true,
          },
          {
            playbook_step_index: 1,
            execution_mode: "real",
            execution_state: "succeeded",
            external_executed: true,
            simulated: false,
          },
        ],
        steps_log: [
          {
            step_index: 0,
            action: "enrich_alert",
            status: "success",
            mode: "simulation",
          },
          {
            step_index: 1,
            action: "block_ip",
            status: "success",
            mode: "real",
          },
        ],
      }}
    />
  );

  expect(screen.getAllByText("Simulated").length).toBeGreaterThan(0);
  expect(screen.getAllByText("Real executed").length).toBeGreaterThan(0);
  const flowSection = screen.getByLabelText("Execution step flow");
  expect(within(flowSection).queryByText(/^Success$/)).not.toBeInTheDocument();
});

test("renders failed step with safe failure class and sanitized message", () => {
  const { container } = render(
    <PlaybookExecutionTimeline
      execution={{
        ...baseExecution,
        status: "failed",
        steps_log: [
          {
            step_index: 0,
            action: "notify_webhook",
            status: "failed",
            failure_class: "transient_network_error",
            error: {
              message:
                "Provider failed at https://hooks.example.test/secret with token=abc123",
            },
          },
        ],
      }}
    />
  );

  expect(screen.getAllByText("Failed").length).toBeGreaterThan(0);
  expect(screen.getAllByText("notify_webhook").length).toBeGreaterThan(0);
  expect(screen.getByText(/^failure class$/i)).toBeInTheDocument();
  expect(screen.getByText("transient_network_error")).toBeInTheDocument();
  expect(screen.getByText(/Provider failed at \[REDACTED_URL\]/)).toBeInTheDocument();
  expect(container).not.toHaveTextContent("hooks.example.test/secret");
  expect(container).not.toHaveTextContent("abc123");
});

test("renders awaiting approval and approval pause marker", () => {
  render(
    <PlaybookExecutionTimeline
      execution={{
        ...baseExecution,
        status: "awaiting_approval",
        steps_log: [
          {
            step_index: 0,
            action: "require_approval",
            event: "approval_requested",
            status: "awaiting_approval",
            approval_request_id: 901,
            approval_status: "pending",
            risk_level: "high",
          },
        ],
      }}
    />
  );

  expect(screen.getAllByText("Approval requested").length).toBeGreaterThan(0);
  expect(screen.getByText("Approval")).toBeInTheDocument();
  expect(screen.getByText(/^approval request$/i)).toBeInTheDocument();
  expect(screen.getByText("901")).toBeInTheDocument();
  expect(screen.getByText(/^approval status$/i)).toBeInTheDocument();
  expect(screen.getAllByText("pending").length).toBeGreaterThan(0);
  expect(screen.getByText(/^risk level$/i)).toBeInTheDocument();
});

test("handles malformed and empty steps_log safely", () => {
  const { rerender } = render(
    <PlaybookExecutionTimeline
      execution={{
        ...baseExecution,
        steps_log: "{not-json",
      }}
    />
  );

  expect(screen.getByText(/steps_log is malformed/i)).toBeInTheDocument();
  expect(screen.getByText(/No safe step events could be parsed/i)).toBeInTheDocument();

  rerender(<PlaybookExecutionTimeline execution={{ ...baseExecution, steps_log: [] }} />);
  expect(screen.getByText(/No step events are available/i)).toBeInTheDocument();
});

test("renders stringified steps_log", () => {
  render(
    <PlaybookExecutionTimeline
      execution={{
        ...baseExecution,
        steps_log: JSON.stringify([
          { step_index: 0, action: "contain", status: "success" },
        ]),
      }}
    />
  );

  expect(screen.getAllByText("contain").length).toBeGreaterThan(0);
  expect(screen.queryByText(/steps_log is malformed/i)).not.toBeInTheDocument();
});

test("renders retry, recovery, and lease markers", () => {
  render(
    <PlaybookExecutionTimeline
      execution={{
        ...baseExecution,
        status: "running",
        recovery_count: 2,
        lease_owner: "worker-1",
        steps_log: [
          {
            step_index: 0,
            action: "retry_notification",
            status: "running",
            retry_count: 2,
            recovered: true,
          },
        ],
      }}
    />
  );

  expect(screen.getByText("Lease tracked")).toBeInTheDocument();
  expect(screen.getByText("Recovery metadata")).toBeInTheDocument();
  expect(screen.getByText("Recovery count 2")).toBeInTheDocument();
  expect(screen.getByText("Retry")).toBeInTheDocument();
  expect(screen.getAllByText("Recovery").length).toBeGreaterThan(0);
  expect(screen.getByText(/^retry count$/i)).toBeInTheDocument();
});

test("renders real-mode labels", () => {
  render(
    <PlaybookExecutionTimeline
      execution={{
        ...baseExecution,
        mode: "real",
        steps_log: [{ step_index: 0, action: "email", status: "success", mode: "real" }],
      }}
    />
  );

  expect(screen.getAllByText("Guarded Real-Capable").length).toBeGreaterThan(0);
  expect(screen.getByText("Real")).toBeInTheDocument();
});

test("compact mode omits detailed timeline list but keeps flow", () => {
  render(
    <PlaybookExecutionTimeline
      compact
      execution={{
        ...baseExecution,
        steps_log: [
          {
            step_index: 0,
            action: "compact_step",
            status: "success",
            message: "Should not render in compact mode.",
          },
        ],
      }}
    />
  );

  expect(screen.getByText("compact_step")).toBeInTheDocument();
  expect(screen.queryByText("Should not render in compact mode.")).not.toBeInTheDocument();
});

test("helper functions normalize and sanitize safely", () => {
  expect(parseStepsLog('[{"status":"success"}]').steps).toHaveLength(1);
  expect(parseStepsLog("{bad").malformed).toBe(true);
  expect(sanitizeTimelineText("see https://example.test/a token=secret")).toContain(
    "[REDACTED_URL]"
  );

  const normalized = normalizeExecutionTimeline({
    steps_log: [
      { action: "one", status: "success" },
      { action: "two", status: "skipped" },
    ],
  });
  expect(normalized.summary.total).toBe(2);
  expect(normalized.summary.success).toBe(1);
  expect(normalized.summary.skipped).toBe(1);
});
