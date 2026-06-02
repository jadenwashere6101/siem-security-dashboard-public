import { fireEvent, render, screen } from "@testing-library/react";

import MapView from "./MapView";

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

test("MapView separates external threat intelligence and behavioral reputation", () => {
  render(
    <MapView
      alerts={[
        {
          id: 9,
          alert_type: "failed_login_threshold",
          source_ip: "198.51.100.9",
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

  const buttons = screen.getAllByRole("button");
  fireEvent.click(buttons[buttons.length - 1]);

  expect(screen.getByText("External Threat Intelligence Reputation:")).toBeInTheDocument();
  expect(screen.getByText("abuseipdb-high (71)")).toBeInTheDocument();
  expect(screen.getByText("Source: abuseipdb")).toBeInTheDocument();
  expect(screen.getByText("Stored AbuseIPDB snapshot")).toBeInTheDocument();
  expect(screen.getByText("Behavioral Reputation:")).toBeInTheDocument();
  expect(screen.getByText("High Risk (12)")).toBeInTheDocument();
  expect(screen.getByText("Password spraying activity")).toBeInTheDocument();
});
