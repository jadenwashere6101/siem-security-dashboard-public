import { fireEvent, render, screen } from "@testing-library/react";

import MapView from "./MapView";
import { loadSourceIpContext } from "../services/sourceIpContextService";

jest.mock("../services/sourceIpContextService", () => ({
  loadSourceIpContext: jest.fn(),
}));

jest.mock("react-simple-maps", () => ({
  ComposableMap: ({ children }) => <div>{children}</div>,
  Geographies: ({ children }) => (
    <div>
      {children({ geographies: [{ rsmKey: "test-geo" }] })}
    </div>
  ),
  Geography: () => <div>Geography</div>,
  Marker: ({ onClick }) => <button type="button" onClick={onClick}>alert marker</button>,
  ZoomableGroup: ({ children }) => <div>{children}</div>,
}));

beforeEach(() => {
  loadSourceIpContext.mockReset();
  loadSourceIpContext.mockResolvedValue({
    source_ip: "8.8.8.8",
    alerts: { counts: { total: 1, open: 1, resolved: 0 }, recent: [] },
    incidents: { count: 0, recent: [] },
    queue: { counts: { total: 0, by_status: {} }, recent: [] },
    blocklist: { effective_status: "none", entries: [] },
    reputation: {
      behavioral: { score: 0, label: "Normal", summary: "No elevated behavioral signals observed in SIEM history." },
      latest_external: null,
      external_snapshots: [],
    },
    playbook_executions: { count: 0, recent: [] },
  });
});

test("MapView opens source-IP context from selected marker source IP", async () => {
  render(
    <MapView
      alerts={[
        {
          id: 9,
          alert_type: "failed_login_threshold",
          source_ip: "8.8.8.8",
          latitude: 40.7128,
          longitude: -74.006,
          city: "New York",
          country: "United States",
          severity: "high",
          message: "Failed login threshold exceeded",
          reputation_score: 71,
          reputation_label: "abuseipdb-high",
          reputation_source: "abuseipdb",
          reputation_summary: "Stored AbuseIPDB snapshot",
          behavioral_reputation: {
            score: 12,
            label: "High Risk",
            source: "siem_internal",
            summary: "Password spraying activity",
            contributing_signals: [],
          },
        },
      ]}
    />
  );

  fireEvent.click(screen.getByRole("button", { name: "alert marker" }));

  expect(screen.getByText("Source-IP Context")).toBeInTheDocument();
  expect(await screen.findByText("Alerts")).toBeInTheDocument();
  expect(loadSourceIpContext).toHaveBeenCalledWith("8.8.8.8");
});
