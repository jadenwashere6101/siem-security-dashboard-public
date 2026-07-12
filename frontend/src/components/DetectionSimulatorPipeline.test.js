import React from "react";
import { render, screen } from "@testing-library/react";

import DetectionSimulatorPipeline from "./DetectionSimulatorPipeline";

const EXPECTED_ORDER = [
  "raw_input",
  "parser",
  "normalized_event",
  "detection_applicability",
  "detection_evaluation",
  "threshold_window_evaluation",
  "alert_preview",
  "mitre_mapping",
  "soar_preview",
];

const succeededStages = Object.fromEntries(EXPECTED_ORDER.map((id) => [id, { status: "succeeded" }]));

test("renders nothing when stages are absent", () => {
  const { container } = render(<DetectionSimulatorPipeline stages={null} />);
  expect(container).toBeEmptyDOMElement();
});

test("renders all nine stages in the exact production pipeline order", () => {
  render(<DetectionSimulatorPipeline stages={succeededStages} />);
  const items = screen.getAllByRole("listitem");
  expect(items.map((item) => item.getAttribute("data-stage"))).toEqual(EXPECTED_ORDER);
});

test("renders a succeeded status with an accessible label, not color alone", () => {
  render(<DetectionSimulatorPipeline stages={succeededStages} />);
  const parserItem = screen.getByText("Parser").closest("li");
  expect(parserItem).toHaveAttribute("data-status", "succeeded");
  expect(parserItem.querySelector('[aria-label="Succeeded status"]')).toHaveTextContent("Succeeded");
});

test("marks downstream stages as skipped when an early stage fails", () => {
  const stages = {
    raw_input: { status: "succeeded" },
    parser: { status: "failed", reason: "parser_failed" },
    normalized_event: { status: "skipped", reason: "parser_failed" },
    detection_applicability: { status: "skipped", reason: "parser_failed" },
    detection_evaluation: { status: "skipped", reason: "parser_failed" },
    threshold_window_evaluation: { status: "skipped", reason: "parser_failed" },
    alert_preview: { status: "skipped", reason: "parser_failed" },
    mitre_mapping: { status: "skipped", reason: "parser_failed" },
    soar_preview: { status: "skipped", reason: "parser_failed" },
  };
  render(<DetectionSimulatorPipeline stages={stages} />);

  const parserItem = screen.getByText("Parser").closest("li");
  expect(parserItem).toHaveAttribute("data-status", "failed");
  expect(parserItem.querySelector('[aria-label="Failed status"]')).toBeInTheDocument();

  const mitreItem = screen.getByText("MITRE Mapping").closest("li");
  expect(mitreItem).toHaveAttribute("data-status", "skipped");
  expect(mitreItem.querySelector('[aria-label="Skipped status"]')).toBeInTheDocument();
});

test("shows a failed applicability reason without recomputing it", () => {
  const stages = {
    ...succeededStages,
    detection_applicability: { status: "failed", reason: "Rule 'x' is not applicable to source 'y'" },
  };
  render(<DetectionSimulatorPipeline stages={stages} />);
  expect(screen.getByText("Rule 'x' is not applicable to source 'y'")).toBeInTheDocument();
});
