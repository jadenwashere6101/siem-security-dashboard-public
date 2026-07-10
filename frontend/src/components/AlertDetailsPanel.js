import React from "react";
import AlertTimeline from "./AlertTimeline";
import { ResponseOutcomeSummary } from "./ResponseOutcome";
import SourceIpContext from "./SourceIpContext";
import { getBehavioralReputation, getExternalReputation } from "../utils/alertDisplay";

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
  onOpenResponseRegistry = null,
}) {
  const externalReputation = getExternalReputation(selectedAlert);
  const behavioralReputation = getBehavioralReputation(selectedAlert);
  const contributingSignals = behavioralReputation.contributing_signals;

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
      <div style={{ margin: "14px 0" }}>
        <strong>Response Outcome:</strong>
        <div style={{ marginTop: "8px" }}>
          <ResponseOutcomeSummary
            outcome={selectedAlert.response_outcome || null}
            showRelated
          />
        </div>
      </div>
      <p>
        <strong>Location:</strong>{" "}
        {selectedAlert.city && selectedAlert.country
          ? `${selectedAlert.city}, ${selectedAlert.country}`
          : "Unknown"}
      </p>
      <p>
        <strong>External Threat Intelligence Reputation:</strong>{" "}
        {externalReputation.label} ({externalReputation.score ?? "n/a"})
      </p>
      <p><strong>Threat Intel Source:</strong> {externalReputation.source}</p>
      <p><strong>Threat Intel Summary:</strong> {externalReputation.summary}</p>
      <p>
        <strong>Behavioral Reputation:</strong>{" "}
        {behavioralReputation.label} ({behavioralReputation.score})
      </p>
      <p><strong>Score Type:</strong> Internal SIEM-generated behavioral score</p>
      <p><strong>Behavioral Summary:</strong> {behavioralReputation.summary}</p>
      <div>
        <strong>Behavioral Contributing Signals:</strong>
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
      <AlertTimeline
        selectedAlert={selectedAlert}
        selectedAlertTimeline={selectedAlertTimeline}
        getSourceBadgeMeta={getSourceBadgeMeta}
      />
      <SourceIpContext
        sourceIp={selectedAlert.source_ip}
        onOpenResponseRegistry={onOpenResponseRegistry}
      />
    </div>
  );
}

export default AlertDetailsPanel;
