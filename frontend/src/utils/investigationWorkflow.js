const severityRank = { critical: 5, high: 4, medium: 3, low: 2, info: 1 };

export function buildInvestigationContext({
  alert = null,
  incident = null,
  timeline = [],
  workspace = null,
  sourceIp = "",
  responseHistory = [],
  observations = [],
} = {}) {
  const normalizedAlert = alert || null;
  const normalizedIncident = incident || null;
  const normalizedTimeline = Array.isArray(timeline) ? timeline : [];
  const normalizedResponses = Array.isArray(responseHistory) ? responseHistory : [];
  const entities = deriveEntities(normalizedAlert, normalizedIncident, sourceIp);
  const detections = deriveDetections(normalizedAlert, normalizedTimeline);
  return {
    alert: normalizedAlert,
    incident: normalizedIncident,
    sourceIp: sourceIp || normalizedAlert?.source_ip || normalizedIncident?.source_ip || "",
    timeline: normalizedTimeline,
    responseHistory: normalizedResponses,
    entities,
    detections,
    observations: Array.isArray(observations) ? observations : [],
    workspace,
    completeness: {
      hasAlert: Boolean(normalizedAlert),
      hasIncident: Boolean(normalizedIncident),
      hasTimeline: normalizedTimeline.length > 0,
      hasResponses: normalizedResponses.length > 0,
      hasWorkspace: Boolean(workspace),
    },
  };
}

export function buildDrawerSections(context = {}) {
  const alert = context.alert || null;
  const incident = context.incident || null;
  return [
    {
      id: "alert-summary",
      title: "Alert summary",
      status: alert ? "available" : "unavailable",
      value: alert ? `${alert.alert_type || "Alert"} #${alert.id ?? alert.alert_id ?? "unknown"}` : "No alert selected",
      detail: alert ? [alert.severity, alert.source_ip, alert.status].filter(Boolean).join(" • ") : "Open from an alert to populate this section.",
    },
    {
      id: "incident-summary",
      title: "Incident summary",
      status: incident ? "available" : "unavailable",
      value: incident ? incident.title || `Incident #${incident.id}` : "No incident linked",
      detail: incident ? [incident.severity, incident.priority, incident.status].filter(Boolean).join(" • ") : "No authoritative incident is linked in the current context.",
    },
    {
      id: "timeline",
      title: "Timeline",
      status: context.timeline?.length ? "available" : "partial",
      value: context.timeline?.length ? `${context.timeline.length} evidence event${context.timeline.length === 1 ? "" : "s"}` : "Timeline incomplete",
      detail: context.timeline?.length ? "Ordered from existing alert/incident timeline data." : "No timeline service data is loaded for this investigation.",
    },
    {
      id: "enrichment",
      title: "Enrichment summary",
      status: alert?.reputation_label || alert?.internet_noise ? "available" : "unavailable",
      value: alert?.reputation_label || alert?.internet_noise?.classification || "No enrichment loaded",
      detail: alert?.reputation_summary || "External or behavioral enrichment is unavailable in the selected context.",
    },
    {
      id: "entities",
      title: "Related entities",
      status: context.entities?.length ? "available" : "unavailable",
      value: context.entities?.length ? `${context.entities.length} related entit${context.entities.length === 1 ? "y" : "ies"}` : "No related entities",
      detail: context.entities?.map((entity) => entity.value).join(", ") || "No source, target, user, or incident entities are available.",
    },
    {
      id: "detections",
      title: "Related detections",
      status: context.detections?.length ? "available" : "unavailable",
      value: context.detections?.length ? context.detections.map((detection) => detection.label).join(", ") : "No related detections",
      detail: "Derived from selected alert and loaded timeline event types only.",
    },
    {
      id: "soar-history",
      title: "SOAR response history",
      status: context.responseHistory?.length ? "available" : "partial",
      value: context.responseHistory?.length ? `${context.responseHistory.length} response event${context.responseHistory.length === 1 ? "" : "s"}` : "No response history loaded",
      detail: context.responseHistory?.length ? "Read-only SOAR history from existing timeline inputs." : "No response history is loaded for this investigation.",
    },
    {
      id: "next-steps",
      title: "Recommended next steps",
      status: alert || incident ? "available" : "unavailable",
      value: deriveNextStep(alert, incident),
      detail: "Deterministic recommendation from selected alert/incident context.",
    },
  ];
}

export function buildThreatStory(context = {}) {
  const alert = context.alert || null;
  const incident = context.incident || null;
  const timeline = Array.isArray(context.timeline) ? [...context.timeline] : [];
  const progression = timeline
    .filter((entry) => entry?.event_type || entry?.title || entry?.summary)
    .sort((a, b) => String(a.timestamp || "").localeCompare(String(b.timestamp || "")))
    .map((entry, index) => ({
      id: `${entry.event_type || "event"}-${index}`,
      label: entry.title || entry.event_type || "Evidence event",
      detail: entry.summary || entry.source || "No summary available.",
      timestamp: entry.timestamp || "",
      source: entry.source || "timeline",
    }));

  return {
    sections: [
      {
        id: "what-happened",
        title: "What happened",
        status: alert || incident ? "available" : "incomplete",
        body: alert
          ? `${alert.alert_type || "An alert"} fired for ${alert.source_ip || "an unknown source"}.`
          : incident
          ? `${incident.title || "An incident"} is currently ${incident.status || "open"}.`
          : "No selected alert or incident is available.",
        source: alert ? "alert" : incident ? "incident" : "missing",
      },
      {
        id: "why-it-mattered",
        title: "Why it mattered",
        status: alert || incident ? "available" : "incomplete",
        body: deriveWhyItMattered(alert, incident),
        source: alert ? "alert severity" : incident ? "incident priority" : "missing",
      },
      {
        id: "affected-entities",
        title: "Affected entities",
        status: context.entities?.length ? "available" : "incomplete",
        body: context.entities?.length ? context.entities.map((entity) => `${entity.label}: ${entity.value}`).join("; ") : "No affected entities are available.",
        source: "selected context",
      },
      {
        id: "detections-triggered",
        title: "Detections triggered",
        status: context.detections?.length ? "available" : "incomplete",
        body: context.detections?.length ? context.detections.map((detection) => detection.label).join(", ") : "No detection list is available.",
        source: "alert/timeline",
      },
      {
        id: "soar-actions",
        title: "SOAR actions",
        status: context.responseHistory?.length ? "available" : "incomplete",
        body: context.responseHistory?.length ? context.responseHistory.map((entry) => entry.summary || entry.title).filter(Boolean).join("; ") : "No SOAR response history is loaded.",
        source: "response history",
      },
      {
        id: "analyst-observations",
        title: "Analyst observations",
        status: context.observations?.length ? "available" : "incomplete",
        body: context.observations?.length ? context.observations.map((note) => note.body || note.note_text).filter(Boolean).join("; ") : "No private analyst observations have been saved.",
        source: "analyst workspace",
      },
      {
        id: "current-status",
        title: "Current investigation status",
        status: incident || alert ? "available" : "incomplete",
        body: incident?.status ? `Incident is ${incident.status}.` : alert?.status ? `Alert is ${alert.status}.` : "No status is available.",
        source: incident ? "incident" : alert ? "alert" : "missing",
      },
    ],
    progression,
    progressionStatus: progression.length ? "available" : "incomplete",
  };
}

export function deriveEntities(alert, incident, sourceIp) {
  const entities = [];
  const add = (label, value) => {
    if (value !== null && value !== undefined && String(value).trim()) {
      entities.push({ label, value: String(value) });
    }
  };
  add("Source IP", sourceIp || alert?.source_ip || incident?.source_ip);
  add("Target IP", alert?.target_ip || alert?.context?.target_ip);
  add("Alert ID", alert?.id ?? alert?.alert_id);
  add("Incident ID", incident?.id);
  add("Source", alert?.source);
  return entities;
}

export function deriveDetections(alert, timeline = []) {
  const detections = new Map();
  if (alert?.alert_type) detections.set(alert.alert_type, { label: alert.alert_type, source: "alert" });
  for (const entry of timeline || []) {
    const label = entry?.event_type || entry?.title;
    if (label && String(label).includes("alert")) {
      detections.set(label, { label, source: entry.source || "timeline" });
    }
  }
  return Array.from(detections.values());
}

function deriveNextStep(alert, incident) {
  if (incident?.status === "open" || incident?.status === "investigating") {
    return `Review incident ${incident.id} evidence and confirm current response history.`;
  }
  if (alert) {
    return `Review ${alert.alert_type || "alert"} evidence from ${alert.source_ip || "unknown source"}.`;
  }
  return "Select an alert or incident to generate a deterministic next step.";
}

function deriveWhyItMattered(alert, incident) {
  const severity = String(alert?.severity || incident?.severity || "").toLowerCase();
  if ((severityRank[severity] || 0) >= severityRank.high) {
    return "High-severity evidence can represent material risk and should be triaged before lower-severity activity.";
  }
  if (incident?.priority) {
    return `Incident priority ${incident.priority} requires analyst review before closure.`;
  }
  return "The available evidence is incomplete, so risk cannot be inferred beyond loaded data.";
}
