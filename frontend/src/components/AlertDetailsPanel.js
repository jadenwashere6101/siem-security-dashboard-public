import React, { useEffect, useState } from "react";
import AlertTimeline from "./AlertTimeline";
import InternetNoiseSummary, { shouldShowInternetNoise } from "./InternetNoiseSummary";
import { ResponseOutcomeSummary } from "./ResponseOutcome";
import SourceIpContext from "./SourceIpContext";
import AiAssistantButton from "./AiAssistantButton";
import { getBehavioralReputation, getExternalReputation } from "../utils/alertDisplay";
import { getOperationalHistoryDescription } from "../utils/operationalHistory";
import { loadPfsenseWhyFired } from "../services/pfsenseAlertInvestigationService";

const PFSENSE_ALERT_TYPES = new Set([
  "pfsense_firewall_repeated_deny",
  "pfsense_firewall_port_scan",
  "pfsense_firewall_suspicious_allow",
  "pfsense_firewall_noisy_source",
  "pfsense_firewall_allow_after_deny",
]);

const singleTargetFields = [
  ["Primary Destination IP", "primary_destination_ip"],
  ["Primary Destination Port", "primary_destination_port"],
  ["Sample Destination IPs", "sample_destination_ips"],
  ["Sample Destination Ports", "sample_destination_ports"],
  ["Distinct Destinations", "distinct_destination_count"],
  ["Distinct Ports", "distinct_port_count"],
  ["Protocol", "protocol"],
  ["Firewall Action", "firewall_action"],
  ["Attempts", "attempts"],
  ["First Seen", "first_seen"],
  ["Last Seen", "last_seen"],
  ["Interface", "interface"],
  ["Direction", "direction"],
  ["Related Events", "related_event_count"],
];

const aggregateTargetFields = [
  ["Primary Destination IP", "primary_destination_ip"],
  ["Primary Destination Port", "primary_destination_port"],
  ["Sample Destination IPs", "sample_destination_ips"],
  ["Sample Destination Ports", "sample_destination_ports"],
  ["Distinct Destinations", "distinct_destination_count"],
  ["Distinct Ports", "distinct_port_count"],
  ["Protocol", "protocol"],
  ["Firewall Action", "firewall_action"],
  ["Attempts", "attempts"],
  ["First Seen", "first_seen"],
  ["Last Seen", "last_seen"],
  ["Interface", "interface"],
  ["Direction", "direction"],
  ["Related Events", "related_event_count"],
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
  if (Array.isArray(value)) {
    return value.join(", ");
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
  onAskAi = null,
  aiEnabled = false,
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
  const reconActivity = selectedAlert?.context?.recon_activity;
  const scanDescription = selectedAlert?.context?.scan_description;
  const investigationValue = selectedAlert?.investigation_value;
  const internetNoise = selectedAlert?.internet_noise;
  const returningAttacker = selectedAlert?.returning_attacker;
  const campaignIntelligence = selectedAlert?.campaign_intelligence;
  const alertStory = selectedAlert?.alert_story;
  const operationalHistoryLabel = selectedAlert?.operational_history?.is_pre_tuning
    ? selectedAlert.operational_history.label || "Pre-Tuning"
    : "";
  const recommendationLabel = investigationValue?.label || alertStory?.headline || "Review";
  const recommendationReasons =
    Array.isArray(investigationValue?.reasons) && investigationValue.reasons.length > 0
      ? investigationValue.reasons
      : [];

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
      {aiEnabled && typeof onAskAi === "function" ? (
        <div style={aiButtonRowStyle}>
          <AiAssistantButton
            onClick={() =>
              onAskAi({
                contextType: "alert",
                action: "explain_alert",
                title: `Alert #${selectedAlert.id}`,
                question: "Explain this alert and the strongest evidence behind it.",
                context: { alert_id: selectedAlert.id, source_ip: selectedAlert.source_ip },
              })
            }
          >
            Explain this alert
          </AiAssistantButton>
          <AiAssistantButton
            onClick={() =>
              onAskAi({
                contextType: "alert",
                action: "recommend_investigation",
                title: `Investigation for alert #${selectedAlert.id}`,
                question: "Recommend read-only investigation next steps for this alert.",
                context: { alert_id: selectedAlert.id, source_ip: selectedAlert.source_ip },
              })
            }
          >
            Recommend investigation
          </AiAssistantButton>
          <AiAssistantButton
            onClick={() =>
              onAskAi({
                contextType: "alert",
                action: "why_important",
                title: `Importance for alert #${selectedAlert.id}`,
                question: "Explain why this alert is important for an analyst.",
                context: { alert_id: selectedAlert.id, source_ip: selectedAlert.source_ip },
              })
            }
          >
            Why is this important?
          </AiAssistantButton>
          <AiAssistantButton
            onClick={() =>
              onAskAi({
                contextType: "detection",
                action: "explain_detection",
                title: `Detection for alert #${selectedAlert.id}`,
                question: "Explain why this detection fired using the available detection evidence.",
                context: { alert_id: selectedAlert.id },
              })
            }
          >
            Explain detection
          </AiAssistantButton>
        </div>
      ) : null}
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
      <div style={whyFiredPanelStyle}>
        <strong>What happened</strong>
        <div style={{ marginTop: "8px" }}>
          <p style={{ margin: "0 0 8px 0" }}>{selectedAlert.message}</p>
          <div style={signalRowStyle}>
            <span>Alert</span>
            <span style={sourceTypeTextStyle}>#{selectedAlert.id} · {selectedAlert.alert_type}</span>
          </div>
          <div style={signalRowStyle}>
            <span>Source IP</span>
            <span style={sourceTypeTextStyle}>{selectedAlert.source_ip}</span>
          </div>
          <div style={signalRowStyle}>
            <span>Status</span>
            <span style={sourceTypeTextStyle}>{selectedAlert.status}</span>
          </div>
          {operationalHistoryLabel ? (
            <div style={signalRowStyle}>
              <span>Operational history</span>
              <span style={sourceTypeTextStyle}>
                {operationalHistoryLabel} · {getOperationalHistoryDescription(selectedAlert)}
              </span>
            </div>
          ) : null}
        </div>
      </div>
      <div style={whyFiredPanelStyle}>
        <strong>Why it matters</strong>
        <div style={{ marginTop: "8px" }}>
          <div style={signalRowStyle}>
            <span>Severity</span>
            <span style={sourceTypeTextStyle}>{selectedAlert.severity}</span>
          </div>
          <div style={signalRowStyle}>
            <span>Investigation Value</span>
            <span style={sourceTypeTextStyle}>{recommendationLabel}</span>
          </div>
          <p style={{ margin: "8px 0", color: "#cbd5e1" }}>
            Severity reflects potential danger. Investigation Value reflects analyst priority.
          </p>
          <p style={{ margin: "0 0 8px 0" }}>
            {alertStory?.headline || recommendationLabel}
            {alertStory?.disposition ? ` · ${alertStory.disposition}` : ""}
          </p>
          {recommendationReasons.length > 0 ? (
            recommendationReasons.map((item) => (
              <div key={item.id} style={signalRowStyle}>
                <span>Evidence</span>
                <span style={sourceTypeTextStyle}>{item.text}</span>
              </div>
            ))
          ) : (
            <div style={whyFiredMutedStyle}>No investigation reasons recorded.</div>
          )}
        </div>
      </div>
      {shouldShowInternetNoise(internetNoise) ? (
        <div style={whyFiredPanelStyle}>
          <InternetNoiseSummary internetNoise={internetNoise} />
        </div>
      ) : null}
      {shouldLoadWhyFired ? (
        <div style={whyFiredPanelStyle}>
          <strong>Primary evidence</strong>
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
          <strong>Target context</strong>
          <div style={{ marginTop: "8px" }}>
            {targetContextRows.length > 0 ? (
              <>
                <p style={{ margin: "0 0 8px 0", color: "#94a3b8" }}>
                  {targetContext?.mode === "aggregate_sample"
                    ? "Bounded aggregate target evidence from the detection window."
                    : "Exact destination evidence captured for this alert."}
                </p>
                {scanDescription ? (
                  <p style={{ margin: "0 0 8px 0", color: "#e2e8f0" }}>{scanDescription}</p>
                ) : null}
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
      {reconActivity ? (
        <div style={whyFiredPanelStyle}>
          <strong>Related objects</strong>
          <div style={{ marginTop: "8px" }}>
            <div style={signalRowStyle}>
              <span>Recon activity</span>
              <span style={sourceTypeTextStyle}>{reconActivity.label}</span>
            </div>
            <div style={signalRowStyle}>
              <span>Activity ID</span>
              <span style={sourceTypeTextStyle}>#{reconActivity.id}</span>
            </div>
            <div style={signalRowStyle}>
              <span>Coordination Status</span>
              <span style={sourceTypeTextStyle}>{String(reconActivity.coordination_status || "not_established").replaceAll("_", " ")}</span>
            </div>
          </div>
        </div>
      ) : null}
      {returningAttacker ? (
        <div style={whyFiredPanelStyle}>
          <strong>Returning attacker context</strong>
          <div style={{ marginTop: "8px" }}>
            <div style={signalRowStyle}>
              <span>Status</span>
              <span style={sourceTypeTextStyle}>{returningAttacker.headline}</span>
            </div>
            <div style={signalRowStyle}>
              <span>First seen</span>
              <span style={sourceTypeTextStyle}>{returningAttacker.first_seen || "Unknown"}</span>
            </div>
            <div style={signalRowStyle}>
              <span>Last seen</span>
              <span style={sourceTypeTextStyle}>{returningAttacker.last_seen || "Unknown"}</span>
            </div>
            {Array.isArray(returningAttacker.reasons)
              ? returningAttacker.reasons.slice(0, 4).map((item) => (
                <div key={item.id} style={signalRowStyle}>
                  <span>Evidence</span>
                  <span style={sourceTypeTextStyle}>{item.text}</span>
                </div>
              ))
              : null}
          </div>
        </div>
      ) : null}
      {campaignIntelligence?.present ? (
        <div style={whyFiredPanelStyle}>
          <strong>Campaign evidence</strong>
          <div style={{ marginTop: "8px" }}>
            <p style={{ margin: "0 0 8px 0" }}>{campaignIntelligence.headline}</p>
            {campaignIntelligence.reasons.map((item) => (
              <div key={item.id} style={signalRowStyle}>
                <span>Evidence</span>
                <span style={sourceTypeTextStyle}>{item.text}</span>
              </div>
            ))}
          </div>
        </div>
      ) : null}
      <div style={{ margin: "14px 0" }}>
        <strong>Investigation recommendation</strong>
        <div style={{ marginTop: "8px", marginBottom: "8px", color: "#cbd5e1" }}>
          {recommendationLabel}
        </div>
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
      <details style={whyFiredPanelStyle}>
        <summary style={{ cursor: "pointer", fontWeight: 600 }}>Secondary technical detail</summary>
        <div style={{ marginTop: "10px" }}>
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
            onAskAi={onAskAi}
            aiEnabled={aiEnabled}
          />
        </div>
      </details>
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

const aiButtonRowStyle = {
  display: "flex",
  flexWrap: "wrap",
  gap: "8px",
  marginBottom: "14px",
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
