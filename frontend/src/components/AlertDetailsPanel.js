import React from "react";
import AlertTimeline from "./AlertTimeline";

function AlertDetailsPanel({
  selectedAlert,
  selectedAlertTimeline,
  getSourceBadgeMeta,
  getTargetedAlertMeta,
  isCorrelationAlert,
  getCorrelationAlertTypes,
  correlationPanelStyle,
  targetedAlertPanelStyle,
  expandedLabelStyle,
  expandedTextStyle,
  monoCellStyle,
  correlationListStyle,
  signalRowStyle,
  sourceTypeTextStyle,
}) {
  return (
    <div style={{ fontSize: "14px", lineHeight: "1.7" }}>
      {getTargetedAlertMeta(selectedAlert.alert_type) && (
        <div
          style={
            isCorrelationAlert(selectedAlert)
              ? correlationPanelStyle
              : targetedAlertPanelStyle
          }
        >
          <p style={{ ...expandedLabelStyle, marginTop: 0 }}>
            {isCorrelationAlert(selectedAlert) ? "Correlation Alert" : "Targeted Correlation Alert"}
          </p>
          <div style={{ marginBottom: "8px" }}>
            <span style={getTargetedAlertMeta(selectedAlert.alert_type).badgeStyle}>
              {getTargetedAlertMeta(selectedAlert.alert_type).badge}
            </span>
          </div>
          <p style={expandedTextStyle}>
            {getTargetedAlertMeta(selectedAlert.alert_type).description}
          </p>
          {isCorrelationAlert(selectedAlert) && getCorrelationAlertTypes(selectedAlert).length > 0 ? (
            <div>
              <strong>Involved Alert Types:</strong>
              <ul style={correlationListStyle}>
                {getCorrelationAlertTypes(selectedAlert).map((alertType) => (
                  <li key={alertType}>
                    <span style={{ ...monoCellStyle, fontSize: "12px" }}>
                      {alertType}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <p><strong>Correlation Message:</strong> {selectedAlert.message}</p>
          )}
        </div>
      )}
      <p><strong>ID:</strong> {selectedAlert.id}</p>
      <p><strong>Type:</strong> {selectedAlert.alert_type}</p>
      <p><strong>Source IP:</strong> {selectedAlert.source_ip}</p>
      <p><strong>Severity:</strong> {selectedAlert.severity}</p>
      <p><strong>Status:</strong> {selectedAlert.status}</p>
      <p><strong>Message:</strong> {selectedAlert.message}</p>
      <p>
        <strong>Location:</strong>{" "}
        {selectedAlert.city && selectedAlert.country
          ? `${selectedAlert.city}, ${selectedAlert.country}`
          : "Unknown"}
      </p>
      <p><strong>Behavioral Reputation:</strong> {selectedAlert.reputation_label || "Normal"} ({selectedAlert.reputation_score ?? 0})</p>
      <p><strong>Score Type:</strong> Internal SIEM-generated behavioral score</p>
      <p><strong>Reputation Summary:</strong> {selectedAlert.reputation_summary || "N/A"}</p>
      <div>
        <strong>Contributing Signals:</strong>
        {Array.isArray(selectedAlert.contributing_signals) && selectedAlert.contributing_signals.length > 0 ? (
          selectedAlert.contributing_signals.map((signal) => (
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
      <AlertTimeline
        selectedAlert={selectedAlert}
        selectedAlertTimeline={selectedAlertTimeline}
        getSourceBadgeMeta={getSourceBadgeMeta}
      />
    </div>
  );
}

export default AlertDetailsPanel;
