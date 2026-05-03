function AlertCorrelationSignals({
  alert,
  detailSectionStyle,
  signalRowStyle,
  sourceTypeTextStyle,
}) {
  return (
    <div style={detailSectionStyle}>
      <strong>Contributing Signals:</strong>
      {Array.isArray(alert.contributing_signals) && alert.contributing_signals.length > 0 ? (
        alert.contributing_signals.map((signal) => (
          <div key={signal.signal} style={signalRowStyle}>
            <span>{signal.label}</span>
            <span style={sourceTypeTextStyle}>
              count {signal.count} · weight {signal.weight} · total {signal.total}
            </span>
          </div>
        ))
      ) : (
        <div style={{ fontSize: "12px", color: "#8b949e", marginTop: "4px" }}>
          No contributing signals
        </div>
      )}
    </div>
  );
}

export default AlertCorrelationSignals;
