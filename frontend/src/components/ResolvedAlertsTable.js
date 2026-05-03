function ResolvedAlertsTable({
  resolvedAlerts,
  cardStyle,
  cardHeaderStyle,
  cardTitleStyle,
  tableWrapperStyle,
  tableStyle,
  headerCellStyle,
  bodyCellStyle,
}) {
  return (
    <section
      style={{
        ...cardStyle,
        marginTop: "24px",
      }}
    >
      <div style={cardHeaderStyle}>
        <h2 style={cardTitleStyle}>Resolved Alerts</h2>
      </div>

      <div style={tableWrapperStyle}>
        <table style={tableStyle}>
          <thead>
            <tr>
              <th style={headerCellStyle}>Type</th>
              <th style={headerCellStyle}>Severity</th>
              <th style={headerCellStyle}>Source IP</th>
              <th style={headerCellStyle}>Message</th>
              <th style={headerCellStyle}>Time</th>
            </tr>
          </thead>

          <tbody>
            {resolvedAlerts.map((alert) => (
              <tr key={alert.id}>
                <td style={bodyCellStyle}>{alert.alert_type}</td>
                <td style={bodyCellStyle}>{alert.severity}</td>
                <td style={bodyCellStyle}>
                  <div>{alert.source_ip}</div>
                  <div style={{ fontSize: "12px", color: "#666", marginTop: "4px" }}>
                    {alert.city && alert.country
                      ? `${alert.city}, ${alert.country}`
                      : "Location unavailable"}
                  </div>
                </td>
                <td style={bodyCellStyle}>{alert.message}</td>
                <td style={bodyCellStyle}>{alert.created_at}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export default ResolvedAlertsTable;
