import React from "react";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import ResponseRegistryPanel from "./ResponseRegistryPanel";
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

async function openFirstRow() {
  const row = await screen.findByRole("row", {
    name: /Registry record 8\.8\.8\.8/i,
  });
  await userEvent.click(row);
  const detail = await screen.findByLabelText("Registry detail");
  await waitFor(() => {
    expect(within(detail).queryByText(/Loading detail/i)).not.toBeInTheDocument();
  });
  expect(within(detail).getByText("Indicator detail")).toBeInTheDocument();
  return detail;
}

beforeEach(() => {
  jest.clearAllMocks();
  loadRegistryRecords.mockResolvedValue({
    items: [
      {
        id: 11,
        indicator_value: "8.8.8.8",
        current_disposition: "monitored",
        latest_requested_action: "monitor",
        latest_outcome: "succeeded",
        enforcement: "none",
        latest_origin_surface: "response_registry",
        updated_at: "2026-07-10T12:00:00+00:00",
      },
    ],
    total: 1,
  });
  loadRegistryDetail.mockResolvedValue({
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
        origin_surface: "response_registry",
        created_at: "2026-07-10T12:00:00+00:00",
        reason: "Watch",
      },
    ],
    blocklist_entry: null,
    related_alert_ids: [42],
    related_incident_ids: [],
    related_alert_count: 1,
    related_incident_count: 0,
    enforcement: "none",
    enforcement_statement: "No firewall or host enforcement.",
    first_seen: "2026-07-01T12:00:00+00:00",
    last_updated: "2026-07-10T12:00:00+00:00",
    response_source: "response_registry",
  });
});

test("shows loading then registry rows", async () => {
  render(<ResponseRegistryPanel {...styleProps} canTakeAlertActions />);

  expect(screen.getByText(/Loading response registry/i)).toBeInTheDocument();
  expect(
    await screen.findByRole("row", { name: /Registry record 8\.8\.8\.8/i })
  ).toBeInTheDocument();
  expect(screen.getAllByText("monitored").length).toBeGreaterThan(0);
});

test("shows empty state when no records", async () => {
  loadRegistryRecords.mockResolvedValue({ items: [], total: 0 });
  render(<ResponseRegistryPanel {...styleProps} canTakeAlertActions />);

  expect(
    await screen.findByText(/No registry records match the current filters/i)
  ).toBeInTheDocument();
});

test("shows error state with retry", async () => {
  loadRegistryRecords.mockRejectedValueOnce(new Error("boom"));
  render(<ResponseRegistryPanel {...styleProps} canTakeAlertActions />);

  expect(await screen.findByRole("alert")).toHaveTextContent("boom");
  expect(screen.getByRole("button", { name: /Retry/i })).toBeInTheDocument();
});

test("opens detail and shows history and related alerts", async () => {
  render(<ResponseRegistryPanel {...styleProps} canTakeAlertActions />);
  const detail = await openFirstRow();

  expect(within(detail).getByText("Indicator detail")).toBeInTheDocument();
  expect(
    await within(detail).findByText("No firewall or host enforcement.")
  ).toBeInTheDocument();
  expect(within(detail).getByText("42")).toBeInTheDocument();
  expect(within(detail).getByText(/monitor_started/i)).toBeInTheDocument();
});

test("viewer cannot mutate and sees locked explanation", async () => {
  render(<ResponseRegistryPanel {...styleProps} canTakeAlertActions={false} />);
  const detail = await openFirstRow();

  expect(
    within(detail).getByText(/Mutation controls are locked for this role/i)
  ).toBeInTheDocument();
  expect(within(detail).getByRole("button", { name: "Monitor" })).toBeDisabled();
  expect(executeRegistryCommand).not.toHaveBeenCalled();
});

test("analyst can run monitor command and shows canonical outcome message", async () => {
  executeRegistryCommand.mockResolvedValue({
    success: true,
    outcome_label: "monitored",
    message: "Monitoring disposition recorded.",
    idempotent: false,
  });
  render(<ResponseRegistryPanel {...styleProps} canTakeAlertActions />);
  const detail = await openFirstRow();

  await userEvent.click(within(detail).getByRole("button", { name: "Monitor" }));

  await waitFor(() => {
    expect(executeRegistryCommand).toHaveBeenCalledWith(
      expect.objectContaining({
        action: "monitor",
        indicatorValue: "8.8.8.8",
      })
    );
  });
  expect(
    await screen.findByText("Monitoring disposition recorded.")
  ).toBeInTheDocument();
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

test("truthful tracking-only copy is present in workspace subtitle", async () => {
  render(<ResponseRegistryPanel {...styleProps} canTakeAlertActions />);
  expect(
    await screen.findByText(/no firewall enforcement is implied/i)
  ).toBeInTheDocument();
});
