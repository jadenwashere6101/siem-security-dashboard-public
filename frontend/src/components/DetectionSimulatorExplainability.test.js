import React from "react";
import { render, screen } from "@testing-library/react";

import DetectionSimulatorExplainability from "./DetectionSimulatorExplainability";

test("renders nothing meaningful when stages are absent", () => {
  const { container } = render(<DetectionSimulatorExplainability stages={null} />);
  expect(container).toBeEmptyDOMElement();
});

test("explains a parser failure with the parser's own error", () => {
  const stages = {
    parser: {
      status: "failed",
      results: [{ index: 0, status: "failed", error: "Malformed nginx access log line" }],
    },
  };
  render(<DetectionSimulatorExplainability stages={stages} />);
  expect(screen.getByText(/Parser failure/i)).toBeInTheDocument();
  expect(screen.getByText(/Malformed nginx access log line/)).toBeInTheDocument();
});

test("explains rule not applicable using the backend's reason", () => {
  const stages = {
    detection_applicability: {
      status: "failed",
      reason: "Rule 'port_scan_threshold' is not applicable to source 'honeypot'",
    },
  };
  render(<DetectionSimulatorExplainability stages={stages} />);
  expect(screen.getByText(/Rule not applicable/i)).toBeInTheDocument();
  expect(screen.getByText("Rule 'port_scan_threshold' is not applicable to source 'honeypot'")).toBeInTheDocument();
});

test("explains a matched detection with threshold parameters and disclosures", () => {
  const stages = {
    threshold_window_evaluation: {
      status: "succeeded",
      rule_parameters: { threshold: 3, window_minutes: 15 },
      matched: true,
      existing_open_alert_for_rule: false,
      blended_with_real_history: true,
    },
  };
  render(<DetectionSimulatorExplainability stages={stages} />);
  expect(screen.getByText(/Detection matched/)).toBeInTheDocument();
  expect(screen.getByText(/threshold=3, window_minutes=15/)).toBeInTheDocument();
  expect(screen.getByText(/real, already-committed production events/)).toBeInTheDocument();
});

test("explains a not-matched detection and existing-alert suppression note", () => {
  const stages = {
    threshold_window_evaluation: {
      status: "succeeded",
      rule_parameters: { threshold: 3, window_minutes: 15 },
      matched: false,
      existing_open_alert_for_rule: true,
      blended_with_real_history: false,
      note: "An open alert already exists for this source and rule; production dedup logic suppresses a new alert even if this rule's threshold was met by this simulation.",
    },
  };
  render(<DetectionSimulatorExplainability stages={stages} />);
  expect(screen.getByText(/Detection not matched/)).toBeInTheDocument();
  expect(screen.getByText(/suppresses a new alert/)).toBeInTheDocument();
});

test("explains a below-threshold near-miss with the backend's real observed value", () => {
  const stages = {
    threshold_window_evaluation: {
      status: "succeeded",
      rule_parameters: { threshold: 3, window_minutes: 15 },
      matched: false,
      existing_open_alert_for_rule: false,
      blended_with_real_history: false,
      evaluated_window_minutes: 15,
      evidence_available: true,
      observed_value: 2,
      observed_value_label: "attempts",
      configured_threshold: 3,
    },
  };
  render(<DetectionSimulatorExplainability stages={stages} />);
  expect(screen.getByText(/Detection not matched/)).toBeInTheDocument();
  expect(screen.getByText(/Observed attempts: 2 \(required: 3\)/)).toBeInTheDocument();
  expect(screen.getByText(/Evaluated window: 15 minute\(s\)/)).toBeInTheDocument();
});

test("discloses when an observed value is unavailable, rather than fabricating one", () => {
  const stages = {
    threshold_window_evaluation: {
      status: "succeeded",
      rule_parameters: { threshold: 3, window_minutes: 15 },
      matched: false,
      existing_open_alert_for_rule: false,
      blended_with_real_history: false,
      evidence_available: false,
      observed_value: null,
      observed_value_label: null,
    },
  };
  render(<DetectionSimulatorExplainability stages={stages} />);
  expect(screen.getByText(/An exact observed value was not available/)).toBeInTheDocument();
});

test("does not claim an observed value is unavailable when suppression already explains the non-match", () => {
  const stages = {
    threshold_window_evaluation: {
      status: "succeeded",
      rule_parameters: { threshold: 3, window_minutes: 15 },
      matched: false,
      existing_open_alert_for_rule: true,
      blended_with_real_history: false,
      evidence_available: false,
      observed_value: null,
      note: "An open alert already exists for this source and rule; production dedup logic suppresses a new alert.",
    },
  };
  render(<DetectionSimulatorExplainability stages={stages} />);
  expect(screen.queryByText(/An exact observed value was not available/)).not.toBeInTheDocument();
  expect(screen.getByText(/suppresses a new alert/)).toBeInTheDocument();
});

test("explains an alert preview with severity, message, and simulated reputation", () => {
  const stages = {
    alert_preview: {
      status: "succeeded",
      alert: {
        alert_type: "failed_login_threshold",
        severity: "high",
        message: "5 failed login attempts detected from 198.51.100.1",
        reputation_source: "simulated",
      },
    },
  };
  render(<DetectionSimulatorExplainability stages={stages} />);
  expect(screen.getByText(/Alert preview/)).toBeInTheDocument();
  expect(screen.getByText(/high-severity "failed_login_threshold" alert/)).toBeInTheDocument();
  expect(screen.getByText(/stubbed for simulation/)).toBeInTheDocument();
});

test("explains no alert would be created", () => {
  const stages = { alert_preview: { status: "succeeded", alert: null } };
  render(<DetectionSimulatorExplainability stages={stages} />);
  expect(screen.getByText(/No alert would be created/)).toBeInTheDocument();
});

test("explains a MITRE mapping", () => {
  const stages = {
    mitre_mapping: {
      status: "succeeded",
      mitre_technique_id: "T1110",
      mitre_technique_name: "Brute Force",
      mitre_tactic: "Credential Access",
    },
  };
  render(<DetectionSimulatorExplainability stages={stages} />);
  expect(screen.getByText(/T1110 — Brute Force \(Credential Access\)/)).toBeInTheDocument();
});

test("explains an unmapped MITRE alert type", () => {
  const stages = { mitre_mapping: { status: "succeeded", mitre_technique_id: null } };
  render(<DetectionSimulatorExplainability stages={stages} />);
  expect(screen.getByText(/does not have a specific MITRE ATT&CK technique mapping/)).toBeInTheDocument();
});

test("explains a matched playbook with approval requirements and selected response", () => {
  const stages = {
    soar_preview: {
      status: "succeeded",
      matched_playbooks: [
        { playbook_id: "pb-1", name: "Critical Response", approval_required: true, approval_risk_levels: ["critical"] },
      ],
      no_playbook_match: false,
      selected_response_action: "monitor",
      response_action_basis: "computed from a stubbed simulated reputation score; not the source IP's real reputation",
    },
  };
  render(<DetectionSimulatorExplainability stages={stages} />);
  expect(screen.getByText(/Matched playbook\(s\): "Critical Response" \(requires approval: critical\)/)).toBeInTheDocument();
  expect(screen.getByText(/Selected response action: monitor/)).toBeInTheDocument();
  expect(screen.getByText(/No playbook execution, queue entry, or external integration was created or invoked\./)).toBeInTheDocument();
});

test("explains no playbook match", () => {
  const stages = { soar_preview: { status: "succeeded", matched_playbooks: [], no_playbook_match: true } };
  render(<DetectionSimulatorExplainability stages={stages} />);
  expect(screen.getByText(/No enabled playbook's trigger configuration matched this alert\./)).toBeInTheDocument();
});
