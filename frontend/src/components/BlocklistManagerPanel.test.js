import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import BlocklistManagerPanel from "./BlocklistManagerPanel";
import {
  addBlocklistEntry,
  loadBlocklistEntries,
  unblockBlocklistEntry,
} from "../services/blocklistService";

jest.mock("../services/blocklistService", () => ({
  loadBlocklistEntries: jest.fn(),
  addBlocklistEntry: jest.fn(),
  unblockBlocklistEntry: jest.fn(),
}));

const styleProps = {
  cardStyle: {},
  cardHeaderStyle: {},
  cardTitleStyle: {},
  cardSubtitleStyle: {},
  filterLabelStyle: {},
  selectStyle: {},
};

beforeEach(() => {
  jest.clearAllMocks();
});

test("BlocklistManagerPanel shows tracking-only badge and enforcement disclaimer", async () => {
  loadBlocklistEntries.mockResolvedValue([
    {
      id: 1,
      ip_address: "203.0.113.10",
      status: "active",
      reason: "Repeated abuse",
      response_outcome: {
        execution_mode: "tracking_only",
        execution_state: "succeeded",
        tracking_recorded: true,
        external_executed: false,
        simulated: false,
      },
    },
  ]);

  render(<BlocklistManagerPanel {...styleProps} />);

  expect(await screen.findByText("203.0.113.10")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Blocklist Tracking" })).toBeInTheDocument();
  expect(screen.getAllByText("Tracking only").length).toBeGreaterThan(0);
  expect(
    screen.getByText(/does not change any firewall, provider, or host/i)
  ).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Remove Tracking" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Unblock/i })).not.toBeInTheDocument();
});

test("Remove Tracking calls unblock API and shows tracking-only success copy", async () => {
  loadBlocklistEntries
    .mockResolvedValueOnce([
      {
        id: 1,
        ip_address: "203.0.113.10",
        status: "active",
        reason: "Repeated abuse",
        response_outcome: null,
      },
    ])
    .mockResolvedValueOnce([
      {
        id: 1,
        ip_address: "203.0.113.10",
        status: "inactive",
        reason: "Repeated abuse",
        response_outcome: null,
      },
    ]);
  unblockBlocklistEntry.mockResolvedValue({
    message:
      "SIEM Blocklist tracking removed. History remains; no firewall or host enforcement changed.",
    enforcement: "none",
  });

  render(<BlocklistManagerPanel {...styleProps} canTakeAlertActions />);
  await userEvent.click(await screen.findByRole("button", { name: "Remove Tracking" }));

  await waitFor(() => expect(unblockBlocklistEntry).toHaveBeenCalledWith(1));
  expect(
    await screen.findByText(/History remains; no firewall or host enforcement changed/i)
  ).toBeInTheDocument();
});

test("inactive records keep history readable and disable Remove Tracking", async () => {
  loadBlocklistEntries.mockResolvedValue([
    {
      id: 2,
      ip_address: "198.51.100.5",
      status: "inactive",
      reason: "Expired hold",
      response_outcome: null,
    },
  ]);

  render(<BlocklistManagerPanel {...styleProps} />);

  expect(await screen.findByText("198.51.100.5")).toBeInTheDocument();
  expect(screen.getByText(/Inactive — history preserved/i)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Remove Tracking" })).not.toBeInTheDocument();
  expect(screen.getByText("No canonical outcome")).toBeInTheDocument();
});

test("viewers see locked Remove Tracking explanation", async () => {
  loadBlocklistEntries.mockResolvedValue([
    {
      id: 3,
      ip_address: "198.51.100.9",
      status: "active",
      reason: "Watch",
      response_outcome: null,
    },
  ]);

  render(<BlocklistManagerPanel {...styleProps} canTakeAlertActions={false} />);

  expect(await screen.findByText("198.51.100.9")).toBeInTheDocument();
  expect(screen.getByText(/locked for this role/i)).toBeInTheDocument();
  expect(screen.getByText(/cannot remove tracking/i)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Remove Tracking" })).not.toBeInTheDocument();
  expect(addBlocklistEntry).not.toHaveBeenCalled();
});
