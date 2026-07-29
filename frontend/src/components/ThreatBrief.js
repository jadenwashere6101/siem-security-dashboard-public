import React from "react";

import { Card, Chip } from "./uiPrimitives";
import { theme, toneForSeverity, toneForStatus } from "../theme";

const severityRank = { critical: 5, high: 4, medium: 3, low: 2, info: 1 };

export function buildThreatBriefModel({ alerts = [], metrics = null, sourceErrors = [], stale = false } = {}) {
  const normalizedAlerts = Array.isArray(alerts) ? alerts : [];
  const highestPriorityAlert = [...normalizedAlerts].sort(compareAlertPriority)[0] || null;
  const riskiestSource = deriveRiskiestSource(normalizedAlerts);
  const automationFailure = normalizedAlerts.find((alert) =>
    String(alert.status || "").toLowerCase().includes("failed") ||
    String(alert.alert_type || "").toLowerCase().includes("exception")
  ) || null;
  const recommendedNextAction = highestPriorityAlert
    ? `Review ${highestPriorityAlert.alert_type || "the highest-priority alert"} from ${highestPriorityAlert.source_ip || "unknown source"}.`
    : riskiestSource
    ? `Review source ${riskiestSource.sourceIp} across visible alerts.`
    : "";

  return {
    loading: false,
    stale,
    sourceErrors,
    sections: [
      {
        id: "highest-priority",
        label: "Highest priority",
        value: highestPriorityAlert?.alert_type || "No priority alert in view",
        meta: highestPriorityAlert ? [highestPriorityAlert.severity, highestPriorityAlert.source_ip].filter(Boolean).join(" • ") : "Current filtered alerts do not expose a priority item.",
        tone: highestPriorityAlert ? toneForSeverity(highestPriorityAlert.severity) : "neutral",
      },
      {
        id: "riskiest-source",
        label: "Riskiest source IP",
        value: riskiestSource?.sourceIp || "Unavailable",
        meta: riskiestSource ? `${riskiestSource.count} visible alert${riskiestSource.count === 1 ? "" : "s"}` : "No source-IP concentration in visible data.",
        tone: riskiestSource ? "info" : "neutral",
      },
      {
        id: "pending-approvals",
        label: "Pending approvals",
        value: "Unavailable",
        meta: "Open SOC Command Center for authoritative approval state.",
        tone: "warning",
      },
      {
        id: "automation-failures",
        label: "Automation failures",
        value: automationFailure ? automationFailure.alert_type || "Failure signal" : "No visible failure signal",
        meta: automationFailure ? [automationFailure.status, automationFailure.source_ip].filter(Boolean).join(" • ") : "No failure is present in the currently loaded dashboard data.",
        tone: automationFailure ? "danger" : "success",
      },
      {
        id: "active-investigations",
        label: "Active investigations",
        value: metrics?.totalAlerts ? `${metrics.totalAlerts} alerts in current view` : "Unavailable",
        meta: "Use loaded dashboard/SOC data; no new workspace persistence is introduced.",
        tone: metrics?.totalAlerts ? "info" : "neutral",
      },
      {
        id: "recommended-next-action",
        label: "Recommended next action",
        value: recommendedNextAction || "Unavailable",
        meta: recommendedNextAction ? "Deterministic recommendation from currently visible data." : "No recommendation is available without relevant data.",
        tone: recommendedNextAction ? "warning" : "neutral",
      },
    ],
  };
}

function ThreatBrief({ model, loading = false }) {
  if (loading) {
    return (
      <Card style={cardStyle} aria-label="Threat Brief">
        <BriefHeader />
        <p style={emptyStyle}>Loading briefing data...</p>
      </Card>
    );
  }
  const sections = model?.sections || [];
  return (
    <Card style={cardStyle} aria-label="Threat Brief">
      <BriefHeader
        subtitle={model?.stale ? "Showing stale briefing inputs." : "Deterministic summary from currently loaded authoritative data."}
      />
      {model?.sourceErrors?.length ? (
        <p style={warningStyle}>Partial data loaded: {model.sourceErrors.join(", ")}</p>
      ) : null}
      <div style={gridStyle}>
        {sections.map((section) => (
          <div key={section.id} style={itemStyle}>
            <div style={itemHeaderStyle}>
              <span style={labelStyle}>{section.label}</span>
              <Chip tone={section.tone || toneForStatus(section.value)}>{section.tone || "neutral"}</Chip>
            </div>
            <p style={valueStyle}>{section.value}</p>
            <p style={metaStyle}>{section.meta}</p>
          </div>
        ))}
      </div>
    </Card>
  );
}

function BriefHeader({ subtitle = "" }) {
  return (
    <div style={headerStyle}>
      <div style={{ minWidth: 0 }}>
        <p style={eyebrowStyle}>Threat Brief</p>
        <p style={titleStyle}>What requires attention right now?</p>
        {subtitle ? <p style={subtitleStyle}>{subtitle}</p> : null}
      </div>
    </div>
  );
}

function compareAlertPriority(a, b) {
  const severityDelta = (severityRank[String(b.severity || "").toLowerCase()] || 0) -
    (severityRank[String(a.severity || "").toLowerCase()] || 0);
  if (severityDelta !== 0) return severityDelta;
  return new Date(b.timestamp || b.created_at || 0) - new Date(a.timestamp || a.created_at || 0);
}

function deriveRiskiestSource(alerts) {
  const counts = new Map();
  for (const alert of alerts) {
    if (!alert.source_ip) continue;
    counts.set(alert.source_ip, (counts.get(alert.source_ip) || 0) + 1);
  }
  return Array.from(counts.entries())
    .sort((a, b) => b[1] - a[1])
    .map(([sourceIp, count]) => ({ sourceIp, count }))[0] || null;
}

const cardStyle = { marginBottom: theme.spacing.lg };
const headerStyle = {
  padding: `${theme.spacing.xl}px ${theme.spacing.xl}px ${theme.spacing.lg}px`,
  borderBottom: `1px solid ${theme.color.border}`,
};
const eyebrowStyle = {
  margin: "0 0 6px",
  color: theme.color.textMuted,
  ...theme.typography.label,
};
const titleStyle = {
  margin: 0,
  color: theme.color.text,
  fontSize: "20px",
  fontWeight: 800,
  lineHeight: 1.2,
};
const subtitleStyle = { margin: "6px 0 0", color: theme.color.textMuted, fontSize: "13px" };
const gridStyle = { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))", gap: theme.spacing.md, padding: theme.spacing.lg };
const itemStyle = { border: `1px solid ${theme.color.border}`, borderRadius: theme.radius.sm, padding: theme.spacing.md, backgroundColor: theme.color.bg };
const itemHeaderStyle = { display: "flex", justifyContent: "space-between", gap: theme.spacing.sm, alignItems: "center" };
const labelStyle = { color: theme.color.textMuted, fontSize: "11px", fontWeight: 900, textTransform: "uppercase" };
const valueStyle = { margin: "8px 0 4px", color: theme.color.text, fontSize: "15px", fontWeight: 900 };
const metaStyle = { margin: 0, color: theme.color.textMuted, fontSize: "12px", lineHeight: 1.4 };
const emptyStyle = { padding: theme.spacing.lg, color: theme.color.textMuted };
const warningStyle = { margin: `${theme.spacing.md}px ${theme.spacing.lg}px 0`, color: theme.color.reviewSoft, fontSize: "12px", fontWeight: 700 };

export default ThreatBrief;
