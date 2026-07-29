export const OPERATIONAL_FEED_GROUPS = Object.freeze({
  Incident: { label: "Incident", tone: "danger" },
  Worker: { label: "Worker", tone: "warning" },
  Approval: { label: "Approval", tone: "warning" },
  Notification: { label: "Notification", tone: "danger" },
  Playbook: { label: "Playbook", tone: "info" },
});

const GROUP_ORDER = ["Incident", "Worker", "Approval", "Notification", "Playbook"];

function firstTimestamp(item) {
  return (
    item?.updated_at ||
    item?.created_at ||
    item?.completed_at ||
    item?.started_at ||
    item?.timestamp ||
    item?.last_seen_at ||
    ""
  );
}

function getId(item) {
  return item?.id || item?.incident_id || item?.execution_id || item?.queue_id || item?.alert_id || "";
}

function titleCase(value) {
  return String(value || "Unknown")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function joinDefined(parts) {
  return parts.filter((part) => part !== undefined && part !== null && part !== "").join(" • ");
}

function toneForExecution(status) {
  const normalized = String(status || "").toLowerCase();
  if (["failed", "permanently_failed", "timeout", "blocked"].includes(normalized)) return "danger";
  if (["awaiting_approval", "pending"].includes(normalized)) return "warning";
  if (["succeeded", "completed"].includes(normalized)) return "success";
  return "info";
}

function normalizeEntry(entry) {
  const source = OPERATIONAL_FEED_GROUPS[entry.source] ? entry.source : "Worker";
  return {
    ...entry,
    group: source,
    source,
    tone: entry.tone || OPERATIONAL_FEED_GROUPS[source].tone,
    timestamp: entry.timestamp || "",
    relatedObjectLabel: entry.relatedObjectLabel || "",
    actionTarget: entry.actionTarget || null,
  };
}

export function buildOperationalFeedEntries(data = {}) {
  const entries = [];

  for (const incident of data.incidents || []) {
    entries.push(normalizeEntry({
      id: `incident-${getId(incident)}`,
      source: "Incident",
      tone: "danger",
      timestamp: firstTimestamp(incident),
      title: incident.title || `Incident #${getId(incident) || "unknown"}`,
      detail: joinDefined([titleCase(incident.severity), titleCase(incident.status), incident.source_ip]),
      relatedObjectLabel: getId(incident) ? `Incident ${getId(incident)}` : "",
    }));
  }

  for (const execution of data.executions || []) {
    entries.push(normalizeEntry({
      id: `execution-${getId(execution)}`,
      source: "Playbook",
      tone: toneForExecution(execution.status),
      timestamp: firstTimestamp(execution),
      title: execution.playbook_id || execution.playbook_name || `Execution #${getId(execution) || "unknown"}`,
      detail: joinDefined([titleCase(execution.status), execution.incident_id ? `Incident ${execution.incident_id}` : ""]),
      relatedObjectLabel: getId(execution) ? `Execution ${getId(execution)}` : "",
    }));
  }

  for (const approval of data.approvals || []) {
    entries.push(normalizeEntry({
      id: `approval-${getId(approval)}`,
      source: "Approval",
      tone: String(approval.status || "").toLowerCase() === "pending" ? "warning" : "info",
      timestamp: firstTimestamp(approval),
      title: approval.action ? titleCase(approval.action) : `Approval #${getId(approval) || "unknown"}`,
      detail: joinDefined([titleCase(approval.status), approval.incident_id ? `Incident ${approval.incident_id}` : ""]),
      relatedObjectLabel: getId(approval) ? `Approval ${getId(approval)}` : "",
    }));
  }

  for (const notification of data.notifications || []) {
    const status = String(notification.status || "").toLowerCase();
    if (!["failed", "timeout", "blocked", "skipped"].includes(status)) continue;
    entries.push(normalizeEntry({
      id: `notification-${getId(notification)}`,
      source: "Notification",
      tone: "danger",
      timestamp: firstTimestamp(notification),
      title: notification.adapter_name || notification.provider || `Notification #${getId(notification) || "unknown"}`,
      detail: joinDefined([titleCase(notification.status), notification.mode ? `Mode ${notification.mode}` : "", notification.failure_class]),
      relatedObjectLabel: getId(notification) ? `Notification ${getId(notification)}` : "",
    }));
  }

  for (const deadLetter of data.deadLetters || []) {
    entries.push(normalizeEntry({
      id: `dead-letter-${getId(deadLetter)}`,
      source: "Worker",
      tone: "danger",
      timestamp: firstTimestamp(deadLetter),
      title: deadLetter.failure_class || deadLetter.error_code || `Dead letter #${getId(deadLetter) || "unknown"}`,
      detail: joinDefined([
        titleCase(deadLetter.status),
        deadLetter.source_type,
        deadLetter.retryable === true ? "Retryable" : "",
      ]),
      relatedObjectLabel: getId(deadLetter) ? `Dead letter ${getId(deadLetter)}` : "",
    }));
  }

  for (const queueItem of data.queueItems || []) {
    const status = String(queueItem.status || "").toLowerCase();
    if (!["running", "failed", "pending", "awaiting_approval", "recovered"].includes(status)) continue;
    entries.push(normalizeEntry({
      id: `queue-${getId(queueItem)}`,
      source: "Worker",
      tone: status === "failed" ? "danger" : status === "pending" ? "warning" : "info",
      timestamp: firstTimestamp(queueItem),
      title: queueItem.playbook_id || queueItem.action || `Queue item #${getId(queueItem) || "unknown"}`,
      detail: joinDefined([titleCase(queueItem.status), queueItem.incident_id ? `Incident ${queueItem.incident_id}` : ""]),
      relatedObjectLabel: getId(queueItem) ? `Queue ${getId(queueItem)}` : "",
    }));
  }

  return entries.sort((a, b) => new Date(b.timestamp || 0) - new Date(a.timestamp || 0));
}

export function groupOperationalFeedEntries(entries = []) {
  const groups = new Map(GROUP_ORDER.map((group) => [group, []]));
  for (const entry of entries) {
    const group = OPERATIONAL_FEED_GROUPS[entry.group] ? entry.group : "Worker";
    groups.get(group).push(entry);
  }
  return GROUP_ORDER.map((group) => ({
    id: group,
    label: OPERATIONAL_FEED_GROUPS[group].label,
    tone: OPERATIONAL_FEED_GROUPS[group].tone,
    items: groups.get(group) || [],
  }));
}
