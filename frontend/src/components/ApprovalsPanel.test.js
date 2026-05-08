import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import ApprovalsPanel from "./ApprovalsPanel";
import {
  getApproval,
  listApprovals,
  submitApprovalDecision,
} from "../services/approvalService";

jest.mock("../services/approvalService", () => ({
  listApprovals: jest.fn(),
  getApproval: jest.fn(),
  submitApprovalDecision: jest.fn(),
}));

const approvalFixture = {
  id: 11,
  incident_id: 7,
  queue_id: 101,
  requested_by: null,
  approved_by: null,
  decided_by: null,
  status: "pending",
  action: "block_ip",
  risk_level: "high",
  request_reason: "high risk containment",
  decision_comment: null,
  created_at: "2026-05-07T12:00:00Z",
  decided_at: null,
  expires_at: "2026-05-07T13:00:00Z",
};

const approvalDetailFixture = {
  ...approvalFixture,
  events: [
    {
      id: 1,
      approval_request_id: 11,
      event_type: "created",
      actor_user_id: null,
      previous_status: null,
      new_status: "pending",
      comment: "high risk containment",
      created_at: "2026-05-07T12:00:00Z",
    },
  ],
};

const renderPanel = (props = {}) =>
  render(
    <ApprovalsPanel
      cardStyle={{}}
      cardHeaderStyle={{}}
      cardTitleStyle={{}}
      cardSubtitleStyle={{}}
      filterLabelStyle={{}}
      selectStyle={{}}
      userRole="super_admin"
      {...props}
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

describe("ApprovalsPanel", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test("shows loading state while approvals load", () => {
    const pending = deferred();
    listApprovals.mockReturnValue(pending.promise);

    renderPanel();

    expect(screen.getByText("Loading approvals...")).toBeInTheDocument();
  });

  test("shows error state when approval list fails", async () => {
    listApprovals.mockRejectedValue(new Error("load failed"));

    renderPanel();

    expect(await screen.findByText("load failed")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  test("shows empty state when no approvals are returned", async () => {
    listApprovals.mockResolvedValue({ approvals: [], count: 0 });

    renderPanel();

    expect(await screen.findByText("No approval requests found.")).toBeInTheDocument();
  });

  test("renders approval list rows", async () => {
    listApprovals.mockResolvedValue({ approvals: [approvalFixture], count: 1 });

    renderPanel();

    expect(await screen.findByText("Block Ip")).toBeInTheDocument();
    expect(screen.getAllByText("High").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Pending").length).toBeGreaterThan(0);
    expect(screen.getByText("101")).toBeInTheDocument();
  });

  test("refetches when status filter changes", async () => {
    listApprovals.mockResolvedValue({ approvals: [approvalFixture], count: 1 });

    renderPanel();
    await screen.findByText("Block Ip");

    await userEvent.selectOptions(screen.getByLabelText("Status"), "approved");

    await waitFor(() =>
      expect(listApprovals).toHaveBeenCalledWith({ status: "approved" })
    );
  });

  test("risk filter is applied client-side", async () => {
    listApprovals.mockResolvedValue({
      approvals: [
        approvalFixture,
        { ...approvalFixture, id: 12, risk_level: "critical" },
      ],
      count: 2,
    });

    renderPanel();
    expect((await screen.findAllByText("Block Ip")).length).toBe(2);

    await userEvent.selectOptions(screen.getByLabelText("Risk"), "critical");

    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.queryByText("11")).not.toBeInTheDocument();
  });

  test("row click loads approval detail", async () => {
    listApprovals.mockResolvedValue({ approvals: [approvalFixture], count: 1 });
    getApproval.mockResolvedValue({ approval: approvalDetailFixture });

    renderPanel();
    await screen.findByText("Block Ip");
    await userEvent.click(screen.getByText("Block Ip"));

    await waitFor(() => expect(getApproval).toHaveBeenCalledWith(11));
  });

  test("shows detail loading state", async () => {
    const pendingDetail = deferred();
    listApprovals.mockResolvedValue({ approvals: [approvalFixture], count: 1 });
    getApproval.mockReturnValue(pendingDetail.promise);

    renderPanel();
    await screen.findByText("Block Ip");
    await userEvent.click(screen.getByText("Block Ip"));

    expect(screen.getByText("Loading approval...")).toBeInTheDocument();
  });

  test("shows detail error state", async () => {
    listApprovals.mockResolvedValue({ approvals: [approvalFixture], count: 1 });
    getApproval.mockRejectedValue(new Error("detail failed"));

    renderPanel();
    await screen.findByText("Block Ip");
    await userEvent.click(screen.getByText("Block Ip"));

    expect(await screen.findByText("Error loading approval: detail failed")).toBeInTheDocument();
  });

  test("renders approval detail and event history", async () => {
    listApprovals.mockResolvedValue({ approvals: [approvalFixture], count: 1 });
    getApproval.mockResolvedValue({ approval: approvalDetailFixture });

    renderPanel();
    await screen.findByText("Block Ip");
    await userEvent.click(screen.getByText("Block Ip"));

    expect(await screen.findByText(/Approval #11/)).toBeInTheDocument();
    expect(screen.getByText("Event History")).toBeInTheDocument();
    expect(screen.getAllByText("Created").length).toBeGreaterThan(0);
    expect(screen.getAllByText("high risk containment").length).toBeGreaterThan(0);
  });

  test("analyst can view but cannot see decision controls", async () => {
    listApprovals.mockResolvedValue({ approvals: [approvalFixture], count: 1 });
    getApproval.mockResolvedValue({ approval: approvalDetailFixture });

    renderPanel({ userRole: "analyst" });
    await screen.findByText("Block Ip");
    await userEvent.click(screen.getByText("Block Ip"));
    await screen.findByText(/Approval #11/);

    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Deny" })).not.toBeInTheDocument();
  });

  test("super admin can see decision controls for pending approvals", async () => {
    listApprovals.mockResolvedValue({ approvals: [approvalFixture], count: 1 });
    getApproval.mockResolvedValue({ approval: approvalDetailFixture });

    renderPanel({ userRole: "super_admin" });
    await screen.findByText("Block Ip");
    await userEvent.click(screen.getByText("Block Ip"));

    expect(await screen.findByRole("button", { name: "Approve" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Deny" })).toBeInTheDocument();
    expect(screen.getByLabelText("Decision reason")).toBeInTheDocument();
  });

  test("super admin cannot see decision controls for terminal approvals", async () => {
    listApprovals.mockResolvedValue({
      approvals: [{ ...approvalFixture, status: "approved" }],
      count: 1,
    });
    getApproval.mockResolvedValue({
      approval: { ...approvalDetailFixture, status: "approved" },
    });

    renderPanel({ userRole: "super_admin" });
    await screen.findByText("Block Ip");
    await userEvent.click(screen.getByText("Block Ip"));
    await screen.findByText(/Approval #11/);

    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Deny" })).not.toBeInTheDocument();
  });

  test("approve submits decision and refreshes list and detail", async () => {
    listApprovals.mockResolvedValue({ approvals: [approvalFixture], count: 1 });
    getApproval.mockResolvedValue({ approval: approvalDetailFixture });
    submitApprovalDecision.mockResolvedValue({
      approval: { ...approvalDetailFixture, status: "approved" },
    });

    renderPanel();
    await screen.findByText("Block Ip");
    await userEvent.click(screen.getByText("Block Ip"));
    await screen.findByRole("button", { name: "Approve" });

    await userEvent.type(screen.getByLabelText("Decision reason"), "looks valid");
    await userEvent.click(screen.getByRole("button", { name: "Approve" }));

    await waitFor(() =>
      expect(submitApprovalDecision).toHaveBeenCalledWith(11, {
        decision: "approved",
        reason: "looks valid",
      })
    );
    expect(getApproval).toHaveBeenCalledTimes(2);
    expect(listApprovals).toHaveBeenCalledTimes(2);
  });

  test("deny submits decision", async () => {
    listApprovals.mockResolvedValue({ approvals: [approvalFixture], count: 1 });
    getApproval.mockResolvedValue({ approval: approvalDetailFixture });
    submitApprovalDecision.mockResolvedValue({
      approval: { ...approvalDetailFixture, status: "denied" },
    });

    renderPanel();
    await screen.findByText("Block Ip");
    await userEvent.click(screen.getByText("Block Ip"));
    await screen.findByRole("button", { name: "Deny" });

    await userEvent.click(screen.getByRole("button", { name: "Deny" }));

    await waitFor(() =>
      expect(submitApprovalDecision).toHaveBeenCalledWith(11, {
        decision: "denied",
        reason: "",
      })
    );
  });

  test("failed decision shows error without changing selected approval", async () => {
    listApprovals.mockResolvedValue({ approvals: [approvalFixture], count: 1 });
    getApproval.mockResolvedValue({ approval: approvalDetailFixture });
    submitApprovalDecision.mockRejectedValue(new Error("approval request is not pending"));

    renderPanel();
    await screen.findByText("Block Ip");
    await userEvent.click(screen.getByText("Block Ip"));
    await screen.findByRole("button", { name: "Approve" });

    await userEvent.click(screen.getByRole("button", { name: "Approve" }));

    expect(
      await screen.findByText("approval request is not pending")
    ).toBeInTheDocument();
    expect(screen.getAllByText("Pending").length).toBeGreaterThan(0);
  });
});
