import { getBehavioralReputation, getExternalReputation } from "../utils/alertDisplay";

function AlertReputationDetails({
  alert,
  expandedTextStyle,
  detailLabelTextStyle,
  expandedSecondaryTextStyle,
  sourceBadgeStyle,
  getReputationBadgeStyle,
}) {
  const externalReputation = getExternalReputation(alert);
  const behavioralReputation = getBehavioralReputation(alert);

  return (
    <>
      <p style={{ ...expandedTextStyle, marginBottom: "6px" }}>
        <strong style={detailLabelTextStyle}>External Threat Intelligence Reputation:</strong>{" "}
        <span
          style={{ ...sourceBadgeStyle, ...getReputationBadgeStyle(externalReputation.label) }}
          title={`External threat intelligence: ${externalReputation.label} (${externalReputation.score ?? "n/a"}) via ${externalReputation.source}`}
        >
          {externalReputation.label} ({externalReputation.score ?? "n/a"})
        </span>
      </p>
      <p style={expandedSecondaryTextStyle}>
        Provider/source: {externalReputation.source}
      </p>
      <p style={{ marginTop: "8px", color: "#e6edf3" }}>
        {externalReputation.summary}
      </p>

      <p style={{ ...expandedTextStyle, marginBottom: "6px", marginTop: "12px" }}>
        <strong style={detailLabelTextStyle}>Behavioral Reputation:</strong>{" "}
        <span
          style={{ ...sourceBadgeStyle, ...getReputationBadgeStyle(behavioralReputation.label) }}
          title={`Behavioral reputation: ${behavioralReputation.label} (${behavioralReputation.score})`}
        >
          {behavioralReputation.label} ({behavioralReputation.score})
        </span>
      </p>
      <p style={expandedSecondaryTextStyle}>
        Internal SIEM-generated behavioral score
      </p>
      <p style={{ marginTop: "8px", color: "#e6edf3" }}>
        {behavioralReputation.summary}
      </p>
    </>
  );
}

export default AlertReputationDetails;
