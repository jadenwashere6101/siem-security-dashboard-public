import React, { useEffect, useMemo, useState } from "react";

import InternetNoiseSummary, { shouldShowInternetNoise } from "./InternetNoiseSummary";
import { loadSourceIpContext } from "../services/sourceIpContextService";
import { CanonicalOutcomeBreakdown, ResponseOutcomeBadge, ResponseOutcomeSummary } from "./ResponseOutcome";
import ResponseStateSummary from "./ResponseStateSummary";
import { outcomeLabel } from "../utils/responseOutcomeDisplay";
import { registryNavFromSourceIp } from "../utils/responseNavigation";

function SourceIpContext({ sourceIp, compact = false, onOpenResponseRegistry = null }) {
  const [context, setContext] = useState(null);
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState(null);

  useEffect(() => {
    const normalizedSourceIp = String(sourceIp || "").trim();
    let isMounted = true;

    if (!normalizedSourceIp) {
      setContext(null);
      setStatus("empty");
      setError(null);
      return () => {
        isMounted = false;
      };
    }

    setStatus("loading");
    setError(null);

    loadSourceIpContext(normalizedSourceIp)
      .then((data) => {
        if (!isMounted) return;
        setContext(data);
        setStatus("ready");
      })
      .catch((err) => {
        if (!isMounted) return;
        setContext(null);
        setError(err);
        setStatus(err?.status === 403 ? "forbidden" : "error");
      });

    return () => {
      isMounted = false;
    };
  }, [sourceIp]);

  const hasAnyContext = useMemo(() => {
    if (!context) return false;
    return Boolean(
      context.alerts?.recent?.length ||
        context.incidents?.recent?.length ||
        context.queue?.recent?.length ||
        context.blocklist?.entries?.length ||
        context.reputation?.latest_external ||
        context.reputation?.external_snapshots?.length ||
        shouldShowInternetNoise(context.internet_noise) ||
        context.playbook_executions?.recent?.length ||
        context.returning_attacker ||
        context.campaigns?.recent?.length ||
        context.reputation?.behavioral ||
        context.response_outcomes?.length ||
        context.response_outcome_counts
    );
  }, [context]);

  const recentOutcomes = Array.isArray(context?.response_outcomes) ? context.response_outcomes : [];
  const latestOutcome = recentOutcomes[0] || null;

  if (status === "empty") {
    return (
      <section style={panelStyle} data-testid="source-ip-context">
        <PanelHeader sourceIp={sourceIp} compact={compact} />
        <p style={mutedTextStyle}>No source IP selected.</p>
      </section>
    );
  }

  if (status === "loading") {
    return (
      <section style={panelStyle} data-testid="source-ip-context">
        <PanelHeader sourceIp={sourceIp} compact={compact} />
        <p style={mutedTextStyle}>Loading source-IP context...</p>
      </section>
    );
  }

  if (status === "forbidden") {
    return (
      <section style={panelStyle} data-testid="source-ip-context">
        <PanelHeader sourceIp={sourceIp} compact={compact} />
        <p style={noticeTextStyle}>Source-IP context unavailable for this role.</p>
      </section>
    );
  }

  if (status === "error") {
    return (
      <section style={panelStyle} data-testid="source-ip-context">
        <PanelHeader sourceIp={sourceIp} compact={compact} />
        <p style={errorTextStyle}>{error?.message || "Unable to load source-IP context."}</p>
      </section>
    );
  }

  if (!context) {
    return null;
  }

  return (
    <section style={panelStyle} data-testid="source-ip-context">
      <PanelHeader sourceIp={context.source_ip || sourceIp} compact={compact} />
      <ResponseStateSummary
        lastAction={latestOutcome ? outcomeLabel(latestOutcome) : null}
        compact={compact}
        onOpenRegistry={
          typeof onOpenResponseRegistry === "function"
            ? () =>
                onOpenResponseRegistry(
                  registryNavFromSourceIp(context.source_ip || sourceIp)
                )
            : null
        }
      />
      {!hasAnyContext ? (
        <p style={mutedTextStyle}>No source-IP context found.</p>
      ) : (
        <div style={sectionGridStyle}>
          <ContextSection title="Canonical Outcomes">
            {recentOutcomes.length === 0 ? (
              <p style={mutedTextStyle}>No canonical response outcomes recorded for this source IP.</p>
            ) : (
              <>
                <div style={outcomeHeaderStyle}>
                  <ResponseOutcomeBadge outcome={latestOutcome} />
                </div>
                <ResponseOutcomeSummary outcome={latestOutcome} />
                {recentOutcomes.length > 1 ? (
                  <div style={outcomeListStyle}>
                    <p style={outcomeListTitleStyle}>Recent canonical outcomes</p>
                    {recentOutcomes.slice(0, 5).map((outcome, index) => (
                      <div
                        key={`${outcome.latest_outcome_event_id || outcome.soar_correlation_id || index}`}
                        style={outcomeListItemStyle}
                      >
                        <ResponseOutcomeBadge outcome={outcome} />
                        <span style={outcomeSummaryStyle}>
                          {outcome.outcome_summary || outcomeLabel(outcome)}
                        </span>
                      </div>
                    ))}
                  </div>
                ) : null}
              </>
            )}
            <CanonicalOutcomeBreakdown
              counts={context.response_outcome_counts}
              title="Outcome counts for this source IP"
            />
          </ContextSection>

          <ContextSection title="Returning Attacker">
            <SummaryLine
              label="Current assessment"
              value={context.returning_attacker?.headline || "No prior history"}
            />
            <SummaryLine
              label="Days observed"
              value={context.returning_attacker?.days_observed ?? 0}
            />
            <SummaryLine
              label="Previous incidents"
              value={context.returning_attacker?.previous_incidents ?? 0}
            />
            <SummaryLine
              label="Previous responses"
              value={context.returning_attacker?.previous_responses ?? 0}
            />
            <RecordList
              records={context.returning_attacker?.reasons}
              emptyText="No returning-attacker evidence"
              renderRecord={(reason) => (
                <>
                  <span style={recordTitleStyle}>{reason.text}</span>
                </>
              )}
            />
          </ContextSection>

          <ContextSection title="Campaigns">
            <SummaryLine label="Recent campaigns" value={context.campaigns?.count ?? 0} />
            <RecordList
              records={context.campaigns?.recent}
              emptyText="No recent campaign memberships"
              renderRecord={(campaign) => (
                <>
                  <span style={recordTitleStyle}>{campaign.label}</span>
                  <span style={recordMetaStyle}>
                    {campaign.campaign_intelligence?.summary || "No campaign summary"}
                  </span>
                  <span style={recordMetaStyle}>
                    {campaign.related_incident_id
                      ? `Related incident: ${campaign.related_incident_id}`
                      : "No active incident"}
                  </span>
                </>
              )}
            />
          </ContextSection>

          <ContextSection title="Alerts">
            <SummaryLine label="Total alerts" value={context.alerts?.counts?.total ?? 0} />
            <SummaryLine label="Open alerts" value={context.alerts?.counts?.open ?? 0} />
            <SummaryLine label="Resolved alerts" value={context.alerts?.counts?.resolved ?? 0} />
            <RecordList
              records={context.alerts?.recent}
              emptyText="No recent alerts"
              renderRecord={(alert) => (
                <>
                  <span style={recordTitleStyle}>{alert.alert_type || `Alert ${alert.id}`}</span>
                  <span style={recordMetaStyle}>Alert status: {alert.status || "unknown"}</span>
                  <span style={recordMetaStyle}>Severity: {alert.severity || "unknown"}</span>
                  <span style={recordMetaStyle}>
                    Legacy response status (non-authoritative):{" "}
                    {alert.response_status || "not set"}
                  </span>
                </>
              )}
            />
          </ContextSection>

          <ContextSection title="Incidents">
            <SummaryLine label="Recent incidents" value={context.incidents?.count ?? 0} />
            <RecordList
              records={context.incidents?.recent}
              emptyText="No linked incidents"
              renderRecord={(incident) => (
                <>
                  <span style={recordTitleStyle}>{incident.title || `Incident ${incident.id}`}</span>
                  <span style={recordMetaStyle}>Incident status: {incident.status || "unknown"}</span>
                  <span style={recordMetaStyle}>Severity: {incident.severity || "unknown"}</span>
                </>
              )}
            />
          </ContextSection>

          <ContextSection title="SOAR Queue">
            <SummaryLine label="Queue rows" value={context.queue?.counts?.total ?? 0} />
            <RecordList
              records={context.queue?.recent}
              emptyText="No recent queue activity"
              renderRecord={(queueRow) => (
                <>
                  <span style={recordTitleStyle}>{queueRow.action || `Queue ${queueRow.id}`}</span>
                  <span style={recordMetaStyle}>Queue execution status: {queueRow.status || "unknown"}</span>
                  <span style={recordMetaStyle}>Alert ID: {queueRow.alert_id ?? "none"}</span>
                </>
              )}
            />
          </ContextSection>

          <ContextSection title="Blocklist">
            <SummaryLine
              label="Blocklist effective status"
              value={context.blocklist?.effective_status || "none"}
            />
            <RecordList
              records={context.blocklist?.entries}
              emptyText="No blocklist entries"
              renderRecord={(entry) => (
                <>
                  <span style={recordTitleStyle}>{entry.ip_address || context.source_ip}</span>
                  <span style={recordMetaStyle}>Blocklist effective status: {entry.effective_status || "none"}</span>
                  <span style={recordMetaStyle}>Stored status: {entry.raw_status || entry.status || "none"}</span>
                </>
              )}
            />
          </ContextSection>

          <ContextSection title="Reputation">
            <SummaryLine
              label="Behavioral reputation"
              value={`${context.reputation?.behavioral?.label || "Normal"} (${context.reputation?.behavioral?.score ?? 0})`}
            />
            <p style={mutedTextStyle}>
              {context.reputation?.behavioral?.summary ||
                "No elevated behavioral signals observed in SIEM history."}
            </p>
            <SummaryLine
              label="Latest external reputation"
              value={
                context.reputation?.latest_external
                  ? `${context.reputation.latest_external.label || "unlabeled"} (${context.reputation.latest_external.score ?? "n/a"})`
                  : "No snapshots"
              }
            />
            <RecordList
              records={context.reputation?.external_snapshots}
              emptyText="No external reputation snapshots"
              renderRecord={(snapshot) => (
                <>
                  <span style={recordTitleStyle}>{snapshot.source || "external snapshot"}</span>
                  <span style={recordMetaStyle}>{snapshot.label || "unlabeled"} ({snapshot.score ?? "n/a"})</span>
                  <span style={recordMetaStyle}>Alert ID: {snapshot.alert_id}</span>
                </>
              )}
            />
          </ContextSection>

          {shouldShowInternetNoise(context.internet_noise) ? (
            <ContextSection title="Internet Noise">
              <InternetNoiseSummary internetNoise={context.internet_noise} compact />
            </ContextSection>
          ) : null}

          <ContextSection title="Playbook Executions">
            <SummaryLine label="Recent executions" value={context.playbook_executions?.count ?? 0} />
            <RecordList
              records={context.playbook_executions?.recent}
              emptyText="No linked playbook executions"
              renderRecord={(execution) => (
                <>
                  <span style={recordTitleStyle}>{execution.playbook_id || `Execution ${execution.id}`}</span>
                  <span style={recordMetaStyle}>Execution status: {execution.status || "unknown"}</span>
                  <span style={recordMetaStyle}>Alert ID: {execution.alert_id ?? "none"}</span>
                </>
              )}
            />
          </ContextSection>
        </div>
      )}
    </section>
  );
}

function PanelHeader({ sourceIp, compact }) {
  return (
    <div style={headerStyle}>
      <div>
        <h3 style={titleStyle}>Source-IP Context</h3>
        {!compact && (
          <p style={subtitleStyle}>Recent history, campaign context, and response activity for this source IP</p>
        )}
      </div>
      <span style={ipPillStyle}>{sourceIp || "none"}</span>
    </div>
  );
}

function ContextSection({ title, children }) {
  return (
    <div style={sectionStyle}>
      <h4 style={sectionTitleStyle}>{title}</h4>
      {children}
    </div>
  );
}

function SummaryLine({ label, value }) {
  return (
    <div style={summaryLineStyle}>
      <span style={summaryLabelStyle}>{label}</span>
      <span style={summaryValueStyle}>{value}</span>
    </div>
  );
}

function RecordList({ records, emptyText, renderRecord }) {
  if (!Array.isArray(records) || records.length === 0) {
    return <p style={mutedTextStyle}>{emptyText}</p>;
  }

  return (
    <div style={recordListStyle}>
      {records.slice(0, 3).map((record, index) => (
        <div key={record.id || record.alert_id || `${record.playbook_id || "record"}-${index}`} style={recordStyle}>
          {renderRecord(record)}
        </div>
      ))}
    </div>
  );
}

const panelStyle = {
  marginTop: "18px",
  padding: "14px",
  backgroundColor: "#0f172a",
  border: "1px solid #334155",
  borderRadius: "8px",
  color: "#e5e7eb",
};

const headerStyle = {
  display: "flex",
  alignItems: "flex-start",
  justifyContent: "space-between",
  gap: "12px",
  marginBottom: "12px",
};

const titleStyle = {
  margin: 0,
  fontSize: "15px",
  lineHeight: 1.3,
};

const subtitleStyle = {
  margin: "2px 0 0",
  color: "#94a3b8",
  fontSize: "12px",
};

const ipPillStyle = {
  flex: "0 0 auto",
  padding: "3px 7px",
  border: "1px solid #475569",
  borderRadius: "999px",
  color: "#bfdbfe",
  fontFamily: "monospace",
  fontSize: "12px",
};

const sectionGridStyle = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
  gap: "10px",
};

const sectionStyle = {
  padding: "10px",
  backgroundColor: "#111827",
  border: "1px solid #1f2937",
  borderRadius: "8px",
};

const sectionTitleStyle = {
  margin: "0 0 8px",
  fontSize: "13px",
  color: "#f8fafc",
};

const summaryLineStyle = {
  display: "flex",
  justifyContent: "space-between",
  gap: "10px",
  marginBottom: "5px",
  fontSize: "12px",
};

const summaryLabelStyle = {
  color: "#94a3b8",
};

const summaryValueStyle = {
  color: "#e5e7eb",
  fontWeight: 700,
  textAlign: "right",
};

const recordListStyle = {
  display: "grid",
  gap: "6px",
  marginTop: "8px",
};

const recordStyle = {
  display: "grid",
  gap: "2px",
  padding: "7px",
  backgroundColor: "#0b1220",
  border: "1px solid #1e293b",
  borderRadius: "6px",
};

const recordTitleStyle = {
  fontSize: "12px",
  color: "#f8fafc",
  fontWeight: 700,
};

const recordMetaStyle = {
  fontSize: "11px",
  color: "#cbd5e1",
};

const mutedTextStyle = {
  margin: "6px 0",
  color: "#94a3b8",
  fontSize: "12px",
};

const noticeTextStyle = {
  margin: "6px 0",
  color: "#fde68a",
  fontSize: "12px",
};

const errorTextStyle = {
  margin: "6px 0",
  color: "#fecaca",
  fontSize: "12px",
};

const outcomeHeaderStyle = {
  marginBottom: "10px",
};

const outcomeListStyle = {
  display: "grid",
  gap: "8px",
  marginTop: "12px",
};

const outcomeListTitleStyle = {
  margin: "0 0 6px 0",
  color: "#cbd5e1",
  fontSize: "12px",
  fontWeight: "700",
};

const outcomeListItemStyle = {
  display: "grid",
  gap: "6px",
  padding: "8px",
  border: "1px solid #1e293b",
  borderRadius: "6px",
  backgroundColor: "#0b1220",
};

const outcomeSummaryStyle = {
  color: "#cbd5e1",
  fontSize: "11px",
  lineHeight: 1.4,
};

export default SourceIpContext;
