import { getSourceBadgeMeta as sharedSourceBadgeMeta } from "./alertDisplay";

export const formatCreatedAt = (value) => {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "UTC",
    timeZoneName: "short",
  }).format(date);
};

export const formatGroupDate = (value) => {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "Unknown Date";
  }

  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "2-digit",
    year: "numeric",
    timeZone: "UTC",
  }).format(date);
};

export const getEventTypeBadgeStyle = (eventType) => {
  const normalized = (eventType || "").toLowerCase();

  if (normalized === "failed_login" || normalized === "login_failure") {
    return {
      color: "#fbbf24",
      backgroundColor: "rgba(251, 191, 36, 0.10)",
      border: "1px solid rgba(251, 191, 36, 0.28)",
    };
  }

  if (normalized === "port_scan") {
    return {
      color: "#f87171",
      backgroundColor: "rgba(248, 113, 113, 0.10)",
      border: "1px solid rgba(248, 113, 113, 0.30)",
    };
  }

  if (normalized === "password_spray" || normalized === "successful_login_after_spray") {
    return {
      color: "#e879f9",
      backgroundColor: "rgba(232, 121, 249, 0.10)",
      border: "1px solid rgba(232, 121, 249, 0.30)",
    };
  }

  if (normalized === "successful_login") {
    return {
      color: "#93c5fd",
      backgroundColor: "rgba(59, 130, 246, 0.10)",
      border: "1px solid rgba(59, 130, 246, 0.25)",
    };
  }

  return {
    color: "#c9d1d9",
    backgroundColor: "rgba(148, 163, 184, 0.08)",
    border: "1px solid rgba(148, 163, 184, 0.20)",
  };
};

export const getSeverityBadgeStyle = (severity) => {
  const normalized = (severity || "").toLowerCase();

  if (normalized === "high") {
    return {
      color: "#f87171",
      backgroundColor: "rgba(248, 113, 113, 0.10)",
      border: "1px solid rgba(248, 113, 113, 0.28)",
    };
  }

  if (normalized === "medium") {
    return {
      color: "#fbbf24",
      backgroundColor: "rgba(251, 191, 36, 0.10)",
      border: "1px solid rgba(251, 191, 36, 0.26)",
    };
  }

  if (normalized === "low") {
    return {
      color: "#86efac",
      backgroundColor: "rgba(74, 222, 128, 0.10)",
      border: "1px solid rgba(74, 222, 128, 0.26)",
    };
  }

  return {
    color: "#c9d1d9",
    backgroundColor: "rgba(148, 163, 184, 0.08)",
    border: "1px solid rgba(148, 163, 184, 0.20)",
  };
};

export const getSourceBadgeMeta = (sourceValue, sourceTypeValue) =>
  sharedSourceBadgeMeta(
    sourceValue,
    sourceTypeValue,
    "1px solid rgba(148, 163, 184, 0.20)"
  );

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

export const formatRawPayload = (rawPayload) => {
  if (!rawPayload) {
    return "No raw_payload available for this event.";
  }

  try {
    return JSON.stringify(rawPayload, null, 2);
  } catch (_error) {
    return "Unable to display raw_payload.";
  }
};

export const groupEventsByDate = (events) => {
  return events.reduce((groups, event) => {
    const groupLabel = formatGroupDate(event.created_at);
    const existingGroup = groups.find((group) => group.label === groupLabel);

    if (existingGroup) {
      existingGroup.events.push(event);
      return groups;
    }

    groups.push({
      label: groupLabel,
      events: [event],
    });
    return groups;
  }, []);
};
