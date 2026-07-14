import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import SeverityResponseMatrixPanel from "./SeverityResponseMatrixPanel";
import * as service from "../services/severityResponseMatrixService";

jest.mock("../services/severityResponseMatrixService");

const matrix = {
  page_statement: "This page explains how the SIEM behaves. It is not another configuration interface.",
  links: {
    detection_rules_section_id: "detection-rules",
    notification_policy_section_id: "notification-policy",
  },
  severity_definitions: [
    {
      severity: "critical",
      definition: "Highest-confidence attack-chain or likely-compromise signal requiring immediate human review.",
      analyst_expectation: "Urgent review.",
      incident_behavior: "Creates or links incidents at priority P1.",
      slack_eligibility_timing: "Immediate Slack attempt before approval.",
      approval_requirement: "Approval remains required for containment.",
      containment_behavior: "Approval-gated containment.",
    },
  ],
  rules: [
    {
      rule_id: "successful_login_after_spray",
      display_name: "Successful Login After Spray",
      default_severity: "critical",
      escalation_conditions: "Requires spray activity and successful authentication.",
      maximum_severity: "critical",
      creates_incident: "Yes — alerts at this default severity create or link incidents.",
      notification_behavior: "Immediate Slack alert attempt to #critical via critical_cross_source when policy gates pass; attempted before any approval step.",
      response_playbook_behavior: "Password Spray Compromise Containment (min critical): flag_high_priority -> enrich_context -> require_approval -> block_ip -> notify_slack -> notify_email",
      why: "Successful authentication after coordinated credential attacks is a likely-compromise indicator requiring immediate human review.",
    },
  ],
};

const props = {
  cardStyle: {},
  cardHeaderStyle: {},
  cardTitleStyle: {},
  cardSubtitleStyle: {},
};

beforeEach(() => {
  service.loadSeverityResponseMatrix.mockResolvedValue(matrix);
});

test("renders the matrix statement and backend-authored why text verbatim", async () => {
  render(<SeverityResponseMatrixPanel {...props} />);

  expect(await screen.findByRole("heading", { name: "Severity & Response Matrix" })).toBeInTheDocument();
  expect(await screen.findByText(matrix.page_statement)).toBeInTheDocument();
  expect(screen.getByText(matrix.rules[0].why)).toBeInTheDocument();
  expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
});

test("renders errors accessibly", async () => {
  service.loadSeverityResponseMatrix.mockRejectedValue(new Error("Forbidden"));
  render(<SeverityResponseMatrixPanel {...props} />);
  expect(await screen.findByRole("alert")).toHaveTextContent("Forbidden");
});

test("navigates to linked workspaces", async () => {
  const onNavigate = jest.fn();
  render(<SeverityResponseMatrixPanel {...props} onNavigate={onNavigate} />);

  fireEvent.click(await screen.findByRole("button", { name: "Detection Rules" }));
  fireEvent.click(screen.getByRole("button", { name: "Notification Policy" }));

  await waitFor(() => expect(onNavigate).toHaveBeenNthCalledWith(1, "detection-rules"));
  expect(onNavigate).toHaveBeenNthCalledWith(2, "notification-policy");
});
