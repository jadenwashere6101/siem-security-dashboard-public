function TargetedAlertPanel({
  targetedAlertMeta,
  correlationAlert,
  correlatedAlertTypes,
  correlationPanelStyle,
  targetedAlertPanelStyle,
  expandedLabelStyle,
  expandedTextStyle,
  correlationListStyle,
  monoCellStyle,
  alert,
}) {
  return (
    <div style={correlationAlert ? correlationPanelStyle : targetedAlertPanelStyle}>
      <p style={expandedLabelStyle}>
        {correlationAlert ? "Correlation Alert" : "Targeted Correlation Alert"}
      </p>
      <div style={{ marginBottom: "8px" }}>
        <span style={targetedAlertMeta.badgeStyle}>{targetedAlertMeta.badge}</span>
      </div>
      <p style={expandedTextStyle}>
        {targetedAlertMeta.description}
      </p>
      {correlationAlert && correlatedAlertTypes.length > 0 ? (
        <div>
          <p style={expandedTextStyle}>
            <strong>Involved Alert Types:</strong>
          </p>
          <ul style={correlationListStyle}>
            {correlatedAlertTypes.map((alertType) => (
              <li key={alertType}>
                <span style={{ ...monoCellStyle, fontSize: "12px" }}>
                  {alertType}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <p style={expandedTextStyle}>
          <strong>{correlationAlert ? "Correlation Message" : "Alert Message"}:</strong> {alert.message}
        </p>
      )}
    </div>
  );
}

export default TargetedAlertPanel;
