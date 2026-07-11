import { getBehavioralReputation } from "../utils/alertDisplay";

function AlertCorrelationSignals({
  alert,
  detailSectionStyle,
  signalRowStyle,
  sourceTypeTextStyle,
}) {
  const contributingSignals = getBehavioralReputation(alert).contributing_signals;

  return (
    <div style={detailSectionStyle}>
      <strong style={{ color: "#cbd5e1" }}>Behavioral Contributing Signals:</strong>
      {contributingSignals.length > 0 ? (
        contributingSignals.map((signal) => (
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
