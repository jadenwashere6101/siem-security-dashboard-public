import React from "react";

function ThreatHuntEventDetails({
  event,
  sourceBadge,
  getReputationBadgeStyle,
  formatRawPayload,
  expandedDetailTextStyle,
  expandedSupportTextStyle,
  expandedSignalsLabelStyle,
  expandedLabelStyle,
  sourceBadgeStyle,
  sourceTypeTextStyle,
  signalRowStyle,
  noSignalTextStyle,
  rawPayloadStyle,
}) {
  return (
    <>
      <p style={expandedDetailTextStyle}>
        <strong>Source:</strong> {sourceBadge.label}{" "}
        <span style={sourceTypeTextStyle}>({sourceBadge.subLabel})</span>
      </p>
      <p style={expandedDetailTextStyle}>
        <strong>Behavioral Reputation:</strong>{" "}
        <span style={{ ...sourceBadgeStyle, ...getReputationBadgeStyle(event.reputation_label) }}>
          {event.reputation_label || "Normal"} ({event.reputation_score ?? 0})
        </span>
      </p>
      <p style={expandedSupportTextStyle}>
        Internal SIEM-generated behavioral score
      </p>
      <p style={expandedDetailTextStyle}>
        <strong>Reputation Summary:</strong> {event.reputation_summary || "No reputation details available."}
      </p>
      <div style={{ marginBottom: "12px" }}>
        <strong style={expandedSignalsLabelStyle}>Contributing Signals</strong>
        {Array.isArray(event.contributing_signals) && event.contributing_signals.length > 0 ? (
          event.contributing_signals.map((signal) => (
            <div key={signal.signal} style={signalRowStyle}>
              <span>{signal.label}</span>
              <span style={sourceTypeTextStyle}>
                count {signal.count} · weight {signal.weight} · total {signal.total}
              </span>
            </div>
          ))
        ) : (
          <div style={noSignalTextStyle}>No contributing signals</div>
        )}
      </div>
      <p style={expandedDetailTextStyle}>
        <strong>App:</strong> {event.app_name || "Unknown"}{" "}
        <span style={sourceTypeTextStyle}>({event.environment || "Unknown"})</span>
      </p>
      <p style={expandedLabelStyle}>Raw Payload</p>
      <pre style={rawPayloadStyle}>
        {formatRawPayload(event.raw_payload)}
      </pre>
    </>
  );
}

export default ThreatHuntEventDetails;
