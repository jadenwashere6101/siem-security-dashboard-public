import React, { useMemo } from "react";
import ExecutionSafetyModelPanel from "./ExecutionSafetyModelPanel";

// spec: SPEC-UI-004 - timeline labels clarify simulation-safe execution without downplaying real workflows.
const STATUS_TONES = {
  pending: "info",
  running: "info",
  success: "success",
  failed: "danger",
  skipped: "muted",
  awaiting_approval: "warning",
  recovered: "success",
  retried: "warning",
  abandoned: "muted",
  aborted: "danger",
  unknown: "muted",
};

const TERMINAL_STATUSES = new Set(["success", "failed", "skipped", "abandoned", "aborted"]);
const ACTIVE_STATUSES = new Set(["running", "awaiting_approval", "pending"]);
const SECRET_KEY_PATTERN =
  /(token|secret|password|authorization|auth_header|cookie|bearer|api[_-]?key|webhook|payload|raw_response|raw_payload|smtp)/i;
const URL_PATTERN = /https?:\/\/[^\s"'<>]+/gi;
const MAX_MESSAGE_LENGTH = 220;

function titleCase(value) {
  return String(value || "unknown")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatValue(value, fallback = "Unavailable") {
  if (value === undefined || value === null || value === "") {
    return fallback;
  }
  return String(value);
}

function parseDate(value) {
  if (!value) return null;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function formatTimestamp(value) {
  const parsed = parseDate(value);
  if (!parsed) return "Unavailable";
  return parsed.toLocaleString();
}

function formatDuration(startedAt, completedAt, explicitDuration) {
  if (explicitDuration !== undefined && explicitDuration !== null && explicitDuration !== "") {
    return `${explicitDuration} ms`;
  }
  const start = parseDate(startedAt);
  const end = parseDate(completedAt);
  if (!start || !end) return "Unavailable";
  const diffMs = Math.max(0, end.getTime() - start.getTime());
  if (diffMs < 1000) return `${diffMs} ms`;
  return `${(diffMs / 1000).toFixed(diffMs < 10000 ? 1 : 0)} sec`;
}

function truncate(value) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (text.length <= MAX_MESSAGE_LENGTH) return text;
  return `${text.slice(0, MAX_MESSAGE_LENGTH - 1)}...`;
}

export function sanitizeTimelineText(value) {
  if (value === undefined || value === null || value === "") {
    return "";
  }
  if (typeof value === "object") {
    if (typeof value.message === "string") {
      return sanitizeTimelineText(value.message);
    }
    if (typeof value.error === "string") {
      return sanitizeTimelineText(value.error);
    }
    return "";
  }
  const redacted = String(value)
    .replace(URL_PATTERN, "[REDACTED_URL]")
    .replace(/bearer\s+[a-z0-9._~+/=-]+/gi, "Bearer [REDACTED]")
    .replace(/(token|password|secret|api[_-]?key)\s*[:=]\s*["']?[^"',\s}]+/gi, "$1=[REDACTED]");
  return truncate(redacted);
}

export function parseStepsLog(stepsLog) {
  if (Array.isArray(stepsLog)) {
    return { steps: stepsLog, malformed: false };
  }
  if (typeof stepsLog === "string" && stepsLog.trim()) {
    try {
      const parsed = JSON.parse(stepsLog);
      return Array.isArray(parsed)
        ? { steps: parsed, malformed: false }
        : { steps: [], malformed: true };
    } catch (err) {
      return { steps: [], malformed: true };
    }
  }
  if (stepsLog && typeof stepsLog === "object") {
    return { steps: [], malformed: true };
  }
  return { steps: [], malformed: false };
}

function getNested(step, key) {
  if (!step || typeof step !== "object") return undefined;
  if (step[key] !== undefined) return step[key];
  if (step.output && typeof step.output === "object" && step.output[key] !== undefined) {
    return step.output[key];
  }
  if (step.result && typeof step.result === "object" && step.result[key] !== undefined) {
    return step.result[key];
  }
  return undefined;
}

function getStepStatus(step) {
  const event = String(step?.event || "").toLowerCase();
  const status = String(step?.status || getNested(step, "status") || "").toLowerCase();
  if (event === "approval_requested" && getNested(step, "approval_status") === "pending") {
    return "awaiting_approval";
  }
  if (event === "approval_resumed") return "recovered";
  if (event === "retry" || event === "retried" || step?.retry === true) return "retried";
  if (status === "aborted") return "aborted";
  if (status) return status;
  return "unknown";
}

function getEventLabel(step, status) {
  switch (step?.event) {
    case "approval_requested":
      return "Approval requested";
    case "approval_approved":
      return "Approval approved";
    case "approval_resumed":
      return "Simulation resumed";
    case "approval_denied":
      return "Approval denied";
    case "approval_expired":
      return "Approval expired";
    case "skipped_after_approval_gate":
      return "Skipped after approval gate";
    default:
      return titleCase(status);
  }
}

function getStepIndex(step, fallbackIndex) {
  const raw = step?.step_index ?? step?.index ?? step?.order ?? fallbackIndex;
  const numeric = Number(raw);
  return Number.isFinite(numeric) ? numeric : fallbackIndex;
}

function getStepAction(step) {
  return (
    step?.action ||
    step?.step_action ||
    step?.action_type ||
    step?.step?.action ||
    step?.name ||
    "unspecified"
  );
}

function getSafeMessage(step) {
  const candidates = [
    step?.failure_message,
    step?.message,
    step?.summary,
    step?.error,
    step?.result?.message,
    step?.output?.message,
    step?.output?.adapter_result?.message,
  ];
  for (const candidate of candidates) {
    const safe = sanitizeTimelineText(candidate);
    if (safe) return safe;
  }
  return "";
}

function getFailureClass(step) {
  return (
    step?.failure_class ||
    step?.failure_code ||
    step?.error_code ||
    step?.error?.code ||
    step?.output?.failure_class ||
    ""
  );
}

function getRetryCount(step) {
  const raw =
    step?.retry_count ??
    step?.attempt ??
    step?.attempt_number ??
    step?.output?.retry_count ??
    step?.result?.retry_count;
  const numeric = Number(raw);
  if (!Number.isFinite(numeric) || numeric <= 0) return 0;
  return numeric;
}

function hasRecoveryMarker(step, execution) {
  return Boolean(
    step?.recovered ||
      step?.recovery ||
      step?.event === "approval_resumed" ||
      execution?.recovery_count ||
      execution?.last_recovered_at
  );
}

function hasLeaseMarker(execution) {
  return Boolean(
    execution?.lease_owner ||
      execution?.lease_acquired_at ||
      execution?.lease_heartbeat_at ||
      execution?.lease_expires_at
  );
}

function safeMetadataEntries(step) {
  const metadata =
    step?.metadata ||
    step?.safe_metadata ||
    step?.output?.safe_metadata ||
    step?.output?.adapter_result?.metadata;
  if (!metadata || typeof metadata !== "object" || Array.isArray(metadata)) {
    return [];
  }
  return Object.entries(metadata)
    .filter(([key]) => !SECRET_KEY_PATTERN.test(key))
    .slice(0, 6)
    .map(([key, value]) => [key, sanitizeTimelineText(value) || formatValue(value)]);
}

export function normalizeExecutionTimeline(execution = {}) {
  const parsed = parseStepsLog(execution?.steps_log);
  const steps = parsed.steps
    .filter((step) => step && typeof step === "object" && !Array.isArray(step))
    .map((step, index) => {
      const status = getStepStatus(step);
      const stepIndex = getStepIndex(step, index);
      const retryCount = getRetryCount(step);
      const action = getStepAction(step);
      const mode =
        step.mode ||
        step.execution_mode ||
        step.output?.adapter_result?.mode ||
        execution.mode ||
        execution.execution_mode ||
        "simulation";
      const adapterResult =
        step.output && typeof step.output === "object" ? step.output.adapter_result : null;
      const startedAt = step.started_at || step.start_time || step.timestamp || step.created_at;
      const completedAt = step.completed_at || step.end_time || step.finished_at;
      return {
        id: step.step_id || `${stepIndex}-${action}-${index}`,
        order: stepIndex,
        label: step.label || step.step_name || `Step ${stepIndex + 1}`,
        action,
        status,
        eventLabel: getEventLabel(step, status),
        tone: STATUS_TONES[status] || "muted",
        mode,
        startedAt,
        completedAt,
        duration: formatDuration(startedAt, completedAt, step.duration_ms ?? step.duration),
        message: getSafeMessage(step),
        failureClass: getFailureClass(step),
        adapterName:
          adapterResult && typeof adapterResult === "object"
            ? sanitizeTimelineText(adapterResult.adapter)
            : "",
        adapterAction:
          adapterResult && typeof adapterResult === "object"
            ? sanitizeTimelineText(adapterResult.action)
            : "",
        adapterSuccess:
          adapterResult && typeof adapterResult === "object"
            ? adapterResult.success
            : undefined,
        retryCount,
        approvalRequestId: getNested(step, "approval_request_id"),
        approvalStatus: getNested(step, "approval_status"),
        riskLevel: getNested(step, "risk_level"),
        skipReason: sanitizeTimelineText(getNested(step, "skip_reason") || step.reason),
        isApproval:
          step.event?.startsWith("approval_") ||
          action === "require_approval" ||
          status === "awaiting_approval",
        isRetry: retryCount > 0 || status === "retried",
        isRecovery: hasRecoveryMarker(step, execution),
        isTerminal: TERMINAL_STATUSES.has(status),
        metadata: safeMetadataEntries(step),
      };
    })
    .sort((a, b) => a.order - b.order);

  const activeStepIndex = steps.findIndex((step) => ACTIVE_STATUSES.has(step.status));
  const terminalStepIndex =
    activeStepIndex >= 0
      ? -1
      : [...steps].reverse().findIndex((step) => step.isTerminal);
  const terminalActualIndex =
    terminalStepIndex >= 0 ? steps.length - 1 - terminalStepIndex : -1;

  const summary = steps.reduce(
    (acc, step) => {
      acc.total += 1;
      acc[step.status] = (acc[step.status] || 0) + 1;
      if (step.isRetry) acc.retries += 1;
      if (step.isApproval) acc.approvals += 1;
      if (step.isRecovery) acc.recoveries += 1;
      return acc;
    },
    { total: 0, retries: 0, approvals: 0, recoveries: 0 }
  );

  return {
    steps,
    malformed: parsed.malformed,
    summary,
    activeStepIndex,
    terminalStepIndex: terminalActualIndex,
    hasLease: hasLeaseMarker(execution),
    executionMode: execution.mode || execution.execution_mode || "simulation",
  };
}

function Badge({ tone = "muted", children }) {
  return <span style={{ ...badgeStyle, ...badgeToneStyles[tone] }}>{children}</span>;
}

function Metric({ label, value }) {
  return (
    <div style={metricStyle}>
      <span style={metricLabelStyle}>{label}</span>
      <strong style={metricValueStyle}>{value}</strong>
    </div>
  );
}

function PlaybookExecutionTimeline({ execution, compact = false }) {
  const timeline = useMemo(() => normalizeExecutionTimeline(execution || {}), [execution]);
  const { steps, summary } = timeline;

  if (!execution) {
    return (
      <section style={panelStyle} aria-label="Playbook execution visualization">
        <p style={emptyTextStyle}>Select an execution to view the timeline.</p>
      </section>
    );
  }

  return (
    <section
      style={compact ? compactPanelStyle : panelStyle}
      aria-label="Playbook execution visualization"
    >
      <div style={headerStyle}>
        <div>
          <p style={eyebrowStyle}>Execution Visualization</p>
          <h4 style={titleStyle}>
            {formatValue(execution.playbook_id, "Unknown playbook")} #{formatValue(execution.id, "unknown")}
          </h4>
        </div>
        <div style={badgeRowStyle}>
          <Badge tone={STATUS_TONES[execution.status] || "muted"}>
            {titleCase(execution.status)}
          </Badge>
          <Badge tone={String(timeline.executionMode).toLowerCase() === "real" ? "warning" : "info"}>
            {String(timeline.executionMode).toLowerCase() === "real"
              ? "Guarded Real-Capable"
              : "Simulation-Safe Execution"}
          </Badge>
        </div>
      </div>

      {!compact ? <ExecutionSafetyModelPanel compact /> : null}

      {timeline.malformed ? (
        <div style={warningStyle}>steps_log is malformed or unsupported; rendering safe fallback metadata only.</div>
      ) : null}

      {timeline.hasLease || summary.recoveries > 0 ? (
        <div style={markerBarStyle}>
          {timeline.hasLease ? <Badge tone="info">Lease tracked</Badge> : null}
          {summary.recoveries > 0 || execution.recovery_count ? (
            <Badge tone="success">Recovery metadata</Badge>
          ) : null}
          {execution.recovery_count ? (
            <span style={markerTextStyle}>Recovery count {execution.recovery_count}</span>
          ) : null}
        </div>
      ) : null}

      <div style={metricsGridStyle}>
        <Metric label="Steps" value={summary.total} />
        <Metric label="Succeeded" value={summary.success || 0} />
        <Metric label="Failed" value={summary.failed || 0} />
        <Metric label="Skipped" value={summary.skipped || 0} />
        <Metric label="Approvals" value={summary.approvals || 0} />
        <Metric label="Retries" value={summary.retries || 0} />
      </div>

      {steps.length === 0 ? (
        <p style={emptyTextStyle}>
          {timeline.malformed
            ? "No safe step events could be parsed."
            : "No step events are available for this execution yet."}
        </p>
      ) : (
        <>
          <div style={flowStyle} aria-label="Execution step flow">
            {steps.map((step, index) => {
              const isCurrent = index === timeline.activeStepIndex;
              const isTerminal = index === timeline.terminalStepIndex;
              return (
                <div
                  key={step.id}
                  style={{
                    ...flowNodeStyle,
                    ...(isCurrent ? flowNodeCurrentStyle : {}),
                    ...(isTerminal ? flowNodeTerminalStyle : {}),
                  }}
                  aria-label={`${step.label}: ${step.eventLabel}`}
                >
                  <span style={{ ...flowDotStyle, ...flowDotToneStyles[step.tone] }} />
                  <span style={flowLabelStyle}>{step.label}</span>
                  <span style={flowActionStyle}>{step.action}</span>
                  <Badge tone={step.tone}>{step.eventLabel}</Badge>
                  {step.isApproval ? <span style={flowMarkerStyle}>Approval</span> : null}
                  {step.isRetry ? <span style={flowMarkerStyle}>Retry</span> : null}
                  {step.isRecovery ? <span style={flowMarkerStyle}>Recovery</span> : null}
                </div>
              );
            })}
          </div>

          {!compact ? (
            <div style={timelineListStyle} aria-label="Execution step timeline">
              {steps.map((step, index) => (
                <div
                  key={`${step.id}-timeline`}
                  style={{
                    ...timelineCardStyle,
                    ...(index === timeline.activeStepIndex ? timelineCardCurrentStyle : {}),
                  }}
                >
                  <div style={timelineCardHeaderStyle}>
                    <div>
                      <p style={stepTitleStyle}>{step.label}</p>
                      <p style={actionStyle}>{step.action}</p>
                    </div>
                    <div style={badgeRowStyle}>
                      <Badge tone={step.tone}>{step.eventLabel}</Badge>
                      <Badge tone={String(step.mode).toLowerCase() === "real" ? "warning" : "info"}>
                        {String(step.mode).toLowerCase() === "real" ? "Real" : "Simulation"}
                      </Badge>
                    </div>
                  </div>

                  <div style={metaGridStyle}>
                    <Field label="Started" value={formatTimestamp(step.startedAt)} />
                    <Field label="Completed" value={formatTimestamp(step.completedAt)} />
                    <Field label="Duration" value={step.duration} />
                    {step.retryCount > 0 ? <Field label="Retry count" value={step.retryCount} /> : null}
                    {step.approvalRequestId ? (
                      <Field label="Approval request" value={step.approvalRequestId} />
                    ) : null}
                    {step.approvalStatus ? <Field label="Approval status" value={step.approvalStatus} /> : null}
                    {step.riskLevel ? <Field label="Risk level" value={step.riskLevel} /> : null}
                    {step.failureClass ? <Field label="Failure class" value={step.failureClass} /> : null}
                    {step.adapterName ? <Field label="Adapter" value={step.adapterName} /> : null}
                    {step.adapterAction ? <Field label="Adapter action" value={step.adapterAction} /> : null}
                    {step.adapterSuccess !== undefined ? (
                      <Field label="Adapter success" value={step.adapterSuccess ? "Yes" : "No"} />
                    ) : null}
                    {step.skipReason ? <Field label="Skip reason" value={step.skipReason} /> : null}
                  </div>

                  {step.message ? <p style={messageStyle}>{step.message}</p> : null}
                  {step.metadata.length > 0 ? (
                    <div style={metadataStyle}>
                      <p style={metadataTitleStyle}>Safe metadata</p>
                      <div style={metaGridStyle}>
                        {step.metadata.map(([key, value]) => (
                          <Field key={key} label={key} value={value} />
                        ))}
                      </div>
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
          ) : null}
        </>
      )}
    </section>
  );
}

function Field({ label, value }) {
  return (
    <div style={fieldStyle}>
      <span style={fieldLabelStyle}>{label}</span>
      <span style={fieldValueStyle}>{formatValue(value)}</span>
    </div>
  );
}

const panelStyle = {
  border: "1px solid #30363d",
  borderRadius: "12px",
  backgroundColor: "#0d1117",
  padding: "14px",
  marginTop: "16px",
};

const compactPanelStyle = {
  ...panelStyle,
  padding: "10px",
};

const headerStyle = {
  display: "flex",
  alignItems: "flex-start",
  justifyContent: "space-between",
  gap: "12px",
  flexWrap: "wrap",
  marginBottom: "12px",
};

const eyebrowStyle = {
  margin: "0 0 5px 0",
  color: "#8b949e",
  fontSize: "10px",
  fontWeight: "800",
  letterSpacing: "0.08em",
  textTransform: "uppercase",
};

const titleStyle = {
  margin: 0,
  color: "#e6edf3",
  fontSize: "18px",
  fontWeight: "800",
};

const badgeRowStyle = {
  display: "flex",
  alignItems: "center",
  justifyContent: "flex-end",
  gap: "6px",
  flexWrap: "wrap",
};

const badgeStyle = {
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  borderRadius: "999px",
  padding: "4px 8px",
  fontSize: "10px",
  fontWeight: "800",
  textTransform: "uppercase",
  whiteSpace: "nowrap",
};

const badgeToneStyles = {
  info: {
    color: "#93c5fd",
    border: "1px solid rgba(88, 166, 255, 0.34)",
    backgroundColor: "rgba(31, 111, 235, 0.14)",
  },
  success: {
    color: "#86efac",
    border: "1px solid rgba(63, 185, 80, 0.34)",
    backgroundColor: "rgba(63, 185, 80, 0.14)",
  },
  warning: {
    color: "#f5d487",
    border: "1px solid rgba(217, 164, 65, 0.34)",
    backgroundColor: "rgba(217, 164, 65, 0.14)",
  },
  danger: {
    color: "#fca5a5",
    border: "1px solid rgba(248, 81, 73, 0.34)",
    backgroundColor: "rgba(248, 81, 73, 0.14)",
  },
  muted: {
    color: "#c9d1d9",
    border: "1px solid rgba(139, 148, 158, 0.28)",
    backgroundColor: "rgba(139, 148, 158, 0.12)",
  },
};

const warningStyle = {
  padding: "10px 12px",
  marginBottom: "12px",
  borderRadius: "8px",
  border: "1px solid rgba(217, 164, 65, 0.34)",
  backgroundColor: "rgba(217, 164, 65, 0.12)",
  color: "#f5d487",
  fontSize: "12px",
  fontWeight: "700",
};

const markerBarStyle = {
  display: "flex",
  alignItems: "center",
  gap: "8px",
  flexWrap: "wrap",
  marginBottom: "12px",
};

const markerTextStyle = {
  color: "#8b949e",
  fontSize: "12px",
  fontWeight: "700",
};

const metricsGridStyle = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(96px, 1fr))",
  gap: "8px",
  marginBottom: "14px",
};

const metricStyle = {
  padding: "10px",
  border: "1px solid #30363d",
  borderRadius: "8px",
  backgroundColor: "#161b22",
};

const metricLabelStyle = {
  display: "block",
  marginBottom: "5px",
  color: "#8b949e",
  fontSize: "10px",
  fontWeight: "800",
  textTransform: "uppercase",
};

const metricValueStyle = {
  color: "#e6edf3",
  fontSize: "18px",
};

const flowStyle = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))",
  gap: "8px",
  marginBottom: "14px",
};

const flowNodeStyle = {
  minHeight: "104px",
  border: "1px solid #30363d",
  borderRadius: "10px",
  backgroundColor: "#161b22",
  padding: "10px",
  display: "flex",
  flexDirection: "column",
  gap: "8px",
};

const flowNodeCurrentStyle = {
  border: "1px solid #d29922",
  boxShadow: "0 0 0 1px rgba(217, 164, 65, 0.18)",
};

const flowNodeTerminalStyle = {
  border: "1px solid #58a6ff",
};

const flowDotStyle = {
  width: "10px",
  height: "10px",
  borderRadius: "50%",
};

const flowDotToneStyles = {
  info: { backgroundColor: "#58a6ff" },
  success: { backgroundColor: "#3fb950" },
  warning: { backgroundColor: "#d29922" },
  danger: { backgroundColor: "#f85149" },
  muted: { backgroundColor: "#8b949e" },
};

const flowLabelStyle = {
  color: "#e6edf3",
  fontSize: "13px",
  fontWeight: "800",
};

const flowActionStyle = {
  color: "#8b949e",
  fontSize: "11px",
  fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
  overflowWrap: "anywhere",
};

const flowMarkerStyle = {
  color: "#8b949e",
  fontSize: "11px",
  fontWeight: "700",
};

const timelineListStyle = {
  display: "flex",
  flexDirection: "column",
  gap: "10px",
};

const timelineCardStyle = {
  border: "1px solid #30363d",
  borderRadius: "10px",
  padding: "12px",
  backgroundColor: "#161b22",
};

const timelineCardCurrentStyle = {
  border: "1px solid #d29922",
  backgroundColor: "rgba(217, 164, 65, 0.08)",
};

const timelineCardHeaderStyle = {
  display: "flex",
  justifyContent: "space-between",
  gap: "12px",
  flexWrap: "wrap",
  marginBottom: "10px",
};

const stepTitleStyle = {
  margin: "0 0 4px 0",
  color: "#e6edf3",
  fontSize: "14px",
  fontWeight: "800",
};

const actionStyle = {
  margin: 0,
  color: "#8b949e",
  fontSize: "12px",
  fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
};

const metaGridStyle = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(128px, 1fr))",
  gap: "8px",
};

const fieldStyle = {
  minWidth: 0,
};

const fieldLabelStyle = {
  display: "block",
  marginBottom: "3px",
  color: "#8b949e",
  fontSize: "10px",
  fontWeight: "800",
  textTransform: "uppercase",
};

const fieldValueStyle = {
  display: "block",
  color: "#e6edf3",
  fontSize: "12px",
  lineHeight: 1.35,
  overflowWrap: "anywhere",
};

const messageStyle = {
  margin: "10px 0 0 0",
  padding: "9px 10px",
  borderRadius: "8px",
  backgroundColor: "#0d1117",
  color: "#c9d1d9",
  fontSize: "12px",
  lineHeight: 1.45,
};

const metadataStyle = {
  marginTop: "10px",
  paddingTop: "10px",
  borderTop: "1px solid #30363d",
};

const metadataTitleStyle = {
  margin: "0 0 8px 0",
  color: "#8b949e",
  fontSize: "11px",
  fontWeight: "800",
  textTransform: "uppercase",
};

const emptyTextStyle = {
  margin: 0,
  color: "#8b949e",
  fontSize: "13px",
  lineHeight: 1.45,
};

export default PlaybookExecutionTimeline;
