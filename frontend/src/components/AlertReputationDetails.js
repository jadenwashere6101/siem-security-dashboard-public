function AlertReputationDetails({
  alert,
  expandedTextStyle,
  detailLabelTextStyle,
  expandedSecondaryTextStyle,
  sourceBadgeStyle,
  getReputationBadgeStyle,
}) {
  return (
    <>
      <p style={{ ...expandedTextStyle, marginBottom: "6px" }}>
        <strong style={detailLabelTextStyle}>Behavioral Reputation:</strong>{" "}
        <span
          style={{ ...sourceBadgeStyle, ...getReputationBadgeStyle(alert.reputation_label) }}
          title={`Behavioral reputation: ${alert.reputation_label || "Normal"} (${alert.reputation_score ?? 0})`}
        >
          {alert.reputation_label || "Normal"} ({alert.reputation_score ?? 0})
        </span>
      </p>
      <p style={expandedSecondaryTextStyle}>
        Internal SIEM-generated behavioral score
      </p>
      <p style={{ marginTop: "8px" }}>
        {alert.reputation_summary || "No reputation details available"}
      </p>
    </>
  );
}

export default AlertReputationDetails;
