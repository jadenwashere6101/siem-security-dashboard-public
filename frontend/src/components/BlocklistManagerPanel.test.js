import React from "react";
import { render, screen } from "@testing-library/react";

import BlocklistManagerPanel from "./BlocklistManagerPanel";
import { loadBlocklistEntries } from "../services/blocklistService";

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
  expect(screen.getAllByText("Tracking only").length).toBeGreaterThan(0);
  expect(
    screen.getByText("SIEM tracking only; no firewall or host enforcement is implied.")
  ).toBeInTheDocument();
});

test("BlocklistManagerPanel leaves entries without canonical outcome unchanged", async () => {
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
  expect(screen.getByText("No canonical outcome")).toBeInTheDocument();
  expect(
    screen.queryByText("SIEM tracking only; no firewall or host enforcement is implied.")
  ).not.toBeInTheDocument();
});
