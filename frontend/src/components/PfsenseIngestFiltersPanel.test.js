import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import PfsenseIngestFiltersPanel from "./PfsenseIngestFiltersPanel";
import * as service from "../services/pfsenseIngestFilterService";

jest.mock("../services/pfsenseIngestFilterService");

const categories = {
  block_events: { enabled: true, parameters: {}, description: "Retain blocks.", override_status: "applied", updated_at: "2026-07-10T10:00:00Z" },
  inbound_sensitive_port_allows: { enabled: true, parameters: { sensitive_ports: [22, 443] }, description: "Retain sensitive allows.", override_status: "applied" },
  all_allow_events: { enabled: false, parameters: {}, description: "Retain all allows.", override_status: "applied" },
  dns_traffic: { enabled: false, parameters: {}, description: "Port 53 only.", override_status: "applied" },
  icmp_traffic: { enabled: false, parameters: {}, description: "Allowed ICMP.", override_status: "applied" },
};

const props = { cardStyle: {}, cardHeaderStyle: {}, cardTitleStyle: {}, cardSubtitleStyle: {} };

beforeEach(() => {
  service.loadPfsenseIngestFilters.mockResolvedValue({ status: "applied", categories });
  service.loadPfsenseIngestFilterMetrics.mockResolvedValue({ started_at: "2026-07-10T10:00:00Z", counts: { "filtered:no_enabled_retention_category": 4 } });
  service.updatePfsenseIngestFilter.mockResolvedValue({});
});

test("renders accurate dark-theme controls and policy explanations", async () => {
  render(<PfsenseIngestFiltersPanel {...props} />);
  expect(await screen.findByRole("heading", { name: "pfSense Ingest Filters" })).toBeInTheDocument();
  expect(await screen.findByText("DNS port-53 traffic")).toBeInTheDocument();
  expect(screen.getByText(/does not inspect resolver queries or domains/i)).toBeInTheDocument();
  expect(screen.getByText(/controls SIEM storage, not firewall enforcement/i)).toBeInTheDocument();
  expect(screen.getByLabelText("Sensitive destination ports")).toHaveValue("22, 443");
  expect(screen.getByText(/filtered:no_enabled_retention_category/)).toBeInTheDocument();
});

test("toggle saves and reloads next-request policy", async () => {
  render(<PfsenseIngestFiltersPanel {...props} />);
  const allAllowed = await screen.findByText("All allowed traffic");
  const card = allAllowed.closest("article");
  fireEvent.click(card.querySelector('input[type="checkbox"]'));
  await waitFor(() => expect(service.updatePfsenseIngestFilter).toHaveBeenCalledWith("all_allow_events", true, {}));
  expect(service.loadPfsenseIngestFilters).toHaveBeenCalledTimes(2);
  expect(await screen.findByRole("status")).toHaveTextContent(/next pfSense request/i);
});

test("invalid duplicate ports disable save and fallback is disclosed", async () => {
  service.loadPfsenseIngestFilters.mockResolvedValue({ status: "unavailable", categories });
  render(<PfsenseIngestFiltersPanel {...props} />);
  expect(await screen.findByText(/restrictive source-controlled defaults are active/i)).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Sensitive destination ports"), { target: { value: "22, 22" } });
  expect(screen.getByRole("button", { name: "Save sensitive ports" })).toBeDisabled();
});

test("backend failures are announced accessibly", async () => {
  service.loadPfsenseIngestFilters.mockRejectedValue(new Error("Forbidden"));
  render(<PfsenseIngestFiltersPanel {...props} />);
  expect(await screen.findByRole("alert")).toHaveTextContent("Forbidden");
});

test("formats policy and metrics timestamps with shared display preferences", async () => {
  const { rerender } = render(
    <PfsenseIngestFiltersPanel
      {...props}
      displaySettings={{ timezoneMode: "utc", timestampFormat: "12h" }}
    />
  );

  expect(await screen.findAllByText(/Jul 10, 2026, 10:00 AM UTC/)).toHaveLength(2);

  rerender(
    <PfsenseIngestFiltersPanel
      {...props}
      displaySettings={{ timezoneMode: "utc", timestampFormat: "24h" }}
    />
  );

  expect(screen.getAllByText(/Jul 10, 2026, 10:00 UTC/)).toHaveLength(2);
  expect(screen.queryByText(/10:00 AM UTC/)).not.toBeInTheDocument();
});
