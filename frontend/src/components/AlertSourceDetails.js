function AlertSourceDetails({
  alert,
  sourceBadge,
  expandedTextStyle,
  detailLabelTextStyle,
  detailValueTextStyle,
  expandedSecondaryTextStyle,
  detailSectionStyle,
  monoCellStyle,
}) {
  return (
    <>
      <p style={{ ...expandedTextStyle, marginBottom: "6px" }}>
        <strong style={detailLabelTextStyle}>Source:</strong>{" "}
        <span style={detailValueTextStyle}>{sourceBadge.label}</span>{" "}
        <span style={expandedSecondaryTextStyle}>
          ({sourceBadge.subLabel})
        </span>
      </p>

      <div style={detailSectionStyle}>
        <p style={{ ...expandedTextStyle, marginBottom: "6px" }}>
          <strong style={detailLabelTextStyle}>Source IP:</strong>{" "}
          <span style={{ ...monoCellStyle, ...detailValueTextStyle }}>
            {alert.source_ip}
          </span>
        </p>

        <p style={{ ...expandedTextStyle, marginBottom: "6px" }}>
          <strong style={detailLabelTextStyle}>Location:</strong>{" "}
          <span style={detailValueTextStyle}>{alert.city && alert.country
            ? `${alert.city}, ${alert.country}`
            : "Location unavailable"}</span>
        </p>
      </div>

    </>
  );
}

export default AlertSourceDetails;
