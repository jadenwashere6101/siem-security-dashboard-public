import { render, screen } from "@testing-library/react";

import AlertReputationDetails from "./AlertReputationDetails";

const expandedTextStyle = { color: "#e6edf3" };
const detailLabelTextStyle = { color: "#cbd5e1" };
const expandedSecondaryTextStyle = { color: "#8b949e" };

const alertFixture = {
  reputation_label: "Suspicious",
  reputation_score: 42,
  reputation_source: "abuseipdb",
  reputation_summary: "2799 reports. ISP: Linode",
  behavioral_reputation: {
    label: "Normal",
    score: 0,
    source: "siem_internal",
    summary: "No elevated behavioral signals observed in SIEM history.",
  },
};

test("external and behavioral reputation summaries use explicit readable dark-theme foregrounds under a black parent", () => {
  render(
    <div style={{ color: "#000000" }}>
      <AlertReputationDetails
        alert={alertFixture}
        expandedTextStyle={expandedTextStyle}
        detailLabelTextStyle={detailLabelTextStyle}
        expandedSecondaryTextStyle={expandedSecondaryTextStyle}
        sourceBadgeStyle={{}}
        getReputationBadgeStyle={() => ({})}
      />
    </div>
  );

  const externalSummary = screen.getByText("2799 reports. ISP: Linode");
  expect(externalSummary).toHaveStyle({ color: "#e6edf3" });
  expect(externalSummary).not.toHaveStyle({ color: "inherit" });

  const behavioralSummary = screen.getByText(
    "No elevated behavioral signals observed in SIEM history."
  );
  expect(behavioralSummary).toHaveStyle({ color: "#e6edf3" });
  expect(behavioralSummary).not.toHaveStyle({ color: "inherit" });
});

test("falls back to default summary copy when reputation data is absent", () => {
  render(
    <div style={{ color: "#000000" }}>
      <AlertReputationDetails
        alert={{}}
        expandedTextStyle={expandedTextStyle}
        detailLabelTextStyle={detailLabelTextStyle}
        expandedSecondaryTextStyle={expandedSecondaryTextStyle}
        sourceBadgeStyle={{}}
        getReputationBadgeStyle={() => ({})}
      />
    </div>
  );

  expect(
    screen.getByText("No external threat intelligence details available.")
  ).toHaveStyle({ color: "#e6edf3" });
  expect(
    screen.getByText("No behavioral reputation details available.")
  ).toHaveStyle({ color: "#e6edf3" });
});
