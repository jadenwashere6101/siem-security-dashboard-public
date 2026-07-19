import React from "react";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import ResponseRegistryPanel from "./ResponseRegistryPanel";
import { ResponseSyncProvider } from "../context/ResponseSyncContext";
import {
  executeRegistryCommand,
  loadRegistryDetail,
  loadRegistryRecords,
} from "../services/responseRegistryService";

jest.mock("../services/responseRegistryService", () => ({
  REGISTRY_VIEWS: jest.requireActual("../services/responseRegistryService").REGISTRY_VIEWS,
  loadRegistryRecords: jest.fn(),
  loadRegistryDetail: jest.fn(),
  executeRegistryCommand: jest.fn(),
}));

jest.mock("./BlocklistManagerPanel", () => {
  return function MockBlocklistManagerPanel() {
    return <div>Blocklist embed</div>;
  };
});

const styleProps = {
  cardStyle: {},
  cardHeaderStyle: {},
  cardTitleStyle: {},
  cardSubtitleStyle: {},
  filterLabelStyle: {},
  selectStyle: {},
};

function makeDetail(overrides = {}) {
  return {
    record: {
      id: 11,
      indicator_value: "8.8.8.8",
      current_disposition: "monitored",
      created_at: "2026-07-01T12:00:00+00:00",
      updated_at: "2026-07-10T12:00:00+00:00",
    },
    events: [
      {
        id: 1,
        event_type: "monitor_started",
        requested_action: "monitor",
        outcome: "succeeded",
        disposition_after: "monitored",
        enforcement: "none",
        origin_surface: "response_registry",
        created_at: "2026-07-10T12:00:00+00:00",
        reason: "Watch",
        alert_id: 42,
        incident_id: 77,
        playbook_execution_id: 19,
        approval_request_id: 31,
        safe_metadata: {},
      },
    ],
    latest_event: {
      id: 1,
      event_type: "monitor_started",
      requested_action: "monitor",
      outcome: "succeeded",
      disposition_after: "monitored",
      enforcement: "none",
      origin_surface: "response_registry",
      created_at: "2026-07-10T12:00:00+00:00",
      reason: "Watch",
      alert_id: 42,
      incident_id: 77,
      playbook_execution_id: 19,
      approval_request_id: 31,
      safe_metadata: {},
    },
    blocklist_entry: null,
    related_alert_ids: [42],
    related_incident_ids: [77],
    related_alert_count: 1,
    related_incident_count: 1,
    related_playbook_execution_ids: [19],
    related_playbook_execution_count: 1,
    related_approval_request_ids: [31],
    related_approval_request_count: 1,
    relationships: {
      alerts: { count: 1, ids: [42], primary_id: 42 },
      incidents: { count: 1, ids: [77], primary_id: 77 },
      playbooks: { count: 1, ids: [19], primary_id: 19 },
      approvals: { count: 1, ids: [31], primary_id: 31 },
    },
    primary_alert: {
      id: 42,
      alert_type: "pfsense_firewall_port_scan",
      severity: "HIGH",
      source_ip: "8.8.8.8",
      message: "Port scan",
    },
    primary_incident: {
      id: 77,
      title: "Registry Incident",
      status: "open",
      priority: "P2",
      severity: "HIGH",
      source_ip: "8.8.8.8",
    },
    primary_playbook_execution: {
      id: 19,
      playbook_id: "core-port-scan",
      status: "awaiting_approval",
      alert_id: 42,
      incident_id: 77,
      source_ip: "8.8.8.8",
    },
    primary_approval_request: {
      id: 31,
      status: "pending",
      risk_level: "high",
      alert_id: 42,
      incident_id: 77,
      queue_id: null,
    },
    enforcement: "none",
    enforcement_statement: "No firewall or host enforcement.",
    first_seen: "2026-07-01T12:00:00+00:00",
    last_updated: "2026-07-10T12:00:00+00:00",
    response_source: "response_registry",
    ...overrides,
  };
}

function makeListItem(overrides = {}) {
  return {
    id: 11,
    indicator_value: "8.8.8.8",
    current_disposition: "monitored",
    latest_requested_action: "monitor",
    latest_outcome: "succeeded",
    enforcement: "none",
    latest_origin_surface: "response_registry",
    updated_at: "2026-07-10T12:00:00+00:00",
    ...overrides,
  };
}

function renderRegistry(ui) {
  return render(<ResponseSyncProvider>{ui}</ResponseSyncProvider>);
}

async function openFirstRow() {
  const row = await screen.findByRole("row", {
    name: /Registry record 8\.8\.8\.8/i,
  });
  await userEvent.click(row);
  const detail = await screen.findByLabelText("Registry detail");
  await waitFor(() => {
    expect(within(detail).queryByText(/Loading detail/i)).not.toBeInTheDocument();
  });
  return detail;
}

beforeEach(() => {
  jest.clearAllMocks();
  loadRegistryRecords.mockResolvedValue({
    items: [makeListItem()],
    total: 1,
  });
  loadRegistryDetail.mockResolvedValue(makeDetail());
});

test("shows loading then registry rows", async () => {
  renderRegistry(<ResponseRegistryPanel {...styleProps} canTakeAlertActions />);

  expect(screen.getByText(/Loading response registry/i)).toBeInTheDocument();
  expect(
    await screen.findByRole("row", { name: /Registry record 8\.8\.8\.8/i })
  ).toBeInTheDocument();
  expect(screen.getAllByText("Monitoring").length).toBeGreaterThan(0);
});

test("renders response registry AI entry point for selected detail", async () => {
  const onAskAi = jest.fn();
  renderRegistry(
    <ResponseRegistryPanel
      {...styleProps}
      canTakeAlertActions
      onAskAi={onAskAi}
      aiEnabled
    />
  );
  const detail = await openFirstRow();

  await userEvent.click(within(detail).getByRole("button", { name: "Explain this response" }));
  await userEvent.click(within(detail).getByRole("button", { name: "Draft response" }));

  expect(onAskAi).toHaveBeenCalledWith(
    expect.objectContaining({
      contextType: "response_registry",
      action: "explain_response",
      context: { registry_id: 11 },
    })
  );
  expect(onAskAi).toHaveBeenCalledWith(
    expect.objectContaining({
      contextType: "response_registry",
      draftType: "response_recommendation",
      context: { registry_id: 11 },
    })
  );
});

test("shows empty state when no records", async () => {
  loadRegistryRecords.mockResolvedValue({ items: [], total: 0 });
  renderRegistry(<ResponseRegistryPanel {...styleProps} canTakeAlertActions />);

  expect(
    await screen.findByText(/No registry records match the current filters/i)
  ).toBeInTheDocument();
});

test("list retry preserves the last requested page offset", async () => {
  loadRegistryRecords
    .mockResolvedValueOnce({
      items: [makeListItem()],
      total: 120,
    })
    .mockRejectedValueOnce(new Error("page 2 failed"))
    .mockResolvedValueOnce({
      items: [makeListItem({ id: 99, indicator_value: "9.9.9.9" })],
      total: 120,
    });

  renderRegistry(<ResponseRegistryPanel {...styleProps} canTakeAlertActions />);
  await screen.findByRole("row", { name: /Registry record 8\.8\.8\.8/i });

  await userEvent.click(screen.getByRole("button", { name: "Next" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("page 2 failed");

  await userEvent.click(screen.getByRole("button", { name: /Retry/i }));
  await waitFor(() => {
    expect(loadRegistryRecords).toHaveBeenLastCalledWith(
      expect.objectContaining({ offset: 50 })
    );
  });
});

test("contextual navigation clears stale filters and applies exact related targeting", async () => {
  const { rerender } = renderRegistry(<ResponseRegistryPanel {...styleProps} canTakeAlertActions />);
  await screen.findByRole("row", { name: /Registry record 8\.8\.8\.8/i });

  await userEvent.type(screen.getByLabelText("Origin filter"), "response_registry");
  await userEvent.type(screen.getByLabelText("Outcome filter"), "succeeded");

  rerender(
    <ResponseSyncProvider>
      <ResponseRegistryPanel
        {...styleProps}
        canTakeAlertActions
        navigationRequest={{
          nonce: 1,
          view: "all",
          exactIndicator: "9.9.9.9",
          relatedAlertId: 42,
          relatedIncidentId: 77,
        }}
      />
    </ResponseSyncProvider>
  );

  await waitFor(() => {
    expect(loadRegistryRecords).toHaveBeenLastCalledWith(
      expect.objectContaining({
        exactIndicator: "9.9.9.9",
        relatedAlertId: 42,
        relatedIncidentId: 77,
        origin: undefined,
        outcome: undefined,
        offset: 0,
      })
    );
  });
  expect(screen.getByLabelText("Search indicator")).toHaveValue("9.9.9.9");
});

test("opens detail with response summary, relationships, and recommended next step", async () => {
  renderRegistry(<ResponseRegistryPanel {...styleProps} canTakeAlertActions />);
  const detail = await openFirstRow();

  expect(within(detail).getByText("Response Summary")).toBeInTheDocument();
  expect(within(detail).getByText("#42 · pfsense_firewall_port_scan")).toBeInTheDocument();
  expect(within(detail).getAllByText("Monitoring").length).toBeGreaterThan(0);
  expect(within(detail).getByText("Recommended Next Step")).toBeInTheDocument();
  expect(within(detail).getByText("Awaiting analyst approval.")).toBeInTheDocument();
  expect(within(detail).getByRole("button", { name: "Alerts (1)" })).toBeInTheDocument();
  expect(within(detail).getByRole("button", { name: "Incident (1)" })).toBeInTheDocument();
  expect(within(detail).getByRole("button", { name: "Playbook (1)" })).toBeInTheDocument();
  expect(within(detail).getByRole("button", { name: "Approvals (1)" })).toBeInTheDocument();
});

test("Investigate prefers incident, then alert, then source ip, else shows explanation", async () => {
  const onOpenIncident = jest.fn();
  const onOpenAlert = jest.fn();
  const onOpenSourceContext = jest.fn();

  renderRegistry(
    <ResponseRegistryPanel
      {...styleProps}
      canTakeAlertActions
      onOpenIncident={onOpenIncident}
      onOpenAlert={onOpenAlert}
      onOpenSourceContext={onOpenSourceContext}
    />
  );
  let detail = await openFirstRow();

  await userEvent.click(within(detail).getByRole("button", { name: "Investigate" }));
  expect(onOpenIncident).toHaveBeenCalledWith(77);

  loadRegistryDetail.mockResolvedValueOnce(
    makeDetail({
      primary_incident: null,
      related_incident_ids: [],
      related_incident_count: 0,
      relationships: {
        alerts: { count: 1, ids: [42], primary_id: 42 },
        incidents: { count: 0, ids: [], primary_id: null },
        playbooks: { count: 1, ids: [19], primary_id: 19 },
        approvals: { count: 1, ids: [31], primary_id: 31 },
      },
      primary_approval_request: null,
    })
  );
  await userEvent.click(within(detail).getByRole("button", { name: "Close" }));
  detail = await openFirstRow();
  await userEvent.click(within(detail).getByRole("button", { name: "Investigate" }));
  expect(onOpenAlert).toHaveBeenCalledWith(42, "8.8.8.8");

  loadRegistryDetail.mockResolvedValueOnce(
    makeDetail({
      primary_incident: null,
      primary_alert: null,
      related_alert_ids: [],
      related_incident_ids: [],
      related_alert_count: 0,
      related_incident_count: 0,
      relationships: {
        alerts: { count: 0, ids: [], primary_id: null },
        incidents: { count: 0, ids: [], primary_id: null },
        playbooks: { count: 0, ids: [], primary_id: null },
        approvals: { count: 0, ids: [], primary_id: null },
      },
      primary_approval_request: null,
    })
  );
  await userEvent.click(within(detail).getByRole("button", { name: "Close" }));
  detail = await openFirstRow();
  await userEvent.click(within(detail).getByRole("button", { name: "Investigate" }));
  expect(onOpenSourceContext).toHaveBeenCalledWith("8.8.8.8");

  loadRegistryDetail.mockResolvedValueOnce(
    makeDetail({
      record: { id: 11, indicator_value: "", current_disposition: "observed" },
      primary_incident: null,
      primary_alert: null,
      related_alert_ids: [],
      related_incident_ids: [],
      related_alert_count: 0,
      related_incident_count: 0,
      relationships: {
        alerts: { count: 0, ids: [], primary_id: null },
        incidents: { count: 0, ids: [], primary_id: null },
        playbooks: { count: 0, ids: [], primary_id: null },
        approvals: { count: 0, ids: [], primary_id: null },
      },
      primary_approval_request: null,
      latest_event: {},
      events: [],
    })
  );
  await userEvent.click(within(detail).getByRole("button", { name: "Close" }));
  detail = await openFirstRow();
  await userEvent.click(within(detail).getByRole("button", { name: "Investigate" }));
  expect(
    await screen.findByRole("status")
  ).toHaveTextContent(/No related incident, alert, or source\/IP context is available/i);
});

test("relationship buttons open linked workspaces", async () => {
  const onOpenAlert = jest.fn();
  const onOpenIncident = jest.fn();
  const onOpenPlaybookExecution = jest.fn();
  const onOpenApproval = jest.fn();
  renderRegistry(
    <ResponseRegistryPanel
      {...styleProps}
      canTakeAlertActions
      onOpenAlert={onOpenAlert}
      onOpenIncident={onOpenIncident}
      onOpenPlaybookExecution={onOpenPlaybookExecution}
      onOpenApproval={onOpenApproval}
    />
  );
  const detail = await openFirstRow();

  await userEvent.click(within(detail).getByRole("button", { name: "Alerts (1)" }));
  await userEvent.click(within(detail).getByRole("button", { name: "Incident (1)" }));
  await userEvent.click(within(detail).getByRole("button", { name: "Playbook (1)" }));
  await userEvent.click(within(detail).getByRole("button", { name: "Approvals (1)" }));

  expect(onOpenAlert).toHaveBeenCalledWith(42, "8.8.8.8");
  expect(onOpenIncident).toHaveBeenCalledWith(77);
  expect(onOpenPlaybookExecution).toHaveBeenCalledWith(19);
  expect(onOpenApproval).toHaveBeenCalledWith(31);
});

test("viewer cannot mutate and sees locked explanation", async () => {
  renderRegistry(<ResponseRegistryPanel {...styleProps} canTakeAlertActions={false} />);
  const detail = await openFirstRow();

  expect(
    within(detail).getByText(/Mutation controls are locked for this role/i)
  ).toBeInTheDocument();
  expect(within(detail).getByRole("button", { name: "Monitor" })).toBeDisabled();
  expect(executeRegistryCommand).not.toHaveBeenCalled();
});

test("analyst command payload includes alert, incident, playbook, and approval context", async () => {
  executeRegistryCommand.mockResolvedValue({
    success: true,
    outcome_label: "monitored",
    message: "Monitoring disposition recorded.",
    idempotent: false,
  });

  renderRegistry(
    <ResponseRegistryPanel
      {...styleProps}
      canTakeAlertActions
      navigationRequest={{
        nonce: 1,
        relatedAlertId: 42,
        relatedIncidentId: 77,
        relatedPlaybookExecutionId: 19,
        relatedApprovalRequestId: 31,
        q: "8.8.8.8",
      }}
    />
  );
  const detail = await openFirstRow();

  await userEvent.click(within(detail).getByRole("button", { name: "Monitor" }));
  await waitFor(() => {
    expect(executeRegistryCommand).toHaveBeenCalledWith(
      expect.objectContaining({
        action: "monitor",
        indicatorValue: "8.8.8.8",
        alertId: 42,
        incidentId: 77,
        playbookExecutionId: 19,
        approvalRequestId: 31,
      })
    );
  });
});

test("detail retry reloads the selected record", async () => {
  loadRegistryDetail
    .mockRejectedValueOnce(new Error("detail failed"))
    .mockResolvedValueOnce(makeDetail());

  renderRegistry(<ResponseRegistryPanel {...styleProps} canTakeAlertActions />);
  const detail = await openFirstRow();
  expect(within(detail).getByText("detail failed")).toBeInTheDocument();

  await userEvent.click(within(detail).getByRole("button", { name: "Retry detail" }));
  await waitFor(() => {
    expect(loadRegistryDetail).toHaveBeenCalledTimes(2);
  });
  expect(await within(detail).findByText("Response Summary")).toBeInTheDocument();
});

test("separates tracking reason and incident reason and uses clearer incident wording", async () => {
  executeRegistryCommand.mockResolvedValue({
    success: true,
    outcome_label: "escalated",
    message: "Escalation recorded; incident 77.",
    idempotent: false,
  });

  renderRegistry(<ResponseRegistryPanel {...styleProps} canTakeAlertActions />);
  const detail = await openFirstRow();

  expect(
    within(detail).getByRole("button", { name: "Create / Link Incident" })
  ).toBeInTheDocument();

  const trackingInput = within(detail).getByLabelText("Tracking reason");
  const incidentInput = within(detail).getByLabelText("Incident reason");
  await userEvent.type(trackingInput, "watch scanner");
  await userEvent.type(incidentInput, "incident handoff");

  expect(trackingInput).toHaveValue("watch scanner");
  expect(incidentInput).toHaveValue("incident handoff");

  await userEvent.click(within(detail).getByRole("button", { name: "Create / Link Incident" }));
  await waitFor(() => {
    expect(executeRegistryCommand).toHaveBeenCalledWith(
      expect.objectContaining({
        action: "flag_high_priority",
        reason: "incident handoff",
      })
    );
  });
});

test("shows actionable backend errors without losing detail state", async () => {
  executeRegistryCommand.mockRejectedValue(
    new Error("No actionable IP is available for this registry record.")
  );
  renderRegistry(<ResponseRegistryPanel {...styleProps} canTakeAlertActions />);
  const detail = await openFirstRow();

  await userEvent.click(within(detail).getByRole("button", { name: "Monitor" }));
  expect(
    await screen.findByText("No actionable IP is available for this registry record.")
  ).toBeInTheDocument();
  expect(within(detail).getByText("Response Summary")).toBeInTheDocument();
});

test("blocklist tracking view embeds blocklist manager", async () => {
  render(
    <ResponseRegistryPanel
      {...styleProps}
      canTakeAlertActions
      initialView="blocklist_tracking"
    />
  );

  expect(await screen.findByTestId("registry-view-blocklist_tracking")).toBeInTheDocument();
  expect(screen.getByRole("tab", { name: "Blocklist Tracking" })).toHaveAttribute(
    "aria-selected",
    "true"
  );
  expect(await screen.findByTestId("registry-blocklist-embed")).toBeInTheDocument();
  expect(screen.getByText("Blocklist embed")).toBeInTheDocument();
});

test("Remove Tracking is discoverable for active tracking and explains no firewall change", async () => {
  loadRegistryDetail.mockResolvedValue(
    makeDetail({
      record: {
        id: 11,
        indicator_value: "8.8.8.8",
        current_disposition: "blocklist_tracked",
        created_at: "2026-07-01T12:00:00+00:00",
        updated_at: "2026-07-10T12:00:00+00:00",
      },
      blocklist_entry: {
        id: 44,
        status: "active",
        reason: "Tracked",
        expires_at: null,
      },
      latest_event: {
        requested_action: "block_ip",
        outcome: "succeeded",
        enforcement: "tracking_only",
      },
      events: [],
    })
  );
  executeRegistryCommand.mockResolvedValue({
    success: true,
    action: "remove_tracking",
    message: "SIEM Blocklist tracking removed.",
    enforcement: "none",
    blocked_ip_id: 44,
    registry_record_id: 11,
  });

  renderRegistry(<ResponseRegistryPanel {...styleProps} canTakeAlertActions />);
  const detail = await openFirstRow();

  const removeButton = within(detail).getByRole("button", { name: "Remove Tracking" });
  expect(removeButton).toBeEnabled();
  await userEvent.click(removeButton);

  await waitFor(() => {
    expect(executeRegistryCommand).toHaveBeenCalledWith(
      expect.objectContaining({ action: "remove_tracking", indicatorValue: "8.8.8.8" })
    );
  });
});
