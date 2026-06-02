export const getSourceBadgeMeta = (source, sourceType) => {
  const normalizedSource = (source || "").toLowerCase();

  if (normalizedSource === "bank_app") {
    return {
      label: "App / Bank",
      subLabel: sourceType || "custom",
      style: {
        color: "#93c5fd",
        backgroundColor: "rgba(59, 130, 246, 0.10)",
        border: "1px solid rgba(59, 130, 246, 0.28)",
      },
    };
  }

  if (normalizedSource === "nginx") {
    return {
      label: "Web Log",
      subLabel: sourceType || "web_log",
      style: {
        color: "#fbbf24",
        backgroundColor: "rgba(251, 191, 36, 0.10)",
        border: "1px solid rgba(251, 191, 36, 0.28)",
      },
    };
  }

  if (normalizedSource === "azure_insights") {
    return {
      label: "Azure",
      subLabel: sourceType || "cloud_api",
      style: {
        color: "#67e8f9",
        backgroundColor: "rgba(103, 232, 249, 0.10)",
        border: "1px solid rgba(103, 232, 249, 0.26)",
      },
    };
  }

  if (normalizedSource === "opentelemetry") {
    return {
      label: "OTEL",
      subLabel: sourceType || "telemetry",
      style: {
        color: "#c4b5fd",
        backgroundColor: "rgba(196, 181, 253, 0.10)",
        border: "1px solid rgba(196, 181, 253, 0.26)",
      },
    };
  }

  return {
    label: "Unknown",
    subLabel: sourceType || "Legacy",
    style: {
      color: "#c9d1d9",
      backgroundColor: "rgba(148, 163, 184, 0.10)",
      border: "1px solid rgba(148, 163, 184, 0.22)",
    },
  };
};

export const getReputationBadgeStyle = (label) => {
  const normalized = (label || "").toLowerCase();

  if (normalized === "critical") {
    return {
      color: "#fecaca",
      backgroundColor: "rgba(239, 68, 68, 0.16)",
      border: "1px solid rgba(239, 68, 68, 0.34)",
    };
  }

  if (normalized === "high risk") {
    return {
      color: "#fca5a5",
      backgroundColor: "rgba(248, 113, 113, 0.12)",
      border: "1px solid rgba(248, 113, 113, 0.28)",
    };
  }

  if (normalized === "suspicious") {
    return {
      color: "#fcd34d",
      backgroundColor: "rgba(251, 191, 36, 0.12)",
      border: "1px solid rgba(251, 191, 36, 0.28)",
    };
  }

  if (normalized === "low suspicion") {
    return {
      color: "#bfdbfe",
      backgroundColor: "rgba(59, 130, 246, 0.10)",
      border: "1px solid rgba(59, 130, 246, 0.24)",
    };
  }

  return {
    color: "#86efac",
    backgroundColor: "rgba(74, 222, 128, 0.10)",
    border: "1px solid rgba(74, 222, 128, 0.24)",
  };
};

export const getBehavioralReputation = (alert) => {
  const behavioral = alert?.behavioral_reputation || {};

  return {
    score: behavioral.score ?? alert?.reputation_score ?? 0,
    label: behavioral.label || alert?.reputation_label || "Normal",
    source: behavioral.source || "siem_internal",
    summary:
      behavioral.summary ||
      alert?.reputation_summary ||
      "No behavioral reputation details available.",
    contributing_signals: Array.isArray(behavioral.contributing_signals)
      ? behavioral.contributing_signals
      : Array.isArray(alert?.contributing_signals)
        ? alert.contributing_signals
        : [],
  };
};

export const getExternalReputation = (alert) => ({
  score: alert?.reputation_score,
  label: alert?.reputation_label || "Unknown",
  source: alert?.reputation_source || "unknown",
  summary: alert?.reputation_summary || "No external threat intelligence details available.",
});

export const isCorrelationAlert = (alert) =>
  alert?.is_correlation_alert || alert?.alert_type === "correlated_activity";

export const getCorrelationAlertTypes = (alert) =>
  Array.isArray(alert?.correlated_alert_types) ? alert.correlated_alert_types : [];

export const buildSelectedAlertTimeline = (selectedAlert, alerts) =>
  selectedAlert?.source_ip
    ? alerts
        .filter((candidate) => candidate.source_ip === selectedAlert.source_ip)
        .slice()
        .sort((a, b) => new Date(a.created_at) - new Date(b.created_at))
    : [];
