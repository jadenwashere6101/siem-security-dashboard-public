import React, { useCallback, useEffect, useMemo, useState } from "react";

import { listApprovals } from "../services/approvalService";
import { getDeadLetterMetrics, getDeadLetters } from "../services/deadLetterService";
import {
  loadIncidentDetail,
  loadIncidentTimeline,
  loadIncidents,
} from "../services/incidentService";
import { getIntegrationStatus } from "../services/integrationService";
import {
  getApprovalMetrics,
  getIncidentMetrics,
  getNotificationDeliveryMetrics,
  getPlaybookMetrics,
  getPlaybookWorkerMetrics,
} from "../services/metricsService";
import {
  listIncidentNotificationDeliveries,
  listNotificationDeliveries,
} from "../services/notificationDeliveryService";
import { listPlaybookExecutions } from "../services/playbookService";
import {
  loadRecentSoarQueueItems,
  loadSoarQueueStatus,
} from "../services/soarQueueService";
import ExecutionSafetyModelPanel from "./ExecutionSafetyModelPanel";
import SourceIpContext from "./SourceIpContext";
import { CanonicalOutcomeBreakdown, ResponseOutcomeSummary } from "./ResponseOutcome";
import { mergeCanonicalOutcomeCounts } from "../utils/responseOutcomeDisplay";
import { WorkspaceInitialState, WorkspaceRefreshState } from "./WorkspaceAsyncState";

// spec: SPEC-UI-004 - SOC safety model wording separates real workflows from guarded integrations.
const SOURCE_LIMIT = 12;
const FEED_LIMIT = 14;
const ATTENTION_LIMIT = 8;
const ACTION_ROLES = new Set(["analyst", "super_admin"]);
const FAILURE_STATUS = new Set(["failed", "timeout", "blocked", "skipped"]);
const ACTIVE_EXECUTION_STATUS = new Set(["pending", "running", "awaiting_approval"]);
const ACTIVE_DEAD_LETTER_STATUS = new Set(["open", "retrying", "retry_requested"]);

const emptyCommandData = {
  incidents: [],
  executions: [],
  approvals: [],
  deadLetters: [],
  notifications: [],
  queueItems: [],
  incidentMetrics: {},
  playbookMetrics: {},
  approvalMetrics: {},
  deadLetterMetrics: {},
  notificationMetrics: {},
  workerMetrics: {},
  queueStatus: {},
  integrationStatus: {},
};

export function normalizeItems(payload, keys = []) {
  if (Array.isArray(payload)) return payload;
  if (!payload || typeof payload !== "object") return [];

  const candidateKeys = [
    ...keys,
    "items",
    "incidents",
    "approvals",
    "dead_letters",
    "deadLetters",
    "executions",
    "timeline",
    "notifications",
  ];

  for (const key of candidateKeys) {
    if (Array.isArray(payload[key])) {
      return payload[key];
    }
  }

  return [];
}

function normalizeIncident(payload) {
  if (!payload || typeof payload !== "object") return null;
  return payload.incident && typeof payload.incident === "object"
    ? payload.incident
    : payload;
}

function valueOrFallback(value, fallback = "Unavailable") {
  if (value === undefined || value === null || value === "") {
    return fallback;
  }
  return String(value);
}

function titleCase(value) {
  return valueOrFallback(value, "Unknown")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function toNumber(value, fallback = 0) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : fallback;
}

function metricCount(metric, paths, fallback = 0) {
  for (const path of paths) {
    const parts = path.split(".");
    let current = metric;
    for (const part of parts) {
      current = current && typeof current === "object" ? current[part] : undefined;
    }
    if (current !== undefined && current !== null) {
      return toNumber(current, fallback);
    }
  }
  return fallback;
}

function firstTimestamp(item) {
  if (!item || typeof item !== "object") return "";
  return (
    item.updated_at ||
    item.created_at ||
    item.completed_at ||
    item.started_at ||
    item.timestamp ||
    item.last_seen_at ||
    ""
  );
}

function formatRelative(value) {
  if (!value) return "Time unavailable";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  const diffMs = Date.now() - date.getTime();
  const diffMinutes = Math.round(diffMs / 60000);
  if (Math.abs(diffMinutes) < 1) return "Just now";
  if (Math.abs(diffMinutes) < 60) return `${diffMinutes}m ago`;
  const diffHours = Math.round(diffMinutes / 60);
  if (Math.abs(diffHours) < 24) return `${diffHours}h ago`;
  const diffDays = Math.round(diffHours / 24);
  if (Math.abs(diffDays) < 7) return `${diffDays}d ago`;
  return date.toLocaleString();
}

function joinDefined(parts) {
  return parts.filter((part) => part !== undefined && part !== null && part !== "").join(" • ");
}

function getId(item) {
  if (!item || typeof item !== "object") return "";
  return item.id || item.incident_id || item.execution_id || item.queue_id || item.alert_id || "";
}

function filterByIncident(items, incidentId) {
  if (incidentId === undefined || incidentId === null || incidentId === "") return [];
  const normalizedId = String(incidentId);
  return items.filter((item) => String(item?.incident_id ?? "") === normalizedId);
}

function findLinkedAlerts(alerts, incident) {
  const incidentId = incident?.id ?? incident?.incident_id;
  const detailAlerts = normalizeItems(incident, ["alerts", "linked_alerts"]);
  if (detailAlerts.length > 0) return detailAlerts;

  return normalizeItems(alerts).filter((alert) => {
    if (incidentId && String(alert.incident_id ?? "") === String(incidentId)) return true;
    if (incident?.alert_id && String(alert.id ?? alert.alert_id ?? "") === String(incident.alert_id)) {
      return true;
    }
    return false;
  });
}

function buildFailureSources(statuses) {
  return statuses.filter((status) => FAILURE_STATUS.has(String(status || "").toLowerCase()));
}

function getIntegrationAdapters(status) {
  return normalizeItems(status, ["adapters", "integrations"]);
}

function deriveIntegrationSummary(status) {
  const adapters = getIntegrationAdapters(status);
  const realEnabled = adapters.filter((adapter) => {
    return (
      adapter?.mode === "real" ||
      adapter?.mode_decision === "real-enabled" ||
      adapter?.real_enabled === true ||
      adapter?.real_mode_enabled === true
    );
  });
  const blocked = adapters.filter((adapter) => {
    const circuit = String(adapter?.circuit_breaker?.state || adapter?.circuit_state || "").toLowerCase();
    return circuit === "open" || adapter?.blocked === true || adapter?.available === false;
  });
  const mode = status?.mode || status?.integration_mode || (realEnabled.length ? "real" : "simulation");
  return {
    adapterCount: adapters.length,
    realEnabledCount: realEnabled.length,
    blockedCount: blocked.length,
    mode,
  };
}

export function buildActivityFeed(data) {
  const entries = [];

  for (const incident of data.incidents || []) {
    entries.push({
      id: `incident-${getId(incident)}`,
      source: "Incident",
      tone: "danger",
      timestamp: firstTimestamp(incident),
      title: incident.title || `Incident #${getId(incident) || "unknown"}`,
      detail: joinDefined([
        titleCase(incident.severity),
        titleCase(incident.status),
        incident.source_ip,
      ]),
    });
  }

  for (const execution of data.executions || []) {
    entries.push({
      id: `execution-${getId(execution)}`,
      source: "Playbook",
      tone: String(execution.status || "").toLowerCase() === "failed" ? "danger" : "info",
      timestamp: firstTimestamp(execution),
      title: execution.playbook_id || execution.playbook_name || `Execution #${getId(execution) || "unknown"}`,
      detail: joinDefined([
        titleCase(execution.status),
        execution.incident_id ? `Incident ${execution.incident_id}` : "",
      ]),
    });
  }

  for (const approval of data.approvals || []) {
    entries.push({
      id: `approval-${getId(approval)}`,
      source: "Approval",
      tone: String(approval.status || "").toLowerCase() === "pending" ? "warning" : "info",
      timestamp: firstTimestamp(approval),
      title: approval.action ? titleCase(approval.action) : `Approval #${getId(approval) || "unknown"}`,
      detail: joinDefined([
        titleCase(approval.status),
        approval.incident_id ? `Incident ${approval.incident_id}` : "",
      ]),
    });
  }

  for (const deadLetter of data.deadLetters || []) {
    entries.push({
      id: `dead-letter-${getId(deadLetter)}`,
      source: "Dead letter",
      tone: "danger",
      timestamp: firstTimestamp(deadLetter),
      title: deadLetter.failure_class || deadLetter.error_code || `Dead letter #${getId(deadLetter) || "unknown"}`,
      detail: joinDefined([
        titleCase(deadLetter.status),
        deadLetter.source_type,
        deadLetter.retryable === true ? "Retryable" : "",
      ]),
    });
  }

  for (const notification of data.notifications || []) {
    const status = String(notification.status || "").toLowerCase();
    if (FAILURE_STATUS.has(status)) {
      entries.push({
        id: `notification-${getId(notification)}`,
        source: "Notification",
        tone: "danger",
        timestamp: firstTimestamp(notification),
        title: notification.adapter_name || notification.provider || "Notification delivery",
        detail: joinDefined([
          titleCase(notification.status),
          notification.mode ? `Mode ${notification.mode}` : "",
          notification.failure_class || notification.failure_code,
        ]),
      });
    }
  }

  for (const queueItem of data.queueItems || []) {
    const status = String(queueItem.status || "").toLowerCase();
    if (["running", "failed", "pending", "awaiting_approval", "recovered"].includes(status)) {
      entries.push({
        id: `queue-${getId(queueItem)}`,
        source: "Worker",
        tone: status === "failed" ? "danger" : status === "pending" ? "warning" : "info",
        timestamp: firstTimestamp(queueItem),
        title: queueItem.playbook_id || queueItem.action || `Queue item #${getId(queueItem) || "unknown"}`,
        detail: joinDefined([
          titleCase(queueItem.status),
          queueItem.incident_id ? `Incident ${queueItem.incident_id}` : "",
        ]),
      });
    }
  }

  return entries
    .filter((entry) => entry.timestamp || entry.title)
    .sort((a, b) => new Date(b.timestamp || 0).getTime() - new Date(a.timestamp || 0).getTime())
    .slice(0, FEED_LIMIT);
}

export function deriveAttentionItems(data) {
  const playbookStatuses = data.playbookMetrics?.by_status || {};
  const pendingApprovals = metricCount(data.approvalMetrics, ["pending_count", "by_status.pending"]);
  const staleExecutions =
    metricCount(data.workerMetrics, ["stale_running_count", "running.stale"]) ||
    metricCount(data.playbookMetrics, ["stale_running_count"]);
  const activeDeadLetters =
    metricCount(data.deadLetterMetrics, ["open"]) +
    metricCount(data.deadLetterMetrics, ["retrying"]);
  const failedPlaybooks =
    toNumber(playbookStatuses.failed) ||
    (data.executions || []).filter((item) => String(item.status || "").toLowerCase() === "failed").length;
  const notificationFailures =
    metricCount(data.notificationMetrics, ["recent.failed"]) +
    metricCount(data.notificationMetrics, ["recent.timeout"]) +
    metricCount(data.notificationMetrics, ["recent.blocked"]) ||
    (data.notifications || []).filter((item) =>
      FAILURE_STATUS.has(String(item.status || "").toLowerCase())
    ).length;
  const queuePressure =
    metricCount(data.workerMetrics, ["queue_depth.active_total"]) ||
    metricCount(data.queueStatus, ["counts.pending"]) +
      metricCount(data.queueStatus, ["counts.running"]) +
      metricCount(data.queueStatus, ["counts.awaiting_approval"]);
  const integrationSummary = deriveIntegrationSummary(data.integrationStatus);

  const items = [
    {
      label: "Stale running executions",
      value: staleExecutions,
      status: staleExecutions > 0 ? "Needs review" : "Clear",
      severity: staleExecutions > 0 ? "danger" : "success",
      navLabel: "Stale running executions",
    },
    {
      label: "Pending approvals",
      value: pendingApprovals,
      status: pendingApprovals > 0 ? "Actionable" : "Clear",
      severity: pendingApprovals > 0 ? "warning" : "success",
      navLabel: "Pending approvals",
    },
    {
      label: "Open or retrying dead letters",
      value: activeDeadLetters,
      status: activeDeadLetters > 0 ? "Review retryability" : "Clear",
      severity: activeDeadLetters > 0 ? "danger" : "success",
      navLabel: "Open or retrying dead letters",
    },
    {
      label: "Failed playbooks",
      value: failedPlaybooks,
      status: failedPlaybooks > 0 ? "Investigate" : "Clear",
      severity: failedPlaybooks > 0 ? "danger" : "success",
      navLabel: "Failed playbooks",
    },
    {
      label: "Notification failures",
      value: notificationFailures,
      status: notificationFailures > 0 ? "Delivery degraded" : "Clear",
      severity: notificationFailures > 0 ? "danger" : "success",
      navLabel: "Notification failures",
    },
    {
      label: "Queue pressure",
      value: queuePressure,
      status: queuePressure > 0 ? "Active work" : "Clear",
      severity: queuePressure > 10 ? "warning" : "info",
      navLabel: "Queue pressure",
    },
    {
      label: "Degraded integrations",
      value: integrationSummary.blockedCount,
      status: integrationSummary.blockedCount > 0 ? "Safety gate active" : "Clear",
      severity: integrationSummary.blockedCount > 0 ? "warning" : "success",
      navLabel: "Degraded integrations",
    },
  ];

  return items.slice(0, ATTENTION_LIMIT);
}

function buildSummaryCards(data) {
  const openIncidents =
    metricCount(data.incidentMetrics, ["open_high_critical"]) ||
    metricCount(data.incidentMetrics, ["by_status.open"]) +
      metricCount(data.incidentMetrics, ["by_status.investigating"]) ||
    (data.incidents || []).filter((item) =>
      ["open", "investigating", "new"].includes(String(item.status || "").toLowerCase())
    ).length;
  const activeAutomations =
    metricCount(data.playbookMetrics, ["by_status.running"]) +
      metricCount(data.playbookMetrics, ["by_status.pending"]) +
      metricCount(data.playbookMetrics, ["by_status.awaiting_approval"]) ||
    (data.executions || []).filter((item) =>
      ACTIVE_EXECUTION_STATUS.has(String(item.status || "").toLowerCase())
    ).length;
  const pendingApprovals = metricCount(data.approvalMetrics, ["pending_count", "by_status.pending"]);
  const activeDeadLetters =
    metricCount(data.deadLetterMetrics, ["open"]) +
      metricCount(data.deadLetterMetrics, ["retrying"]) ||
    (data.deadLetters || []).filter((item) =>
      ACTIVE_DEAD_LETTER_STATUS.has(String(item.status || "").toLowerCase())
    ).length;
  const notificationFailures =
    metricCount(data.notificationMetrics, ["recent.failed"]) +
      metricCount(data.notificationMetrics, ["recent.timeout"]) +
      metricCount(data.notificationMetrics, ["recent.blocked"]) ||
    buildFailureSources((data.notifications || []).map((item) => item.status)).length;
  const workerStatus =
    data.workerMetrics?.daemon_health?.status ||
    (metricCount(data.workerMetrics, ["running.stale", "stale_running_count"]) > 0
      ? "degraded"
      : "available");
  const integrationSummary = deriveIntegrationSummary(data.integrationStatus);

  return [
    {
      label: "Incident pressure",
      value: openIncidents,
      detail: "Open and high-priority incidents",
      tone: openIncidents > 0 ? "danger" : "success",
    },
    {
      label: "Active automations",
      value: activeAutomations,
      detail: "Pending, running, and approval-gated playbooks",
      tone: activeAutomations > 0 ? "info" : "success",
    },
    {
      label: "Pending approvals",
      value: pendingApprovals,
      detail: "Human decisions waiting",
      tone: pendingApprovals > 0 ? "warning" : "success",
    },
    {
      label: "Dead-letter pressure",
      value: activeDeadLetters,
      detail: "Open or retrying failures",
      tone: activeDeadLetters > 0 ? "danger" : "success",
    },
    {
      label: "Notification health",
      value: notificationFailures,
      detail: "Recent failed, blocked, or timed out deliveries",
      tone: notificationFailures > 0 ? "danger" : "success",
    },
    {
      label: "Worker health",
      value: titleCase(workerStatus),
      detail: "Queue and stale execution posture",
      tone: String(workerStatus).toLowerCase().includes("healthy") ? "success" : "info",
    },
    {
      label: "Integration safety",
      value:
        integrationSummary.realEnabledCount > 0
          ? `${integrationSummary.realEnabledCount} real-enabled`
          : "Simulation",
      detail: `${integrationSummary.adapterCount} adapters, ${integrationSummary.blockedCount} blocked`,
      tone: integrationSummary.realEnabledCount > 0 ? "warning" : "info",
    },
  ];
}

async function settleSource(label, loader) {
  try {
    return { label, status: "fulfilled", value: await loader() };
  } catch (err) {
    return {
      label,
      status: "rejected",
      reason: err?.message || "Unavailable",
      value: null,
    };
  }
}

function sourceFailureMap(results) {
  return results
    .filter((result) => result.status === "rejected")
    .reduce((acc, result) => {
      acc[result.label] = result.reason;
      return acc;
    }, {});
}

function StatusBadge({ tone = "info", children }) {
  return <span style={{ ...badgeStyle, ...badgeToneStyles[tone] }}>{children}</span>;
}

function useViewportWidth() {
  const getWidth = () =>
    typeof window === "undefined" ? 1200 : window.innerWidth || 1200;
  const [width, setWidth] = useState(getWidth);

  useEffect(() => {
    if (typeof window === "undefined") return undefined;
    const onResize = () => setWidth(getWidth());
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  return width;
}

function SummaryCard({ card }) {
  return (
    <div style={summaryCardStyle}>
      <div style={summaryCardHeaderStyle}>
        <p style={summaryLabelStyle}>{card.label}</p>
        <StatusBadge tone={card.tone}>{card.tone === "success" ? "Clear" : titleCase(card.tone)}</StatusBadge>
      </div>
      <p style={summaryValueStyle}>{card.value}</p>
      <p style={summaryDetailStyle}>{card.detail}</p>
    </div>
  );
}

function EmptyState({ children }) {
  return <p style={emptyTextStyle}>{children}</p>;
}

function SocCommandCenter({
  alerts = [],
  userRole,
  currentUsername,
  onNavigate,
  onOpenAttentionItem = null,
  onOpenResponseRegistry = null,
}) {
  const canOperate = ACTION_ROLES.has(userRole);
  const [data, setData] = useState(emptyCommandData);
  const [loading, setLoading] = useState(true);
  const [hasLoadedOnce, setHasLoadedOnce] = useState(false);
  const [refreshError, setRefreshError] = useState("");
  const [sourceErrors, setSourceErrors] = useState({});
  const [selectedIncidentId, setSelectedIncidentId] = useState(null);
  const [incidentContext, setIncidentContext] = useState({
    detail: null,
    timeline: [],
    notifications: [],
    loading: false,
    error: "",
  });
  const [selectedSourceIp, setSelectedSourceIp] = useState(null);
  const viewportWidth = useViewportWidth();
  const useSingleColumn = viewportWidth < 980;
  const useCompactWorkspace = viewportWidth < 760;

  const loadCommandData = useCallback(async () => {
    if (!canOperate) return;
    setLoading(true);
    setRefreshError("");

    const results = await Promise.all([
      settleSource("incidents", () => loadIncidents({ limit: SOURCE_LIMIT })),
      settleSource("playbook executions", () => listPlaybookExecutions({ limit: SOURCE_LIMIT })),
      settleSource("approvals", () => listApprovals({ limit: SOURCE_LIMIT })),
      settleSource("dead letters", () => getDeadLetters({ limit: SOURCE_LIMIT })),
      settleSource("notification deliveries", () =>
        listNotificationDeliveries({ limit: SOURCE_LIMIT })
      ),
      settleSource("queue activity", () => loadRecentSoarQueueItems({ limit: SOURCE_LIMIT })),
      settleSource("incident metrics", () => getIncidentMetrics()),
      settleSource("playbook metrics", () => getPlaybookMetrics()),
      settleSource("approval metrics", () => getApprovalMetrics()),
      settleSource("dead letter metrics", () => getDeadLetterMetrics()),
      settleSource("notification metrics", () => getNotificationDeliveryMetrics()),
      settleSource("worker metrics", () => getPlaybookWorkerMetrics()),
      settleSource("queue status", () => loadSoarQueueStatus()),
      settleSource("integration status", () => getIntegrationStatus()),
    ]);

    const byLabel = Object.fromEntries(results.map((result) => [result.label, result]));
    const failures = sourceFailureMap(results);
    let nextIncidents = data.incidents;

    setData((current) => {
      nextIncidents =
        byLabel.incidents?.status === "fulfilled"
          ? normalizeItems(byLabel.incidents.value, ["incidents"])
          : current.incidents;
      return {
        incidents: nextIncidents,
        executions:
          byLabel["playbook executions"]?.status === "fulfilled"
            ? normalizeItems(byLabel["playbook executions"].value, ["items", "executions"])
            : current.executions,
        approvals:
          byLabel.approvals?.status === "fulfilled"
            ? normalizeItems(byLabel.approvals.value, ["approvals"])
            : current.approvals,
        deadLetters:
          byLabel["dead letters"]?.status === "fulfilled"
            ? normalizeItems(byLabel["dead letters"].value, ["items", "dead_letters"])
            : current.deadLetters,
        notifications:
          byLabel["notification deliveries"]?.status === "fulfilled"
            ? normalizeItems(byLabel["notification deliveries"].value, ["items"])
            : current.notifications,
        queueItems:
          byLabel["queue activity"]?.status === "fulfilled"
            ? normalizeItems(byLabel["queue activity"].value, ["items"])
            : current.queueItems,
        incidentMetrics:
          byLabel["incident metrics"]?.status === "fulfilled"
            ? byLabel["incident metrics"].value || {}
            : current.incidentMetrics,
        playbookMetrics:
          byLabel["playbook metrics"]?.status === "fulfilled"
            ? byLabel["playbook metrics"].value || {}
            : current.playbookMetrics,
        approvalMetrics:
          byLabel["approval metrics"]?.status === "fulfilled"
            ? byLabel["approval metrics"].value || {}
            : current.approvalMetrics,
        deadLetterMetrics:
          byLabel["dead letter metrics"]?.status === "fulfilled"
            ? byLabel["dead letter metrics"].value || {}
            : current.deadLetterMetrics,
        notificationMetrics:
          byLabel["notification metrics"]?.status === "fulfilled"
            ? byLabel["notification metrics"].value || {}
            : current.notificationMetrics,
        workerMetrics:
          byLabel["worker metrics"]?.status === "fulfilled"
            ? byLabel["worker metrics"].value || {}
            : current.workerMetrics,
        queueStatus:
          byLabel["queue status"]?.status === "fulfilled"
            ? byLabel["queue status"].value || {}
            : current.queueStatus,
        integrationStatus:
          byLabel["integration status"]?.status === "fulfilled"
            ? byLabel["integration status"].value || {}
            : current.integrationStatus,
      };
    });
    setSourceErrors(failures);
    setLoading(false);
    setHasLoadedOnce(true);
    setRefreshError(Object.values(failures).join("; "));

    setSelectedIncidentId((current) => {
      if (current && nextIncidents.some((incident) => String(incident.id) === String(current))) {
        return current;
      }
      return nextIncidents[0]?.id ?? null;
    });
  }, [canOperate, data.incidents]);

  useEffect(() => {
    loadCommandData();
  }, [loadCommandData]);

  useEffect(() => {
    if (!selectedIncidentId || !canOperate) {
      setIncidentContext({
        detail: null,
        timeline: [],
        notifications: [],
        loading: false,
        error: "",
      });
      return;
    }

    let isCurrent = true;
    setIncidentContext((current) => ({ ...current, loading: true, error: "" }));

    Promise.all([
      settleSource("incident detail", () => loadIncidentDetail(selectedIncidentId)),
      settleSource("incident timeline", () => loadIncidentTimeline(selectedIncidentId)),
      settleSource("incident notifications", () =>
        listIncidentNotificationDeliveries(selectedIncidentId, { limit: SOURCE_LIMIT })
      ),
    ]).then((results) => {
      if (!isCurrent) return;
      const byLabel = Object.fromEntries(results.map((result) => [result.label, result.value]));
      const errors = sourceFailureMap(results);
      setIncidentContext({
        detail: normalizeIncident(byLabel["incident detail"]),
        timeline: normalizeItems(byLabel["incident timeline"], ["timeline"]),
        notifications: normalizeItems(byLabel["incident notifications"], ["items"]),
        loading: false,
        error: Object.values(errors).join("; "),
      });
    });

    return () => {
      isCurrent = false;
    };
  }, [canOperate, selectedIncidentId]);

  const selectedIncident = useMemo(() => {
    const listed = data.incidents.find((incident) => String(incident.id) === String(selectedIncidentId));
    return incidentContext.detail || listed || null;
  }, [data.incidents, incidentContext.detail, selectedIncidentId]);

  const linkedAlerts = useMemo(
    () => findLinkedAlerts(alerts, selectedIncident),
    [alerts, selectedIncident]
  );
  const relatedApprovals = useMemo(
    () => filterByIncident(data.approvals, selectedIncident?.id),
    [data.approvals, selectedIncident]
  );
  const relatedDeadLetters = useMemo(
    () => filterByIncident(data.deadLetters, selectedIncident?.id),
    [data.deadLetters, selectedIncident]
  );
  const relatedExecutions = useMemo(
    () => filterByIncident(data.executions, selectedIncident?.id),
    [data.executions, selectedIncident]
  );

  const summaryCards = useMemo(() => buildSummaryCards(data), [data]);
  const canonicalOutcomeCounts = useMemo(
    () =>
      mergeCanonicalOutcomeCounts(
        data.playbookMetrics?.canonical_outcome_counts,
        data.incidentMetrics?.canonical_outcome_counts,
        data.approvalMetrics?.canonical_outcome_counts,
        data.notificationMetrics?.canonical_outcome_counts
      ),
    [data.approvalMetrics, data.incidentMetrics, data.notificationMetrics, data.playbookMetrics]
  );
  const feed = useMemo(() => buildActivityFeed(data), [data]);
  const attentionItems = useMemo(() => deriveAttentionItems(data), [data]);
  const integrationSummary = useMemo(
    () => deriveIntegrationSummary(data.integrationStatus),
    [data.integrationStatus]
  );
  const sourceErrorLabels = Object.keys(sourceErrors);
  const initialLoadFailed =
    hasLoadedOnce &&
    sourceErrorLabels.length > 0 &&
    data.incidents.length === 0 &&
    data.executions.length === 0 &&
    data.approvals.length === 0 &&
    data.deadLetters.length === 0 &&
    data.notifications.length === 0 &&
    data.queueItems.length === 0 &&
    Object.keys(data.incidentMetrics || {}).length === 0 &&
    Object.keys(data.playbookMetrics || {}).length === 0 &&
    Object.keys(data.approvalMetrics || {}).length === 0 &&
    Object.keys(data.deadLetterMetrics || {}).length === 0 &&
    Object.keys(data.notificationMetrics || {}).length === 0 &&
    Object.keys(data.workerMetrics || {}).length === 0 &&
    Object.keys(data.queueStatus || {}).length === 0 &&
    Object.keys(data.integrationStatus || {}).length === 0;

  if (!canOperate) {
    return (
      <section style={panelStyle}>
        <div style={panelHeaderStyle}>
          <div>
            <p style={sectionLabelStyle}>SOC Command Center</p>
            <h2 style={titleStyle}>Operational command center</h2>
            <p style={subtitleStyle}>
              Viewer and auditor roles can use the dashboard but cannot access operational SOAR controls.
            </p>
          </div>
          <StatusBadge tone="info">Read-only role</StatusBadge>
        </div>
      </section>
    );
  }

  return (
    <section style={panelStyle}>
      <div style={panelHeaderStyle}>
        <div>
          <p style={sectionLabelStyle}>SOC Command Center</p>
          <h2 style={titleStyle}>Operational command center</h2>
          <p style={subtitleStyle}>
            Unified SOC pressure, SOAR safety, delivery health, and incident context for {currentUsername || "analyst"}.
          </p>
        </div>
        <div style={headerActionsStyle}>
          <StatusBadge tone={integrationSummary.realEnabledCount > 0 ? "warning" : "info"}>
            {integrationSummary.realEnabledCount > 0 ? "Guarded Real-Capable" : "Simulation-Safe Execution"}
          </StatusBadge>
          <button type="button" onClick={loadCommandData} style={secondaryButtonStyle}>
            {loading ? "Refreshing..." : "Refresh"}
          </button>
        </div>
      </div>

      {!hasLoadedOnce || (loading && !hasLoadedOnce) ? (
        <WorkspaceInitialState
          loading
          error=""
          loadingLabel="Loading SOC command center…"
        />
      ) : null}

      {initialLoadFailed ? (
        <WorkspaceInitialState
          loading={false}
          error="Unable to load SOC command center."
          errorLabel="Unable to load SOC command center."
          onRetry={loadCommandData}
        />
      ) : null}

      {hasLoadedOnce && !initialLoadFailed ? (
        <WorkspaceRefreshState refreshing={loading} refreshError={!loading ? refreshError : ""} />
      ) : null}

      {hasLoadedOnce && !initialLoadFailed && sourceErrorLabels.length > 0 ? (
        <div style={warningBannerStyle} role="status">
          Partial data loaded. Unavailable sources: {sourceErrorLabels.join(", ")}.
        </div>
      ) : null}

      {hasLoadedOnce && !initialLoadFailed ? (
        <>
          <div style={summaryGridStyle}>
            {summaryCards.map((card) => (
              <SummaryCard key={card.label} card={card} />
            ))}
          </div>

          <CanonicalOutcomeBreakdown
            counts={canonicalOutcomeCounts}
            title="Canonical SOAR outcome counts"
          />

          <div
            style={{
              ...mainGridStyle,
              gridTemplateColumns: useSingleColumn
                ? "minmax(0, 1fr)"
                : mainGridStyle.gridTemplateColumns,
            }}
          >
            <div style={leftColumnStyle}>
          <section style={cardStyle} aria-labelledby="attention-heading">
            <div style={cardHeaderStyle}>
              <div>
                <p style={sectionLabelStyle}>Operations</p>
                <h3 id="attention-heading" style={cardTitleStyle}>What needs attention?</h3>
              </div>
              {typeof onNavigate === "function" ? (
                <button
                  type="button"
                  onClick={() => onNavigate("soar-operations")}
                  style={linkButtonStyle}
                >
                  Open SOAR Operations
                </button>
              ) : null}
            </div>
            <div style={attentionListStyle}>
              {attentionItems.map((item) => (
                <div key={item.label} style={attentionItemStyle}>
                  <div>
                    <p style={attentionLabelStyle}>{item.label}</p>
                    <p style={attentionStatusStyle}>{item.status}</p>
                    {typeof onOpenAttentionItem === "function" ? (
                      <button
                        type="button"
                        style={linkButtonStyle}
                        onClick={() => onOpenAttentionItem(item.navLabel || item.label)}
                      >
                        Open workspace
                      </button>
                    ) : null}
                  </div>
                  <div style={attentionValueWrapStyle}>
                    <strong style={attentionValueStyle}>{item.value}</strong>
                    <StatusBadge tone={item.severity}>{titleCase(item.severity)}</StatusBadge>
                  </div>
                </div>
              ))}
            </div>
          </section>

          <section style={cardStyle} aria-labelledby="incident-heading">
            <div style={cardHeaderStyle}>
              <div>
                <p style={sectionLabelStyle}>Incident Workspace</p>
                <h3 id="incident-heading" style={cardTitleStyle}>Selected incident</h3>
              </div>
            </div>
            <div
              style={{
                ...workspaceGridStyle,
                gridTemplateColumns: useCompactWorkspace
                  ? "minmax(0, 1fr)"
                  : workspaceGridStyle.gridTemplateColumns,
              }}
            >
              <div
                style={{
                  ...incidentListStyle,
                  borderRight: useCompactWorkspace ? "none" : incidentListStyle.borderRight,
                  borderBottom: useCompactWorkspace ? "1px solid #30363d" : "none",
                }}
              >
                {loading && data.incidents.length === 0 ? (
                  <EmptyState>Loading incidents...</EmptyState>
                ) : data.incidents.length === 0 ? (
                  <EmptyState>No incidents available.</EmptyState>
                ) : (
                  data.incidents.slice(0, 8).map((incident) => (
                    <button
                      type="button"
                      key={incident.id || incident.title}
                      onClick={() => setSelectedIncidentId(incident.id)}
                      style={{
                        ...incidentButtonStyle,
                        ...(String(selectedIncidentId) === String(incident.id)
                          ? incidentButtonActiveStyle
                          : {}),
                      }}
                    >
                      <span style={incidentTitleStyle}>
                        {incident.title || `Incident #${valueOrFallback(incident.id, "unknown")}`}
                      </span>
                      <span style={incidentMetaStyle}>
                        {joinDefined([titleCase(incident.severity), titleCase(incident.status)])}
                      </span>
                    </button>
                  ))
                )}
              </div>
              <div style={incidentDetailStyle}>
                {incidentContext.loading ? (
                  <EmptyState>Loading incident context...</EmptyState>
                ) : selectedIncident ? (
                  <>
                    {incidentContext.error ? (
                      <div style={subtleWarningStyle}>
                        Some incident context is unavailable: {incidentContext.error}
                      </div>
                    ) : null}
                    <div style={incidentHeroStyle}>
                      <div>
                        <p style={sectionLabelStyle}>Incident #{valueOrFallback(selectedIncident.id, "unknown")}</p>
                        <h4 style={incidentHeroTitleStyle}>
                          {selectedIncident.title || "Untitled incident"}
                        </h4>
                      </div>
                      <StatusBadge tone={String(selectedIncident.severity || "").toLowerCase() === "critical" ? "danger" : "warning"}>
                        {titleCase(selectedIncident.severity)}
                      </StatusBadge>
                    </div>
                    <dl style={detailGridStyle}>
                      <div>
                        <dt style={detailTermStyle}>Status</dt>
                        <dd style={detailValueStyle}>{titleCase(selectedIncident.status)}</dd>
                      </div>
                      <div>
                        <dt style={detailTermStyle}>Priority</dt>
                        <dd style={detailValueStyle}>{valueOrFallback(selectedIncident.priority, "Unassigned")}</dd>
                      </div>
                      <div>
                        <dt style={detailTermStyle}>Assignment</dt>
                        <dd style={detailValueStyle}>{valueOrFallback(selectedIncident.assigned_to, "Unassigned")}</dd>
                      </div>
                      <div>
                        <dt style={detailTermStyle}>Source</dt>
                        <dd style={detailValueStyle}>
                          {selectedIncident.source_ip ? (
                            <button
                              type="button"
                              onClick={() => setSelectedSourceIp(selectedIncident.source_ip)}
                              style={sourceIpButtonStyle}
                              aria-label={`Open source-IP context for ${selectedIncident.source_ip}`}
                            >
                              {selectedIncident.source_ip}
                            </button>
                          ) : (
                            valueOrFallback(selectedIncident.source_ip)
                          )}
                        </dd>
                      </div>
                    </dl>
                    <div style={incidentOutcomeStyle}>
                      <p style={miniHeadingStyle}>Response outcome</p>
                      <ResponseOutcomeSummary outcome={selectedIncident.response_outcome || null} />
                    </div>
                    <div style={contextGridStyle}>
                      <ContextBlock label="Linked alerts" count={linkedAlerts.length} items={linkedAlerts} field="alert_type" />
                      <ContextBlock label="Playbooks" count={relatedExecutions.length} items={relatedExecutions} field="playbook_id" />
                      <ContextBlock label="Approvals" count={relatedApprovals.length} items={relatedApprovals} field="action" />
                      <ContextBlock label="Dead letters" count={relatedDeadLetters.length} items={relatedDeadLetters} field="failure_class" />
                      <ContextBlock label="Notifications" count={incidentContext.notifications.length} items={incidentContext.notifications} field="provider" />
                    </div>
                    <div style={timelineBlockStyle}>
                      <p style={miniHeadingStyle}>Timeline</p>
                      {incidentContext.timeline.length === 0 ? (
                        <EmptyState>No timeline events found for this incident.</EmptyState>
                      ) : (
                        incidentContext.timeline.slice(0, 5).map((event, index) => (
                          <div key={`${event.timestamp || event.created_at}-${index}`} style={timelineItemStyle}>
                            <span style={timelineDotStyle} />
                            <div>
                              <p style={timelineTitleStyle}>{event.event_type || event.type || "Timeline event"}</p>
                              <p style={timelineMetaStyle}>{formatRelative(firstTimestamp(event))}</p>
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                  </>
                ) : (
                  <EmptyState>Select an incident to view SOC context.</EmptyState>
                )}
              </div>
            </div>
          </section>
            </div>

            <aside style={rightColumnStyle}>
          <ExecutionSafetyModelPanel />

          <section style={cardStyle} aria-labelledby="feed-heading">
            <div style={cardHeaderStyle}>
              <div>
                <p style={sectionLabelStyle}>Global Activity</p>
                <h3 id="feed-heading" style={cardTitleStyle}>Live operations feed</h3>
              </div>
            </div>
            <div style={feedListStyle}>
              {loading && feed.length === 0 ? (
                <EmptyState>Loading activity...</EmptyState>
              ) : feed.length === 0 ? (
                <EmptyState>No recent operational activity found.</EmptyState>
              ) : (
                feed.map((entry) => (
                  <div key={entry.id} style={feedItemStyle}>
                    <div style={feedRailStyle}>
                      <span style={{ ...feedDotStyle, ...feedDotToneStyles[entry.tone] }} />
                    </div>
                    <div>
                      <div style={feedHeaderStyle}>
                        <StatusBadge tone={entry.tone}>{entry.source}</StatusBadge>
                        <span style={feedTimeStyle}>{formatRelative(entry.timestamp)}</span>
                      </div>
                      <p style={feedTitleStyle}>{entry.title}</p>
                      <p style={feedDetailStyle}>{entry.detail || "No additional metadata"}</p>
                    </div>
                  </div>
                ))
              )}
            </div>
          </section>

          <section style={cardStyle} aria-labelledby="safety-heading">
            <div style={cardHeaderStyle}>
              <div>
                <p style={sectionLabelStyle}>Safety</p>
                <h3 id="safety-heading" style={cardTitleStyle}>Integration posture</h3>
              </div>
            </div>
            <div style={safetyBodyStyle}>
              <div style={safetyModeStyle}>
                <StatusBadge tone={integrationSummary.realEnabledCount > 0 ? "warning" : "info"}>
                  {integrationSummary.mode === "real" ? "Guarded Real-Capable" : "Simulation-Safe Execution"}
                </StatusBadge>
                <p style={safetyTextStyle}>
                  {integrationSummary.realEnabledCount > 0
                    ? "Real-capable adapters are protected by per-adapter guard, audit, rate-limit, and dedup controls."
                    : "Workflows remain real; outbound adapter execution stays simulation-safe until per-adapter guards pass."}
                </p>
              </div>
              {getIntegrationAdapters(data.integrationStatus).length === 0 ? (
                <EmptyState>Integration status is unavailable or no adapters are registered.</EmptyState>
              ) : (
                getIntegrationAdapters(data.integrationStatus).slice(0, 6).map((adapter) => (
                  <div key={adapter.name || adapter.adapter_name} style={adapterRowStyle}>
                    <div>
                      <p style={adapterNameStyle}>{adapter.name || adapter.adapter_name || "Unnamed adapter"}</p>
                      <p style={adapterMetaStyle}>
                        {joinDefined([
                          adapter.mode_decision || adapter.mode || "simulation",
                          adapter.circuit_breaker?.state ? `circuit ${adapter.circuit_breaker.state}` : "",
                        ])}
                      </p>
                    </div>
                    <StatusBadge tone={adapter.real_enabled || adapter.real_mode_enabled ? "warning" : "info"}>
                      {adapter.real_enabled || adapter.real_mode_enabled ? "Guarded Real-Capable" : "Real Integration Disabled"}
                    </StatusBadge>
                  </div>
                ))
              )}
            </div>
          </section>
            </aside>
          </div>
        </>
      ) : null}

      {selectedSourceIp ? (
        <div
          style={sourceIpDrawerOverlayStyle}
          onClick={() => setSelectedSourceIp(null)}
          role="presentation"
        >
          <aside
            role="dialog"
            aria-modal="true"
            aria-labelledby="source-ip-context-drawer-title"
            style={sourceIpDrawerStyle}
            onClick={(event) => event.stopPropagation()}
          >
            <div style={sourceIpDrawerHeaderStyle}>
              <div>
                <p style={sectionLabelStyle}>Investigation</p>
                <h3 id="source-ip-context-drawer-title" style={sourceIpDrawerTitleStyle}>
                  Source-IP Context
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setSelectedSourceIp(null)}
                style={drawerCloseButtonStyle}
                aria-label="Close source-IP context drawer"
              >
                Close
              </button>
            </div>
            <div style={sourceIpDrawerBodyStyle}>
              <SourceIpContext sourceIp={selectedSourceIp} />
            </div>
          </aside>
        </div>
      ) : null}
    </section>
  );
}

function ContextBlock({ label, count, items, field }) {
  return (
    <div style={contextBlockStyle}>
      <div style={contextBlockHeaderStyle}>
        <p style={miniHeadingStyle}>{label}</p>
        <StatusBadge tone={count > 0 ? "info" : "success"}>{count}</StatusBadge>
      </div>
      {items.length === 0 ? (
        <p style={contextEmptyStyle}>No linked records.</p>
      ) : (
        items.slice(0, 3).map((item, index) => (
          <p key={`${label}-${getId(item) || index}`} style={contextItemStyle}>
            {valueOrFallback(item[field] || item.title || item.status, "Record")}
          </p>
        ))
      )}
    </div>
  );
}

const panelStyle = {
  display: "flex",
  flexDirection: "column",
  gap: "16px",
};

const panelHeaderStyle = {
  display: "flex",
  justifyContent: "space-between",
  gap: "16px",
  alignItems: "flex-start",
  flexWrap: "wrap",
  padding: "20px",
  border: "1px solid #30363d",
  borderRadius: "12px",
  backgroundColor: "#161b22",
};

const sectionLabelStyle = {
  margin: "0 0 6px 0",
  color: "#8b949e",
  fontSize: "11px",
  fontWeight: "800",
  letterSpacing: "0.08em",
  textTransform: "uppercase",
};

const titleStyle = {
  margin: 0,
  color: "#e6edf3",
  fontSize: "26px",
  fontWeight: "700",
};

const subtitleStyle = {
  margin: "8px 0 0 0",
  color: "#8b949e",
  fontSize: "14px",
  maxWidth: "760px",
  lineHeight: 1.45,
};

const headerActionsStyle = {
  display: "flex",
  alignItems: "center",
  gap: "10px",
  flexWrap: "wrap",
};

const secondaryButtonStyle = {
  border: "1px solid #30363d",
  backgroundColor: "#0d1117",
  color: "#e6edf3",
  borderRadius: "999px",
  padding: "8px 12px",
  fontSize: "12px",
  fontWeight: "800",
  cursor: "pointer",
};

const linkButtonStyle = {
  ...secondaryButtonStyle,
  color: "#93c5fd",
};

const warningBannerStyle = {
  padding: "12px 14px",
  border: "1px solid rgba(217, 164, 65, 0.36)",
  borderRadius: "10px",
  backgroundColor: "rgba(217, 164, 65, 0.12)",
  color: "#f5d487",
  fontSize: "13px",
  fontWeight: "700",
};

const summaryGridStyle = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))",
  gap: "12px",
};

const summaryCardStyle = {
  minHeight: "132px",
  padding: "14px",
  border: "1px solid #30363d",
  borderRadius: "10px",
  backgroundColor: "#161b22",
};

const summaryCardHeaderStyle = {
  display: "flex",
  justifyContent: "space-between",
  gap: "8px",
  alignItems: "center",
};

const summaryLabelStyle = {
  margin: 0,
  color: "#8b949e",
  fontSize: "12px",
  fontWeight: "800",
};

const summaryValueStyle = {
  margin: "18px 0 6px 0",
  color: "#e6edf3",
  fontSize: "28px",
  fontWeight: "800",
  lineHeight: 1.05,
};

const summaryDetailStyle = {
  margin: 0,
  color: "#8b949e",
  fontSize: "12px",
  lineHeight: 1.4,
};

const mainGridStyle = {
  display: "grid",
  gridTemplateColumns: "minmax(0, 1.45fr) minmax(330px, 0.75fr)",
  gap: "16px",
  alignItems: "start",
};

const leftColumnStyle = {
  display: "flex",
  flexDirection: "column",
  gap: "16px",
  minWidth: 0,
};

const rightColumnStyle = {
  display: "flex",
  flexDirection: "column",
  gap: "16px",
  minWidth: 0,
};

const cardStyle = {
  border: "1px solid #30363d",
  borderRadius: "12px",
  backgroundColor: "#161b22",
  overflow: "hidden",
};

const cardHeaderStyle = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  gap: "12px",
  padding: "16px",
  borderBottom: "1px solid #30363d",
  flexWrap: "wrap",
};

const cardTitleStyle = {
  margin: 0,
  color: "#e6edf3",
  fontSize: "18px",
  fontWeight: "800",
};

const attentionListStyle = {
  display: "grid",
  gap: "1px",
  backgroundColor: "#30363d",
};

const attentionItemStyle = {
  display: "flex",
  justifyContent: "space-between",
  gap: "12px",
  alignItems: "center",
  padding: "13px 16px",
  backgroundColor: "#161b22",
};

const attentionLabelStyle = {
  margin: "0 0 4px 0",
  color: "#e6edf3",
  fontSize: "13px",
  fontWeight: "800",
};

const attentionStatusStyle = {
  margin: 0,
  color: "#8b949e",
  fontSize: "12px",
};

const attentionValueWrapStyle = {
  display: "flex",
  alignItems: "center",
  gap: "8px",
};

const attentionValueStyle = {
  color: "#e6edf3",
  fontSize: "18px",
};

const workspaceGridStyle = {
  display: "grid",
  gridTemplateColumns: "minmax(220px, 0.36fr) minmax(0, 0.64fr)",
  minHeight: "520px",
};

const incidentListStyle = {
  borderRight: "1px solid #30363d",
  backgroundColor: "#0d1117",
  padding: "10px",
  display: "flex",
  flexDirection: "column",
  gap: "8px",
};

const incidentButtonStyle = {
  width: "100%",
  textAlign: "left",
  border: "1px solid #30363d",
  borderRadius: "8px",
  backgroundColor: "#161b22",
  color: "#e6edf3",
  padding: "10px",
  cursor: "pointer",
};

const incidentButtonActiveStyle = {
  border: "1px solid #58a6ff",
  backgroundColor: "rgba(31, 111, 235, 0.16)",
};

const incidentTitleStyle = {
  display: "block",
  fontSize: "13px",
  fontWeight: "800",
  lineHeight: 1.35,
};

const incidentMetaStyle = {
  display: "block",
  marginTop: "5px",
  color: "#8b949e",
  fontSize: "12px",
};

const incidentDetailStyle = {
  padding: "16px",
  minWidth: 0,
};

const incidentHeroStyle = {
  display: "flex",
  justifyContent: "space-between",
  gap: "12px",
  alignItems: "flex-start",
  marginBottom: "14px",
};

const incidentHeroTitleStyle = {
  margin: 0,
  color: "#e6edf3",
  fontSize: "18px",
  fontWeight: "800",
  lineHeight: 1.35,
};

const detailGridStyle = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))",
  gap: "10px",
  margin: "0 0 16px 0",
};

const detailTermStyle = {
  margin: "0 0 5px 0",
  color: "#8b949e",
  fontSize: "11px",
  fontWeight: "800",
  textTransform: "uppercase",
};

const detailValueStyle = {
  margin: 0,
  color: "#e6edf3",
  fontSize: "13px",
  fontWeight: "700",
};

const incidentOutcomeStyle = {
  marginBottom: "16px",
};

const sourceIpButtonStyle = {
  margin: 0,
  padding: 0,
  border: "none",
  background: "transparent",
  color: "#93c5fd",
  font: "inherit",
  fontWeight: "800",
  textDecoration: "underline",
  textUnderlineOffset: "3px",
  cursor: "pointer",
  overflowWrap: "anywhere",
  wordBreak: "break-word",
};

const contextGridStyle = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(min(150px, 100%), 1fr))",
  gap: "10px",
};

const contextBlockStyle = {
  border: "1px solid #30363d",
  borderRadius: "8px",
  padding: "10px",
  backgroundColor: "#0d1117",
  minHeight: "96px",
  minWidth: 0,
  boxSizing: "border-box",
};

const contextBlockHeaderStyle = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "flex-start",
  gap: "8px",
  minWidth: 0,
};

const miniHeadingStyle = {
  margin: "0 0 8px 0",
  color: "#c9d1d9",
  fontSize: "12px",
  fontWeight: "800",
  minWidth: 0,
  overflowWrap: "break-word",
};

const contextEmptyStyle = {
  margin: 0,
  color: "#8b949e",
  fontSize: "12px",
};

const contextItemStyle = {
  margin: "6px 0 0 0",
  color: "#e6edf3",
  fontSize: "12px",
  lineHeight: 1.35,
  minWidth: 0,
  whiteSpace: "normal",
  overflowWrap: "anywhere",
  wordBreak: "break-word",
};

const timelineBlockStyle = {
  marginTop: "16px",
};

const timelineItemStyle = {
  display: "grid",
  gridTemplateColumns: "14px minmax(0, 1fr)",
  gap: "8px",
  padding: "8px 0",
};

const timelineDotStyle = {
  width: "8px",
  height: "8px",
  marginTop: "5px",
  borderRadius: "50%",
  backgroundColor: "#58a6ff",
};

const timelineTitleStyle = {
  margin: 0,
  color: "#e6edf3",
  fontSize: "13px",
  fontWeight: "700",
};

const timelineMetaStyle = {
  margin: "3px 0 0 0",
  color: "#8b949e",
  fontSize: "12px",
};

const feedListStyle = {
  padding: "12px 16px 16px",
};

const feedItemStyle = {
  display: "grid",
  gridTemplateColumns: "18px minmax(0, 1fr)",
  gap: "10px",
  padding: "10px 0",
  borderBottom: "1px solid #30363d",
};

const feedRailStyle = {
  display: "flex",
  justifyContent: "center",
  paddingTop: "5px",
};

const feedDotStyle = {
  width: "9px",
  height: "9px",
  borderRadius: "50%",
  backgroundColor: "#58a6ff",
};

const feedDotToneStyles = {
  info: { backgroundColor: "#58a6ff" },
  warning: { backgroundColor: "#d29922" },
  danger: { backgroundColor: "#f85149" },
  success: { backgroundColor: "#3fb950" },
};

const feedHeaderStyle = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: "8px",
};

const feedTimeStyle = {
  color: "#8b949e",
  fontSize: "11px",
};

const feedTitleStyle = {
  margin: "7px 0 3px 0",
  color: "#e6edf3",
  fontSize: "13px",
  fontWeight: "800",
  lineHeight: 1.35,
};

const feedDetailStyle = {
  margin: 0,
  color: "#8b949e",
  fontSize: "12px",
  lineHeight: 1.35,
};

const safetyBodyStyle = {
  padding: "14px 16px 16px",
};

const safetyModeStyle = {
  paddingBottom: "12px",
  borderBottom: "1px solid #30363d",
};

const safetyTextStyle = {
  margin: "10px 0 0 0",
  color: "#8b949e",
  fontSize: "12px",
  lineHeight: 1.45,
};

const adapterRowStyle = {
  display: "flex",
  justifyContent: "space-between",
  gap: "12px",
  padding: "12px 0",
  borderBottom: "1px solid #30363d",
};

const adapterNameStyle = {
  margin: 0,
  color: "#e6edf3",
  fontSize: "13px",
  fontWeight: "800",
};

const adapterMetaStyle = {
  margin: "4px 0 0 0",
  color: "#8b949e",
  fontSize: "12px",
};

const subtleWarningStyle = {
  marginBottom: "12px",
  padding: "10px",
  border: "1px solid rgba(217, 164, 65, 0.32)",
  borderRadius: "8px",
  backgroundColor: "rgba(217, 164, 65, 0.10)",
  color: "#f5d487",
  fontSize: "12px",
};

const emptyTextStyle = {
  margin: 0,
  color: "#8b949e",
  fontSize: "13px",
  lineHeight: 1.45,
};

const badgeStyle = {
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  whiteSpace: "nowrap",
  borderRadius: "999px",
  padding: "4px 8px",
  fontSize: "10px",
  fontWeight: "800",
  textTransform: "uppercase",
};

const badgeToneStyles = {
  info: {
    color: "#93c5fd",
    border: "1px solid rgba(88, 166, 255, 0.34)",
    backgroundColor: "rgba(31, 111, 235, 0.14)",
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
  success: {
    color: "#86efac",
    border: "1px solid rgba(63, 185, 80, 0.34)",
    backgroundColor: "rgba(63, 185, 80, 0.14)",
  },
};

const sourceIpDrawerOverlayStyle = {
  position: "fixed",
  inset: 0,
  zIndex: 50,
  display: "flex",
  justifyContent: "flex-end",
  padding: "16px",
  backgroundColor: "rgba(13, 17, 23, 0.42)",
  boxSizing: "border-box",
};

const sourceIpDrawerStyle = {
  width: "min(420px, calc(100vw - 32px))",
  maxHeight: "calc(100vh - 32px)",
  display: "flex",
  flexDirection: "column",
  overflow: "hidden",
  border: "1px solid #30363d",
  borderRadius: "12px",
  backgroundColor: "#0d1117",
  boxShadow: "0 18px 48px rgba(0, 0, 0, 0.45)",
};

const sourceIpDrawerHeaderStyle = {
  flex: "0 0 auto",
  display: "flex",
  alignItems: "flex-start",
  justifyContent: "space-between",
  gap: "12px",
  padding: "16px",
  borderBottom: "1px solid #30363d",
  backgroundColor: "#161b22",
};

const sourceIpDrawerTitleStyle = {
  margin: 0,
  color: "#e6edf3",
  fontSize: "18px",
  fontWeight: "800",
};

const drawerCloseButtonStyle = {
  border: "1px solid #30363d",
  backgroundColor: "#0d1117",
  color: "#e6edf3",
  borderRadius: "999px",
  padding: "7px 10px",
  fontSize: "12px",
  fontWeight: "800",
  cursor: "pointer",
};

const sourceIpDrawerBodyStyle = {
  flex: "1 1 auto",
  minHeight: 0,
  overflowY: "auto",
  overflowX: "hidden",
  padding: "0 16px 16px",
  overscrollBehavior: "contain",
};

export default SocCommandCenter;
