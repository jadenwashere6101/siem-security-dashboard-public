import React, { useEffect, useState } from "react";
import AlertTimeline from "./AlertTimeline";
import { ResponseOutcomeSummary } from "./ResponseOutcome";
import SourceIpContext from "./SourceIpContext";
import { getBehavioralReputation, getExternalReputation } from "../utils/alertDisplay";
import { loadPfsenseWhyFired } from "../services/pfsenseAlertInvestigationService";

const PFSENSE_ALERT_TYPES = new Set([
  "pfsense_firewall_repeated_deny",
  "pfsense_firewall_port_scan",
  "pfsense_firewall_suspicious_allow",
  "pfsense_firewall_noisy_source",
]);

const singleTargetFields = [
  ["Destination IP", "destination_ip"],
  ["Destination Port", "destination_port"],
  ["Protocol", "protocol"],
  ["Firewall Action", "firewall_action"],
  ["Attempts", "attempts"],
  ["First Seen", "first_seen"],
  ["Last Seen", "last_seen"],
  ["Interface", "interface"],
  ["Direction", "direction"],
];

const aggregateTargetFields = [
  ["Top Destination IP", "top_destination_ip"],
  ["Top Destination Port", "top_destination_port"],
  ["Distinct Destinations", "distinct_destination_count"],
  ["Distinct Ports", "distinct_port_count"],
  ["Firewall Action", "firewall_action"],
  ["Attempts", "attempts"],
  ["First Seen", "first_seen"],
  ["Last Seen", "last_seen"],
];

function formatTargetContextValue(field, value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  if (field === "direction") {
    return value === "out"
      ? "LAN to WAN (outbound)"
      : value === "in"
        ? "WAN to LAN (inbound)"
        : String(value);
  }
  return String(value);
}

function buildTargetContextRows(targetContext) {
  if (!targetContext || typeof targetContext !== "object") {
    return [];
  }
  const fields =
    targetContext.mode === "aggregate_targets" ? aggregateTargetFields : singleTargetFields;
  return fields
    .map(([label, field]) => ({
      label,
      value: formatTargetContextValue(field, targetContext[field]),
    }))
    .filter((item) => item.value !== null);
}

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
  const [whyFired, setWhyFired] = useState(null);
  const [whyFiredLoading, setWhyFiredLoading] = useState(false);
  const [whyFiredError, setWhyFiredError] = useState("");
  const shouldLoadWhyFired = Boolean(selectedAlert?.pfsense_quality?.why_fired_available);
  const isPfsenseAlert = PFSENSE_ALERT_TYPES.has(selectedAlert?.alert_type);
  const targetContext = selectedAlert?.context?.target_context;
  const targetContextRows = buildTargetContextRows(targetContext);

  useEffect(() => {
    let cancelled = false;

    if (!shouldLoadWhyFired || !selectedAlert?.id) {
      setWhyFired(null);
      setWhyFiredLoading(false);
      setWhyFiredError("");
      return undefined;
    }

    setWhyFiredLoading(true);
    setWhyFiredError("");

    loadPfsenseWhyFired(selectedAlert.id)
      .then((data) => {
        if (!cancelled) {
          setWhyFired(data);
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setWhyFired(null);
          setWhyFiredError(error.message || "Unable to load why this fired");
        }
      })
      .finally(() => {
        if (!cancelled) {
          setWhyFiredLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [selectedAlert?.id, shouldLoadWhyFired]);

  return (
    <div style={{ fontSize: "14px", lineHeight: "1.7", color: "#e6edf3" }}>
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
      {shouldLoadWhyFired ? (
        <div style={whyFiredPanelStyle}>
          <strong>Why this fired</strong>
          {whyFiredLoading ? (
            <div style={whyFiredMutedStyle}>Loading detection evidence...</div>
          ) : whyFiredError ? (
            <div role="alert" style={whyFiredErrorStyle}>{whyFiredError}</div>
          ) : whyFired ? (
            <div style={{ marginTop: "8px" }}>
              <p style={{ margin: "0 0 8px 0" }}>{whyFired.summary}</p>
              {Array.isArray(whyFired.evidence) && whyFired.evidence.length > 0 ? (
                whyFired.evidence.map((item) => (
                  <div key={item.field} style={signalRowStyle}>
                    <span>{item.label}</span>
                    <span style={sourceTypeTextStyle}>{String(item.value)}</span>
                  </div>
                ))
              ) : (
                <div style={whyFiredMutedStyle}>No persisted detection evidence was recorded.</div>
              )}
              {whyFired.cooldown?.active ? (
                <p style={whyFiredNoticeStyle}>
                  Cooldown active until {whyFired.cooldown.cooldown_until}
                </p>
              ) : null}
              {whyFired.suppressed_rollup ? (
                <p style={whyFiredInfoStyle}>
                  This alert represents a suppression roll-up for repeated noisy traffic.
                </p>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}
      {isPfsenseAlert ? (
        <div style={whyFiredPanelStyle}>
          <strong>Target Context</strong>
          <div style={{ marginTop: "8px" }}>
            {targetContextRows.length > 0 ? (
              <>
                <p style={{ margin: "0 0 8px 0", color: "#94a3b8" }}>
                  {targetContext?.mode === "aggregate_targets"
                    ? "Top-target aggregate evidence from the detection window."
                    : "Exact destination evidence captured for this alert."}
                </p>
                {targetContextRows.map((item) => (
                  <div key={item.label} style={signalRowStyle}>
                    <span>{item.label}</span>
                    <span style={sourceTypeTextStyle}>{item.value}</span>
                  </div>
                ))}
              </>
            ) : (
              <div style={whyFiredMutedStyle}>Unavailable</div>
            )}
          </div>
        </div>
      ) : null}
      <div style={{ margin: "14px 0" }}>
        <strong>Response Outcome:</strong>
        <div style={{ marginTop: "8px" }}>
          <ResponseOutcomeSummary
            outcome={selectedAlert.response_outcome || null}
            showRelated
            onOpenRelated={
              typeof onOpenResponseRegistry === "function"
                ? ({ kind, id, outcome }) => {
                    if (kind === "alert" || kind === "incident") {
                      onOpenResponseRegistry({
                        relatedAlertId: kind === "alert" ? id : selectedAlert.id,
                        relatedIncidentId: kind === "incident" ? id : undefined,
                        sourceIp: outcome?.source_ip || selectedAlert.source_ip || undefined,
                      });
                    }
                  }
                : null
            }
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

const whyFiredPanelStyle = {
  margin: "14px 0",
  padding: "12px",
  border: "1px solid #223449",
  borderRadius: "10px",
  backgroundColor: "#0f1720",
};

const whyFiredMutedStyle = {
  marginTop: "8px",
  color: "#94a3b8",
};

const whyFiredErrorStyle = {
  marginTop: "8px",
  color: "#fca5a5",
};

const whyFiredNoticeStyle = {
  margin: "8px 0 0 0",
  color: "#fde68a",
};

const whyFiredInfoStyle = {
  margin: "8px 0 0 0",
  color: "#bfdbfe",
};

export default AlertDetailsPanel;
