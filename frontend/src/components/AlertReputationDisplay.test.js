import { render, screen } from "@testing-library/react";

import AlertCorrelationSignals from "./AlertCorrelationSignals";
import AlertDetailsPanel from "./AlertDetailsPanel";
import AlertReputationDetails from "./AlertReputationDetails";
import AlertTableRow from "./AlertTableRow";

const alert = {
  id: 7,
  alert_type: "failed_login_threshold",
  source_ip: "198.51.100.7",
  severity: "high",
  status: "open",
  message: "Failed login threshold exceeded",
  city: "New York",
  country: "United States",
  reputation_score: 71,
  reputation_label: "abuseipdb-high",
  reputation_source: "abuseipdb",
  reputation_summary: "Stored AbuseIPDB snapshot",
  behavioral_reputation: {
    score: 12,
    label: "High Risk",
    source: "siem_internal",
    summary: "Password spraying activity",
    contributing_signals: [
      {
        signal: "password_spraying_threshold",
        label: "Password Spraying",
        count: 2,
        weight: 5,
        total: 10,
      },
    ],
  },
};

const baseStyle = {};
const getReputationBadgeStyle = () => ({});
const getSeverityBadgeStyle = () => ({});
const sourceBadge = { label: "App / Bank", subLabel: "custom", style: {} };

test("AlertReputationDetails renders external and behavioral reputation separately", () => {
  render(
    <AlertReputationDetails
      alert={alert}
      expandedTextStyle={baseStyle}
      detailLabelTextStyle={baseStyle}
      expandedSecondaryTextStyle={baseStyle}
      sourceBadgeStyle={baseStyle}
      getReputationBadgeStyle={getReputationBadgeStyle}
    />
  );

  expect(screen.getByText("External Threat Intelligence Reputation:")).toBeInTheDocument();
  expect(screen.getByText("abuseipdb-high (71)")).toBeInTheDocument();
  expect(screen.getByText("Provider/source: abuseipdb")).toBeInTheDocument();
  expect(screen.getByText("Stored AbuseIPDB snapshot")).toBeInTheDocument();
  expect(screen.getByText("Behavioral Reputation:")).toBeInTheDocument();
  expect(screen.getByText("High Risk (12)")).toBeInTheDocument();
  expect(screen.getByText("Password spraying activity")).toBeInTheDocument();
});

test("AlertCorrelationSignals reads behavioral contributing signals", () => {
  render(
    <AlertCorrelationSignals
      alert={alert}
      detailSectionStyle={baseStyle}
      signalRowStyle={baseStyle}
      sourceTypeTextStyle={baseStyle}
    />
  );

  expect(screen.getByText("Behavioral Contributing Signals:")).toBeInTheDocument();
  expect(screen.getByText("Password Spraying")).toBeInTheDocument();
  expect(screen.getByText("count 2 · weight 5 · total 10")).toBeInTheDocument();
});

test("AlertDetailsPanel renders both reputation concepts", () => {
  render(
    <AlertDetailsPanel
      selectedAlert={alert}
      selectedAlertTimeline={[]}
      getSourceBadgeMeta={() => sourceBadge}
      getTargetedAlertMeta={() => null}
      isCorrelationAlert={() => false}
      getCorrelationAlertTypes={() => []}
      correlationPanelStyle={baseStyle}
      targetedAlertPanelStyle={baseStyle}
      expandedLabelStyle={baseStyle}
      expandedTextStyle={baseStyle}
      monoCellStyle={baseStyle}
      correlationListStyle={baseStyle}
      signalRowStyle={baseStyle}
      sourceTypeTextStyle={baseStyle}
    />
  );

  expect(screen.getByText(/External Threat Intelligence Reputation:/)).toBeInTheDocument();
  expect(screen.getByText(/abuseipdb-high \(71\)/)).toBeInTheDocument();
  expect(screen.getByText(/Threat Intel Source:/)).toBeInTheDocument();
  expect(screen.getByText(/Behavioral Reputation:/)).toBeInTheDocument();
  expect(screen.getByText(/High Risk \(12\)/)).toBeInTheDocument();
  expect(screen.getByText("Behavioral Contributing Signals:")).toBeInTheDocument();
});

test("AlertTableRow shows external and behavioral badges", () => {
  render(
    <table>
      <tbody>
        <AlertTableRow
          alert={alert}
          sourceBadge={sourceBadge}
          targetedAlertMeta={null}
          isSelected={false}
          isHovered={false}
          onRowClick={() => {}}
          onHoverStart={() => {}}
          onHoverEnd={() => {}}
          onResolve={() => {}}
          canTakeAlertActions={true}
          getActionButtonStyle={(style) => style}
          getSeverityBadgeStyle={getSeverityBadgeStyle}
          tableRowStyle={baseStyle}
          bodyCellStyle={baseStyle}
          monoCellStyle={baseStyle}
        />
      </tbody>
    </table>
  );

  expect(screen.getByText("Threat Intel: abuseipdb-high")).toBeInTheDocument();
  expect(screen.getByText("Score 71 · abuseipdb")).toBeInTheDocument();
  expect(screen.getByText("Behavioral: High Risk")).toBeInTheDocument();
  expect(screen.getByText("Score 12")).toBeInTheDocument();
});

