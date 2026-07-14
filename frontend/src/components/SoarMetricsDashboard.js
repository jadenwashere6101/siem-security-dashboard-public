import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  Bar,
  BarChart,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { getDeadLetterMetrics } from "../services/deadLetterService";
import {
  getApprovalMetrics,
  getIncidentMetrics,
  getNotificationDeliveryMetrics,
  getPlaybookMetrics,
  getPlaybookWorkerMetrics,
} from "../services/metricsService";
import { loadSoarQueueStatus } from "../services/soarQueueService";
import { formatAdminTimestamp } from "../utils/adminPanelDisplay";
import { CanonicalOutcomeBreakdown } from "./ResponseOutcome";

// spec: SPEC-METRICS-001
export const REFRESH_INTERVAL_MS = 60_000;

// --- Domain constants ---

const PLAYBOOK_STATUSES = [
  "pending",
  "running",
  "awaiting_approval",
  "success",
  "failed",
  "abandoned",
];
const DL_STATUSES = ["open", "retrying", "retried", "dismissed"];
const INCIDENT_STATUSES = ["open", "investigating", "resolved", "closed"];
const INCIDENT_SEVERITIES = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];
const APPROVAL_STATUSES = ["pending", "approved", "denied", "expired"];
const QUEUE_STATUSES = [
  "pending",
  "running",
  "awaiting_approval",
  "success",
  "failed",
  "skipped",
];
const CB_STATES = ["closed", "open", "half_open"];
const NOTIF_MODES = ["simulation", "real"];

// spec: SPEC-UI-004 - metrics wording keeps real workflow visibility distinct from guarded integration execution.
const SIMULATION_NOTICE =
  "Simulation-safe execution is the default for outbound actions. These metrics reflect real workflow records, worker activity, approvals, dead letters, and delivery attempts; they do not imply destructive remediation is enabled.";

// spec: SPEC-NOTIFY-001
const NOTIFICATION_METRICS_NOTICE =
  "Operational evidence only: delivery metrics count recorded attempts (simulation and real mode). They do not prove a human received a message at Slack, Teams, or any other provider.";

const WORKER_OPERATIONS_NOTICE =
  "Operational visibility only: worker and queue metrics do not indicate real remediation is active.";

const STATUS_COLOR = {
  success: "#3fb950",
  resolved: "#3fb950",
  retried: "#3fb950",
  approved: "#3fb950",
  closed: "#8b949e",
  failed: "#f85149",
  open: "#f85149",
  denied: "#f85149",
  awaiting_approval: "#d29922",
  retrying: "#d29922",
  pending: "#d29922",
  investigating: "#d29922",
  running: "#388bfd",
  skipped: "#8b949e",
  abandoned: "#8b949e",
  dismissed: "#8b949e",
  expired: "#8b949e",
};

const SEVERITY_COLOR = {
  CRITICAL: "#f85149",
  HIGH: "#db6d28",
  MEDIUM: "#d29922",
  LOW: "#8b949e",
};

const QUEUE_COLOR = {
  pending: "#d29922",
  running: "#388bfd",
  awaiting_approval: "#bc8cff",
  success: "#3fb950",
  failed: "#f85149",
  skipped: "#8b949e",
};

const WORKER_HEALTH_ACCENT = {
  unknown: "#d29922",
  healthy: "#3fb950",
  degraded: "#d29922",
  offline: "#f85149",
};

// --- Helpers ---

function toCount(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
}

export function formatRelativeTime(isoString) {
  if (!isoString) return null;
  const then = new Date(isoString);
  if (Number.isNaN(then.getTime())) return String(isoString);
  const diffMs = Date.now() - then.getTime();
  const diffMins = Math.floor(diffMs / 60_000);
  if (diffMins < 2) return "just now";
  if (diffMins < 60) return `${diffMins} minutes ago`;
  const diffHrs = Math.floor(diffMins / 60);
  if (diffHrs < 24) return `${diffHrs} hour${diffHrs !== 1 ? "s" : ""} ago`;
  const diffDays = Math.floor(diffHrs / 24);
  return `${diffDays} day${diffDays !== 1 ? "s" : ""} ago`;
}

function formatRefreshTime(date) {
  if (!date) return null;
  return (
    date.toLocaleTimeString("en-US", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      timeZone: "UTC",
      hour12: false,
    }) + " UTC"
  );
}

function titleCaseValue(value, fallback = "Unknown") {
  if (!value) return fallback;
  return String(value)
    .replaceAll("_", " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatUptimeSeconds(value) {
  const seconds = Number(value);
  if (!Number.isFinite(seconds) || seconds < 0) return "N/A";
  if (seconds < 60) return `${Math.floor(seconds)}s`;
  const minutes = Math.floor(seconds / 60);
  const remainderSeconds = Math.floor(seconds % 60);
  if (minutes < 60) return `${minutes}m ${remainderSeconds}s`;
  const hours = Math.floor(minutes / 60);
  const remainderMinutes = minutes % 60;
  if (hours < 24) return `${hours}h ${remainderMinutes}m`;
  const days = Math.floor(hours / 24);
  const remainderHours = hours % 24;
  return `${days}d ${remainderHours}h`;
}

function toChartData(obj, keys) {
  if (!obj || typeof obj !== "object") return keys.map((k) => ({ name: k, count: 0 }));
  return keys.map((key) => ({ name: key, count: toCount(obj[key]) }));
}

function toChartDataDynamic(obj) {
  if (!obj || typeof obj !== "object" || Array.isArray(obj)) return [];
  return Object.entries(obj)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([name, count]) => ({ name, count: toCount(count) }));
}

function hasNonZero(data) {
  return Array.isArray(data) && data.some((d) => d.count > 0);
}

function sortedTopN(obj, n = 5) {
  if (!obj || typeof obj !== "object" || Array.isArray(obj)) return [];
  return Object.entries(obj)
    .sort(([, a], [, b]) => toCount(b) - toCount(a))
    .slice(0, n)
    .map(([key, count]) => ({ key, count: toCount(count) }));
}

function normalizePlaybookRows(rawRows) {
  if (!Array.isArray(rawRows)) return [];
  return rawRows.map((row, index) => {
    const playbookId =
      row &&
      row.playbook_id !== null &&
      row.playbook_id !== undefined &&
      row.playbook_id !== ""
        ? String(row.playbook_id)
        : `unknown-${index + 1}`;
    return {
      playbook_id: playbookId,
      total: toCount(row?.total),
      by_status: PLAYBOOK_STATUSES.reduce((acc, s) => {
        acc[s] = toCount(row?.by_status?.[s]);
        return acc;
      }, {}),
    };
  });
}

function initSection() {
  return { data: null, loading: true, error: null };
}

// --- Presentational sub-components ---

function SectionLoading({ label }) {
  return <div aria-label={`Loading ${label}`}>Loading…</div>;
}

function SectionError({ message, onRetry }) {
  return (
    <div role="alert" data-metrics-state="error">
      <span>{message || "Failed to load"}</span>
      <span> — values unavailable (unknown), not zero.</span>
      <button onClick={onRetry} style={{ marginLeft: 8 }}>
        Retry
      </button>
    </div>
  );
}

function MetricCard({ label, value, accent }) {
  const isLongValue = typeof value === "string" && value.length > 18;
  return (
    <div
      style={{
        ...summaryCardStyle,
        ...(accent ? { borderColor: accent + "55" } : {}),
      }}
    >
      <span style={summaryLabelStyle}>{label}</span>
      <span
        style={{
          ...summaryValueStyle,
          ...(isLongValue
            ? {
                fontSize: "14px",
                lineHeight: 1.35,
                wordBreak: "break-word",
              }
            : {}),
          ...(accent ? { color: accent } : {}),
        }}
      >
        {value ?? 0}
      </span>
    </div>
  );
}

function MetricBarChart({ data, colorMap, height = 200 }) {
  if (!hasNonZero(data)) return null;
  return (
    <div style={{ marginTop: 14 }} data-testid="chart-container">
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={data} style={{ backgroundColor: "transparent" }}>
          <XAxis dataKey="name" stroke="#8b949e" tick={{ fontSize: 11 }} />
          <YAxis stroke="#8b949e" allowDecimals={false} />
          <Tooltip
            contentStyle={{
              backgroundColor: "#161b22",
              border: "1px solid #30363d",
              color: "#e6edf3",
            }}
            labelStyle={{ color: "#c9d1d9" }}
            cursor={{ fill: "rgba(88, 166, 255, 0.08)" }}
            wrapperStyle={{ outline: "none" }}
          />
          <Bar dataKey="count">
            {data.map((entry) => (
              <Cell key={entry.name} fill={colorMap?.[entry.name] || "#8b949e"} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function MetricBarChartH({ data, colorMap, height = 180 }) {
  if (!hasNonZero(data)) return null;
  return (
    <div style={{ marginTop: 14 }} data-testid="chart-container">
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={data} layout="vertical" style={{ backgroundColor: "transparent" }}>
          <XAxis type="number" stroke="#8b949e" allowDecimals={false} />
          <YAxis
            dataKey="name"
            type="category"
            stroke="#8b949e"
            width={90}
            tick={{ fontSize: 11 }}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "#161b22",
              border: "1px solid #30363d",
              color: "#e6edf3",
            }}
            labelStyle={{ color: "#c9d1d9" }}
            cursor={{ fill: "rgba(88, 166, 255, 0.08)" }}
            wrapperStyle={{ outline: "none" }}
          />
          <Bar dataKey="count">
            {data.map((entry) => (
              <Cell key={entry.name} fill={colorMap?.[entry.name] || "#8b949e"} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function PlaybookTable({ rows }) {
  const [open, setOpen] = useState(false);
  if (!rows || rows.length === 0) return null;
  return (
    <div style={sectionBlockStyle}>
      <button
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        style={toggleButtonStyle}
      >
        {open ? "▾" : "▸"} Per-Playbook Breakdown ({rows.length})
      </button>
      {open && (
        <ul style={rowListStyle} aria-label="Playbook breakdown table">
          {rows.map((row) => (
            <li key={row.playbook_id} style={rowCardStyle}>
              <div style={rowHeaderStyle}>
                <span style={playbookIdStyle}>{row.playbook_id}</span>
                <span style={totalPillStyle}>Total: {row.total}</span>
              </div>
              <div style={rowStatusGridStyle}>
                {PLAYBOOK_STATUSES.map((status) => (
                  <span key={status} style={inlineStatusStyle}>
                    {status}: {row.by_status[status]}
                  </span>
                ))}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// --- Main component ---

export default function SoarMetricsDashboard({
  cardStyle,
  cardHeaderStyle,
  cardTitleStyle,
  cardSubtitleStyle,
  userRole,
}) {
  const [playbook, setPlaybook] = useState(initSection);
  const [deadLetter, setDeadLetter] = useState(initSection);
  const [notification, setNotification] = useState(initSection);
  const [incident, setIncident] = useState(initSection);
  const [approval, setApproval] = useState(initSection);
  const [worker, setWorker] = useState(initSection);
  const [queue, setQueue] = useState(initSection);
  const [refreshing, setRefreshing] = useState(false);
  const [lastRefreshedAt, setLastRefreshedAt] = useState(null);

  const intervalRef = useRef(null);
  const isSuperAdmin = userRole === "super_admin";
  const canViewWorkerOperations = userRole === "analyst" || userRole === "super_admin";

  const fetchSection = useCallback(async (fetchFn, setter) => {
    setter((prev) => ({ ...prev, loading: true, error: null }));
    try {
      const data = await fetchFn();
      setter({ data, loading: false, error: null });
    } catch (err) {
      setter((prev) => ({
        ...prev,
        loading: false,
        error: err?.message || "Failed to load",
      }));
    }
  }, []);

  const fetchAll = useCallback(async () => {
    setRefreshing(true);

    const sections = [
      [getPlaybookMetrics, setPlaybook],
      [getDeadLetterMetrics, setDeadLetter],
      [getNotificationDeliveryMetrics, setNotification],
      [getIncidentMetrics, setIncident],
      [getApprovalMetrics, setApproval],
    ];

    if (canViewWorkerOperations) {
      sections.push([getPlaybookWorkerMetrics, setWorker]);
    } else {
      setWorker((prev) => ({ ...prev, loading: false }));
    }

    if (userRole === "super_admin") {
      sections.push([loadSoarQueueStatus, setQueue]);
    } else {
      setQueue((prev) => ({ ...prev, loading: false }));
    }

    const results = await Promise.allSettled(sections.map(([fn]) => fn()));

    results.forEach((result, i) => {
      const [, setter] = sections[i];
      if (result.status === "fulfilled") {
        setter({ data: result.value, loading: false, error: null });
      } else {
        setter((prev) => ({
          ...prev,
          loading: false,
          error: result.reason?.message || "Failed to load",
        }));
      }
    });

    setRefreshing(false);
    setLastRefreshedAt(new Date());
  }, [canViewWorkerOperations, userRole]);

  useEffect(() => {
    fetchAll();
    intervalRef.current = setInterval(fetchAll, REFRESH_INTERVAL_MS);
    return () => {
      clearInterval(intervalRef.current);
    };
  }, [fetchAll]);

  const handleManualRefresh = useCallback(() => {
    setPlaybook((prev) => ({ ...prev, error: null }));
    setDeadLetter((prev) => ({ ...prev, error: null }));
    setNotification((prev) => ({ ...prev, error: null }));
    setIncident((prev) => ({ ...prev, error: null }));
    setApproval((prev) => ({ ...prev, error: null }));
    setWorker((prev) => ({ ...prev, error: null }));
    setQueue((prev) => ({ ...prev, error: null }));
    clearInterval(intervalRef.current);
    intervalRef.current = setInterval(fetchAll, REFRESH_INTERVAL_MS);
    fetchAll();
  }, [fetchAll]);

  // Pre-computed chart/card values from section data
  const playbookStatusData = toChartData(playbook.data?.by_status, PLAYBOOK_STATUSES);
  const playbookRows = normalizePlaybookRows(playbook.data?.by_playbook_id);

  const dlStatusData = toChartData(deadLetter.data?.by_status, DL_STATUSES);
  const dlTopFailures = sortedTopN(deadLetter.data?.by_failure_class, 5);
  const dlOldestActive = formatRelativeTime(deadLetter.data?.oldest_active_at ?? null);

  const notifProviders = toChartDataDynamic(notification.data?.by_provider);
  const notifCbData = toChartData(
    notification.data?.circuit_breaker_state_counts,
    CB_STATES
  );
  const notifRecentSuccess = toCount(notification.data?.recent?.success);
  const notifRecentFailedBlocked =
    toCount(notification.data?.recent?.failed) +
    toCount(notification.data?.recent?.blocked);
  const notifSimCount = toCount(notification.data?.by_mode?.simulation);
  const notifRealCount = toCount(notification.data?.by_mode?.real);
  const notifTotal = toCount(notification.data?.total_delivery_attempts);

  const incidentStatusData = toChartData(incident.data?.by_status, INCIDENT_STATUSES);
  const incidentSeverityData = toChartData(
    incident.data?.by_severity,
    INCIDENT_SEVERITIES
  );
  const incidentOpenActive =
    toCount(incident.data?.by_status?.open) +
    toCount(incident.data?.by_status?.investigating);
  const incidentResolvedClosed =
    toCount(incident.data?.by_status?.resolved) +
    toCount(incident.data?.by_status?.closed);
  const incidentOpenHighCritical = toCount(
    incident.data?.open_high_critical ?? incident.data?.open_high_critical_count
  );

  const approvalStatusData = toChartData(approval.data?.by_status, APPROVAL_STATUSES);
  const approvalPending = toCount(
    approval.data?.pending_count ?? approval.data?.by_status?.pending
  );

  const workerQueueDepth = worker.data?.queue_depth || {};
  const workerRunning = worker.data?.running || {};
  const workerRecent = worker.data?.recent || {};
  const workerRecovery = worker.data?.recovery || {};
  const workerHealth = worker.data?.daemon_health || {};
  const workerHeartbeatStatus = workerHealth.status || "unknown";
  const workerHeartbeatAccent = WORKER_HEALTH_ACCENT[workerHeartbeatStatus] || undefined;
  const workerHeartbeatMessage =
    workerHealth.message || "Worker heartbeat status is unavailable.";
  const workerLastHeartbeat = workerHealth.last_heartbeat_at
    ? formatAdminTimestamp(workerHealth.last_heartbeat_at, "Never seen")
    : "Never seen";
  const workerStartedAt = workerHealth.started_at
    ? formatAdminTimestamp(workerHealth.started_at, "Not started")
    : "Not started";
  const workerUptime = formatUptimeSeconds(workerHealth.uptime_seconds);
  const workerBuildVersion = workerHealth.build_version || "Unavailable";
  const workerHasMetrics =
    toCount(workerQueueDepth.active_total) > 0 ||
    toCount(workerRunning.total) > 0 ||
    toCount(workerRecent.failed_executions) > 0 ||
    toCount(workerRecent.active_dead_letters) > 0 ||
    toCount(workerRecovery.total_recovery_count) > 0;

  const queueStatusData = toChartData(queue.data?.counts, QUEUE_STATUSES);
  const queueGeneratedAt = queue.data?.generated_at;

  return (
    <section style={cardStyle}>
      <header style={cardHeaderStyle}>
        <div>
          <span style={cardTitleStyle}>SOAR Metrics Dashboard</span>
          {lastRefreshedAt && (
            <span style={cardSubtitleStyle}>
              {" "}Last refreshed: {formatRefreshTime(lastRefreshedAt)}
            </span>
          )}
        </div>
        <div>
          {refreshing && <span aria-label="Refreshing">Refreshing…</span>}
          <button onClick={handleManualRefresh} disabled={refreshing}>
            Refresh now
          </button>
        </div>
      </header>

      <div style={panelContentStyle}>

        {/* ── Section 1: Playbook Metrics ── */}
        <section aria-label="Playbook Metrics" style={sectionWrapStyle} data-metrics-source="playbook_executions">
          <h3 style={sectionHeadingStyle}>Playbook Metrics</h3>
          {playbook.loading && <SectionLoading label="Playbook Metrics" />}
          {!playbook.loading && playbook.error && (
            <SectionError
              message={playbook.error}
              onRetry={() => fetchSection(getPlaybookMetrics, setPlaybook)}
            />
          )}
          {!playbook.loading && !playbook.error && (
            <>
              <div style={simulationNoticeStyle} role="note">
                {SIMULATION_NOTICE}
              </div>
              <div style={summaryGridStyle}>
                <MetricCard
                  label="Total Executions"
                  value={toCount(playbook.data?.total_executions)}
                />
                <MetricCard
                  label="Success (24 h)"
                  value={toCount(playbook.data?.recent?.success)}
                  accent="#3fb950"
                />
                <MetricCard
                  label="Failed (24 h)"
                  value={toCount(playbook.data?.recent?.failed)}
                  accent={
                    toCount(playbook.data?.recent?.failed) > 0 ? "#f85149" : undefined
                  }
                />
                <MetricCard
                  label="Awaiting Approval"
                  value={toCount(playbook.data?.approval_gated?.awaiting_approval)}
                />
                {playbook.data?.stale_running_count != null && (
                  <MetricCard
                    label="Stale Running"
                    value={toCount(playbook.data.stale_running_count)}
                    accent={
                      toCount(playbook.data.stale_running_count) > 0
                        ? "#f85149"
                        : undefined
                    }
                  />
                )}
              </div>
              {hasNonZero(playbookStatusData) ? (
                <MetricBarChart data={playbookStatusData} colorMap={STATUS_COLOR} />
              ) : (
                <p style={emptyTextStyle}>No executions recorded.</p>
              )}
              <PlaybookTable rows={playbookRows} />
              <CanonicalOutcomeBreakdown
                counts={playbook.data?.canonical_outcome_counts}
                title="Playbook canonical outcome counts"
              />
            </>
          )}
        </section>

        {/* ── Section 2: Dead Letter Metrics ── */}
        <section aria-label="Dead Letter Metrics" style={sectionWrapStyle} data-metrics-source="soar_dead_letters">
          <h3 style={sectionHeadingStyle}>Dead Letter Metrics</h3>
          {deadLetter.loading && <SectionLoading label="Dead Letter Metrics" />}
          {!deadLetter.loading && deadLetter.error && (
            <SectionError
              message={deadLetter.error}
              onRetry={() => fetchSection(getDeadLetterMetrics, setDeadLetter)}
            />
          )}
          {!deadLetter.loading && !deadLetter.error && (
            <>
              <div style={summaryGridStyle}>
                <MetricCard
                  label="Open"
                  value={toCount(deadLetter.data?.open)}
                  accent={toCount(deadLetter.data?.open) > 0 ? "#f85149" : undefined}
                />
                <MetricCard
                  label="Retrying"
                  value={toCount(deadLetter.data?.retrying)}
                  accent={toCount(deadLetter.data?.retrying) > 0 ? "#d29922" : undefined}
                />
                <MetricCard
                  label="Oldest Active"
                  value={dlOldestActive ?? "None"}
                />
              </div>
              {hasNonZero(dlStatusData) ? (
                <MetricBarChart data={dlStatusData} colorMap={STATUS_COLOR} />
              ) : (
                <p style={emptyTextStyle}>No dead letters recorded.</p>
              )}
              <div style={sectionBlockStyle}>
                <h4 style={subsectionTitleStyle}>Top Failure Classes</h4>
                {dlTopFailures.length === 0 ? (
                  <p style={emptyTextStyle}>No failures recorded.</p>
                ) : (
                  <table style={simpleTableStyle}>
                    <thead>
                      <tr>
                        <th style={tableThStyle}>Failure class</th>
                        <th style={tableThStyle}>Count</th>
                      </tr>
                    </thead>
                    <tbody>
                      {dlTopFailures.map(({ key, count }) => (
                        <tr key={key}>
                          <td style={tableTdStyle}>{key}</td>
                          <td style={tableTdStyle}>{count}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
              <p style={operationalNoteStyle}>
                Review and retry failed executions in the SOAR Operations tab.
              </p>
            </>
          )}
        </section>

        {/* ── Section 3: Notification Delivery Metrics ── */}
        <section aria-label="Notification Delivery Metrics" style={sectionWrapStyle} data-metrics-source="notification_delivery_attempts">
          <h3 style={sectionHeadingStyle}>Notification Delivery Metrics</h3>
          {notification.loading && (
            <SectionLoading label="Notification Delivery Metrics" />
          )}
          {!notification.loading && notification.error && (
            <SectionError
              message={notification.error}
              onRetry={() =>
                fetchSection(getNotificationDeliveryMetrics, setNotification)
              }
            />
          )}
          {!notification.loading && !notification.error && (
            <>
              <div style={notificationNoticeStyle} role="note">
                {NOTIFICATION_METRICS_NOTICE}
              </div>
              <div style={summaryGridStyle}>
                <MetricCard label="Total Attempts" value={notifTotal} />
                <MetricCard
                  label="Success (24 h)"
                  value={notifRecentSuccess}
                  accent="#3fb950"
                />
                <MetricCard
                  label="Failed + Blocked (24 h)"
                  value={notifRecentFailedBlocked}
                  accent={notifRecentFailedBlocked > 0 ? "#f85149" : undefined}
                />
                <MetricCard
                  label="Simulation / Real"
                  value={`${notifSimCount} / ${notifRealCount}`}
                />
              </div>
              {hasNonZero(notifProviders) ? (
                <MetricBarChartH data={notifProviders} colorMap={{}} />
              ) : (
                <p style={emptyTextStyle}>No provider breakdown available.</p>
              )}
              {hasNonZero(notifCbData) && (
                <div style={sectionBlockStyle}>
                  <h4 style={subsectionTitleStyle}>Circuit Breaker States</h4>
                  <div style={inlineRowStyle}>
                    {notifCbData.map(({ name, count }) => (
                      <span key={name} style={cbPillStyle}>
                        {name}: {count}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              <div style={summaryGridStyle}>
                {NOTIF_MODES.map((mode) => (
                  <MetricCard
                    key={mode}
                    label={`Mode: ${mode}`}
                    value={toCount(notification.data?.by_mode?.[mode])}
                  />
                ))}
              </div>
              <CanonicalOutcomeBreakdown
                counts={notification.data?.canonical_outcome_counts}
                title="Notification canonical outcome counts"
              />
            </>
          )}
        </section>

        {/* ── Section 4: Incident Metrics ── */}
        <section aria-label="Incident Metrics" style={sectionWrapStyle} data-metrics-source="soar_incidents">
          <h3 style={sectionHeadingStyle}>Incident Metrics</h3>
          {incident.loading && <SectionLoading label="Incident Metrics" />}
          {!incident.loading && incident.error && (
            <SectionError
              message={incident.error}
              onRetry={() => fetchSection(getIncidentMetrics, setIncident)}
            />
          )}
          {!incident.loading && !incident.error && (
            <>
              <div style={summaryGridStyle}>
                <MetricCard
                  label="Open + Investigating"
                  value={incidentOpenActive}
                  accent={incidentOpenActive > 0 ? "#d29922" : undefined}
                />
                <MetricCard label="Resolved + Closed" value={incidentResolvedClosed} />
                <MetricCard
                  label="Open Critical / High"
                  value={incidentOpenHighCritical}
                  accent={incidentOpenHighCritical > 0 ? "#f85149" : undefined}
                />
              </div>
              <div style={dualChartGridStyle}>
                <div>
                  <h4 style={subsectionTitleStyle}>By Status</h4>
                  {hasNonZero(incidentStatusData) ? (
                    <MetricBarChart
                      data={incidentStatusData}
                      colorMap={STATUS_COLOR}
                      height={180}
                    />
                  ) : (
                    <p style={emptyTextStyle}>No incidents recorded.</p>
                  )}
                </div>
                <div>
                  <h4 style={subsectionTitleStyle}>By Severity</h4>
                  {hasNonZero(incidentSeverityData) ? (
                    <MetricBarChart
                      data={incidentSeverityData}
                      colorMap={SEVERITY_COLOR}
                      height={180}
                    />
                  ) : (
                    <p style={emptyTextStyle}>No severity data.</p>
                  )}
                </div>
              </div>
              <CanonicalOutcomeBreakdown
                counts={incident.data?.canonical_outcome_counts}
                title="Incident canonical outcome counts"
              />
            </>
          )}
        </section>

        {/* ── Section 5: Approval Metrics ── */}
        <section aria-label="Approval Metrics" style={sectionWrapStyle} data-metrics-source="soar_approvals">
          <h3 style={sectionHeadingStyle}>Approval Metrics</h3>
          {approval.loading && <SectionLoading label="Approval Metrics" />}
          {!approval.loading && approval.error && (
            <SectionError
              message={approval.error}
              onRetry={() => fetchSection(getApprovalMetrics, setApproval)}
            />
          )}
          {!approval.loading && !approval.error && (
            <>
              <div style={summaryGridStyle}>
                <MetricCard
                  label="Pending"
                  value={approvalPending}
                  accent={approvalPending > 0 ? "#d29922" : undefined}
                />
                <MetricCard
                  label="Approved"
                  value={toCount(approval.data?.by_status?.approved)}
                  accent="#3fb950"
                />
                <MetricCard
                  label="Denied"
                  value={toCount(approval.data?.by_status?.denied)}
                  accent={
                    toCount(approval.data?.by_status?.denied) > 0 ? "#f85149" : undefined
                  }
                />
                <MetricCard
                  label="Expired"
                  value={toCount(approval.data?.by_status?.expired)}
                />
              </div>
              {hasNonZero(approvalStatusData) ? (
                <MetricBarChart data={approvalStatusData} colorMap={STATUS_COLOR} />
              ) : (
                <p style={emptyTextStyle}>No approvals recorded.</p>
              )}
              <p style={operationalNoteStyle}>
                Approve or deny pending approvals in the SOAR Approvals tab.
              </p>
              <CanonicalOutcomeBreakdown
                counts={approval.data?.canonical_outcome_counts}
                title="Approval canonical outcome counts"
              />
            </>
          )}
        </section>

        {/* ── Section 6: Worker Operations ── */}
        {canViewWorkerOperations && (
          <section aria-label="Worker Operations" style={sectionWrapStyle} data-metrics-source="playbook_worker_runtime">
            <h3 style={sectionHeadingStyle}>Worker Operations</h3>
            {worker.loading && <SectionLoading label="Worker Operations" />}
            {!worker.loading && worker.error && (
              <SectionError
                message={worker.error}
                onRetry={() => fetchSection(getPlaybookWorkerMetrics, setWorker)}
              />
            )}
            {!worker.loading && !worker.error && (
              <>
                <div style={workerNoticeStyle} role="note">
                  {WORKER_OPERATIONS_NOTICE}
                </div>
                <div style={summaryGridStyle}>
                  <MetricCard
                    label="Heartbeat"
                    value={titleCaseValue(workerHeartbeatStatus)}
                    accent={workerHeartbeatAccent}
                  />
                  <MetricCard
                    label="Last Heartbeat"
                    value={workerLastHeartbeat}
                    accent={workerHeartbeatAccent}
                  />
                  <MetricCard
                    label="Started"
                    value={workerStartedAt}
                  />
                  <MetricCard
                    label="Uptime"
                    value={workerUptime}
                  />
                  <MetricCard
                    label="Build"
                    value={workerBuildVersion}
                  />
                  <MetricCard
                    label="Pending"
                    value={toCount(workerQueueDepth.pending)}
                    accent={toCount(workerQueueDepth.pending) > 0 ? "#d29922" : undefined}
                  />
                  <MetricCard
                    label="Running"
                    value={toCount(workerQueueDepth.running)}
                    accent="#388bfd"
                  />
                  <MetricCard
                    label="Awaiting Approval"
                    value={toCount(workerQueueDepth.awaiting_approval)}
                    accent="#bc8cff"
                  />
                  <MetricCard
                    label="Stale Running"
                    value={toCount(
                      worker.data?.stale_running_count ?? workerRunning.stale
                    )}
                    accent={
                      toCount(worker.data?.stale_running_count ?? workerRunning.stale) > 0
                        ? "#f85149"
                        : undefined
                    }
                  />
                  <MetricCard
                    label="Missing Lease"
                    value={toCount(workerRunning.missing_lease)}
                    accent={toCount(workerRunning.missing_lease) > 0 ? "#d29922" : undefined}
                  />
                  <MetricCard
                    label="Failed (24 h)"
                    value={toCount(workerRecent.failed_executions)}
                    accent={toCount(workerRecent.failed_executions) > 0 ? "#f85149" : undefined}
                  />
                  <MetricCard
                    label="Active Dead Letters"
                    value={toCount(workerRecent.active_dead_letters)}
                    accent={toCount(workerRecent.active_dead_letters) > 0 ? "#f85149" : undefined}
                  />
                  <MetricCard
                    label="Playbook Dead Letters"
                    value={toCount(workerRecent.active_playbook_dead_letters)}
                    accent={
                      toCount(workerRecent.active_playbook_dead_letters) > 0
                        ? "#f85149"
                        : undefined
                    }
                  />
                  <MetricCard
                    label="Recoveries"
                    value={toCount(workerRecovery.total_recovery_count)}
                  />
                  <MetricCard
                    label="Recovered Executions"
                    value={toCount(workerRecovery.recovered_execution_count)}
                  />
                </div>
                <p style={mutedTextStyle}>{workerHeartbeatMessage}</p>
                {!workerHasMetrics && (
                  <p style={emptyTextStyle}>No worker queue activity recorded.</p>
                )}
              </>
            )}
          </section>
        )}

        {/* ── Section 7: SOAR Queue Health (super_admin only) ── */}
        {isSuperAdmin && (
          <section aria-label="SOAR Queue Health" style={sectionWrapStyle} data-metrics-source="response_action_queue">
            <h3 style={sectionHeadingStyle}>SOAR Queue Health</h3>
            {queue.loading && <SectionLoading label="SOAR Queue Health" />}
            {!queue.loading && queue.error && (
              <SectionError
                message={queue.error}
                onRetry={() => fetchSection(loadSoarQueueStatus, setQueue)}
              />
            )}
            {!queue.loading && !queue.error && (
              <>
                <div style={summaryGridStyle}>
                  <MetricCard
                    label="Pending"
                    value={toCount(queue.data?.counts?.pending)}
                    accent={
                      toCount(queue.data?.counts?.pending) > 0 ? "#d29922" : undefined
                    }
                  />
                  <MetricCard
                    label="Running"
                    value={toCount(queue.data?.counts?.running)}
                    accent="#388bfd"
                  />
                  <MetricCard
                    label="Awaiting Approval"
                    value={toCount(queue.data?.counts?.awaiting_approval)}
                    accent="#bc8cff"
                  />
                  <MetricCard
                    label="Failed"
                    value={toCount(queue.data?.counts?.failed)}
                    accent={
                      toCount(queue.data?.counts?.failed) > 0 ? "#f85149" : undefined
                    }
                  />
                </div>
                {hasNonZero(queueStatusData) ? (
                  <MetricBarChart data={queueStatusData} colorMap={QUEUE_COLOR} />
                ) : (
                  <p style={emptyTextStyle}>No queue entries recorded.</p>
                )}
                {queueGeneratedAt && (
                  <p style={mutedTextStyle} aria-label="Queue snapshot timestamp">
                    Queue snapshot as of {queueGeneratedAt}
                  </p>
                )}
              </>
            )}
          </section>
        )}

      </div>
    </section>
  );
}

// --- Styles ---

const panelContentStyle = {
  padding: "20px 20px 24px",
  display: "flex",
  flexDirection: "column",
  gap: "0",
};

const sectionWrapStyle = {
  paddingTop: "22px",
  paddingBottom: "22px",
  borderBottom: "1px solid #21262d",
};

const sectionHeadingStyle = {
  margin: "0 0 14px 0",
  fontSize: "16px",
  fontWeight: "700",
  color: "#e6edf3",
};

const subsectionTitleStyle = {
  margin: "0 0 8px 0",
  fontSize: "13px",
  fontWeight: "700",
  color: "#c9d1d9",
};

const summaryGridStyle = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
  gap: "10px",
  marginBottom: "14px",
};

const summaryCardStyle = {
  display: "flex",
  flexDirection: "column",
  gap: "4px",
  padding: "10px 12px",
  borderRadius: "10px",
  border: "1px solid #30363d",
  backgroundColor: "#0d1117",
};

const summaryLabelStyle = {
  color: "#8b949e",
  fontSize: "11px",
  fontWeight: "700",
  letterSpacing: "0.06em",
  textTransform: "uppercase",
};

const summaryValueStyle = {
  color: "#e6edf3",
  fontSize: "20px",
  fontWeight: "700",
};

const sectionBlockStyle = {
  marginTop: "16px",
};

const emptyTextStyle = {
  margin: "10px 0",
  color: "#8b949e",
  fontSize: "13px",
};

const operationalNoteStyle = {
  marginTop: "12px",
  color: "#8b949e",
  fontSize: "12px",
  fontStyle: "italic",
};

const mutedTextStyle = {
  margin: "10px 0 0",
  color: "#8b949e",
  fontSize: "12px",
};

const simulationNoticeStyle = {
  marginBottom: "14px",
  padding: "10px 14px",
  borderRadius: "10px",
  border: "1px solid rgba(210, 153, 34, 0.35)",
  backgroundColor: "rgba(210, 153, 34, 0.10)",
  color: "#e6c35c",
  fontSize: "12px",
  fontWeight: "600",
  lineHeight: 1.45,
};

const notificationNoticeStyle = {
  marginBottom: "14px",
  padding: "10px 12px",
  borderRadius: "10px",
  border: "1px solid rgba(56, 139, 253, 0.35)",
  backgroundColor: "rgba(56, 139, 253, 0.08)",
  color: "#c9e1ff",
  fontSize: "12px",
  fontWeight: "600",
  lineHeight: 1.45,
};

const workerNoticeStyle = {
  marginBottom: "14px",
  padding: "10px 12px",
  borderRadius: "10px",
  border: "1px solid rgba(188, 140, 255, 0.35)",
  backgroundColor: "rgba(188, 140, 255, 0.08)",
  color: "#d8c4ff",
  fontSize: "12px",
  fontWeight: "600",
  lineHeight: 1.45,
};

const dualChartGridStyle = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
  gap: "20px",
  marginTop: "14px",
};

const inlineRowStyle = {
  display: "flex",
  flexWrap: "wrap",
  gap: "8px",
  marginTop: "6px",
};

const cbPillStyle = {
  fontSize: "12px",
  color: "#c9d1d9",
  border: "1px solid #30363d",
  borderRadius: "8px",
  padding: "3px 10px",
  backgroundColor: "#161b22",
};

const simpleTableStyle = {
  width: "100%",
  borderCollapse: "collapse",
  marginTop: "8px",
};

const tableThStyle = {
  textAlign: "left",
  color: "#8b949e",
  fontSize: "11px",
  fontWeight: "700",
  letterSpacing: "0.06em",
  textTransform: "uppercase",
  padding: "6px 8px",
  borderBottom: "1px solid #30363d",
};

const tableTdStyle = {
  color: "#c9d1d9",
  fontSize: "13px",
  padding: "6px 8px",
  borderBottom: "1px solid #21262d",
};

const toggleButtonStyle = {
  background: "none",
  border: "1px solid #30363d",
  borderRadius: "6px",
  color: "#c9d1d9",
  fontSize: "13px",
  cursor: "pointer",
  padding: "5px 10px",
  marginBottom: "10px",
};

const rowListStyle = {
  listStyle: "none",
  margin: 0,
  padding: 0,
  display: "flex",
  flexDirection: "column",
  gap: "8px",
};

const rowCardStyle = {
  border: "1px solid #30363d",
  borderRadius: "8px",
  padding: "10px 12px",
  backgroundColor: "#0d1117",
};

const rowHeaderStyle = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: "10px",
  marginBottom: "6px",
  flexWrap: "wrap",
};

const playbookIdStyle = {
  color: "#e6edf3",
  fontWeight: "700",
  fontSize: "13px",
};

const totalPillStyle = {
  color: "#c9d1d9",
  fontSize: "12px",
  border: "1px solid #30363d",
  borderRadius: "999px",
  padding: "2px 8px",
  backgroundColor: "#161b22",
};

const rowStatusGridStyle = {
  display: "flex",
  flexWrap: "wrap",
  gap: "6px",
};

const inlineStatusStyle = {
  color: "#8b949e",
  fontSize: "11px",
  border: "1px solid #30363d",
  borderRadius: "6px",
  padding: "2px 6px",
};
