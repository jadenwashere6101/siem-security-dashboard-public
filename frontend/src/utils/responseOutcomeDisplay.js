export const EXECUTION_MODES = ["observed", "simulation", "tracking_only", "real"];

export const EXECUTION_STATES = [
  "observed",
  "selected",
  "queued",
  "awaiting_approval",
  "running",
  "skipped",
  "blocked",
  "succeeded",
  "failed",
];

export const REASON_CODES = [
  "approval_required",
  "approval_denied",
  "simulation_mode",
  "tracking_only",
  "adapter_unavailable",
  "provider_error",
  "policy_blocked",
  "duplicate_suppressed",
  "unsupported_action",
];

export const OUTCOME_TONES = {
  neutral: {
    color: "#c9d1d9",
    backgroundColor: "rgba(148, 163, 184, 0.10)",
    border: "1px solid rgba(148, 163, 184, 0.24)",
  },
  info: {
    color: "#93c5fd",
    backgroundColor: "rgba(59, 130, 246, 0.12)",
    border: "1px solid rgba(59, 130, 246, 0.30)",
  },
  success: {
    color: "#86efac",
    backgroundColor: "rgba(34, 197, 94, 0.12)",
    border: "1px solid rgba(34, 197, 94, 0.30)",
  },
  warning: {
    color: "#fcd34d",
    backgroundColor: "rgba(251, 191, 36, 0.12)",
    border: "1px solid rgba(251, 191, 36, 0.30)",
  },
  danger: {
    color: "#fca5a5",
    backgroundColor: "rgba(239, 68, 68, 0.14)",
    border: "1px solid rgba(239, 68, 68, 0.34)",
  },
};

const STATE_LABELS = {
  awaiting_approval: "Awaiting approval",
  blocked: "Blocked by approval",
  skipped: "Skipped",
  failed: "Failed",
  running: "Running",
  queued: "Queued",
  selected: "Selected",
};

const REASON_EXPLANATIONS = {
  approval_required: "Human approval is required before the response can continue.",
  approval_denied: "Approval denied or expired before enforcement.",
  simulation_mode: "Simulation mode completed without real provider or local enforcement.",
  tracking_only: "Recorded for SIEM tracking without provider or local enforcement.",
  adapter_unavailable: "Required adapter was unavailable.",
  provider_error: "Provider returned an error.",
  policy_blocked: "Policy prevented the selected response.",
  duplicate_suppressed: "Duplicate response was suppressed.",
  unsupported_action: "Selected action is not supported.",
};

export function outcomeLabel(outcome) {
  if (!outcome || !outcome.execution_mode) {
    return "Observed only";
  }

  const state = outcome.execution_state;
  const mode = outcome.execution_mode;

  if (STATE_LABELS[state]) {
    return STATE_LABELS[state];
  }
  if (state === "observed") {
    return "Observed only";
  }
  if (mode === "simulation" || outcome.simulated === true) {
    return "Simulated";
  }
  if (mode === "tracking_only" || outcome.tracking_recorded === true) {
    return "Tracking only";
  }
  if (mode === "real" && outcome.external_executed === true) {
    return "Real executed";
  }
  if (mode === "real") {
    return "Failed";
  }
  if (mode === "observed") {
    return "Observed only";
  }

  return "Observed only";
}

export function outcomeColor(outcome) {
  const label = outcomeLabel(outcome);

  if (label === "Real executed") return "success";
  if (label === "Simulated" || label === "Running" || label === "Queued") return "info";
  if (label === "Tracking only" || label === "Awaiting approval") return "warning";
  if (label === "Blocked by approval" || label === "Failed") return "danger";
  return "neutral";
}

export function outcomeToneStyle(outcome) {
  return OUTCOME_TONES[outcomeColor(outcome)] || OUTCOME_TONES.neutral;
}

export function formatOutcomeStatus(outcome) {
  if (!outcome) {
    return "Observed only";
  }

  const state = outcome.execution_state;
  const mode = outcome.execution_mode;

  if (state === "succeeded") {
    if (mode === "simulation" || outcome.simulated === true) {
      return "Simulated succeeded";
    }
    if (mode === "tracking_only" || outcome.tracking_recorded === true) {
      return "Tracking-only recorded";
    }
    if (mode === "real" && outcome.external_executed === true) {
      return "Real executed";
    }
  }

  return outcomeLabel(outcome);
}

export function formatOutcomeValue(value, fallback = "Unavailable") {
  if (value === undefined || value === null || value === "") {
    return fallback;
  }
  return String(value)
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function formatExecutionClauses(outcome) {
  return [
    outcome?.external_executed === true
      ? "Real execution confirmed"
      : "No real execution confirmed",
    outcome?.tracking_recorded === true
      ? "Tracking-only record created"
      : "No tracking-only record created",
    outcome?.simulated === true
      ? "Simulation completed without enforcement"
      : "Not marked as simulation",
  ];
}

export function reasonCodeExplanation(reasonCode) {
  return REASON_EXPLANATIONS[reasonCode] || "";
}

export function relatedOutcomeIds(outcome) {
  if (!outcome) return [];

  return [
    ["Alert id", outcome.alert_id ?? outcome.related?.alert_id],
    ["Queue id", outcome.queue_id ?? outcome.related?.queue_id],
    ["Playbook execution id", outcome.playbook_execution_id ?? outcome.related?.playbook_execution_id],
    ["Approval request id", outcome.approval_request_id ?? outcome.related?.approval_request_id],
    [
      "Notification delivery id",
      outcome.notification_delivery_id ||
        outcome.notification_delivery_attempt_id ||
        outcome.related?.notification_delivery_attempt_id,
    ],
  ];
}

const OUTCOME_COUNT_GROUP_ORDER = [
  "execution_mode",
  "execution_state",
  "external_executed",
  "tracking_recorded",
  "simulated",
];

const OUTCOME_COUNT_GROUP_LABELS = {
  execution_mode: "Execution mode",
  execution_state: "Execution state",
  external_executed: "External executed",
  tracking_recorded: "Tracking recorded",
  simulated: "Simulated",
};

export function outcomeCountEntryLabel(groupName, key) {
  if (groupName === "execution_mode") {
    return outcomeLabel({
      execution_mode: key,
      execution_state: "succeeded",
      external_executed: key === "real",
      tracking_recorded: key === "tracking_only",
      simulated: key === "simulation",
    });
  }
  if (groupName === "execution_state") {
    return outcomeLabel({
      execution_mode: "observed",
      execution_state: key,
    });
  }
  if (groupName === "external_executed") {
    return key === "true" ? "Real executed" : "Not real executed";
  }
  if (groupName === "tracking_recorded") {
    return key === "true" ? "Tracking only" : "Not tracking only";
  }
  if (groupName === "simulated") {
    return key === "true" ? "Simulated" : "Not simulated";
  }
  return formatOutcomeValue(key);
}

export function mergeCanonicalOutcomeCounts(...sources) {
  const merged = {};
  for (const source of sources) {
    if (!source || typeof source !== "object") continue;
    for (const [groupName, values] of Object.entries(source)) {
      if (!values || typeof values !== "object") continue;
      if (!merged[groupName]) merged[groupName] = {};
      for (const [key, count] of Object.entries(values)) {
        merged[groupName][key] = Number(merged[groupName][key] || 0) + Number(count || 0);
      }
    }
  }
  return merged;
}

export function hasCanonicalOutcomeCounts(counts) {
  if (!counts || typeof counts !== "object") return false;
  return OUTCOME_COUNT_GROUP_ORDER.some((groupName) => {
    const group = counts[groupName];
    if (!group || typeof group !== "object") return false;
    return Object.values(group).some((value) => Number(value) > 0);
  });
}

export function canonicalOutcomeCountSections(counts) {
  if (!counts || typeof counts !== "object") return [];
  return OUTCOME_COUNT_GROUP_ORDER.map((groupName) => ({
    groupName,
    title: OUTCOME_COUNT_GROUP_LABELS[groupName] || formatOutcomeValue(groupName),
    entries: Object.entries(counts[groupName] || {})
      .map(([key, count]) => ({
        key,
        count: Number(count) || 0,
        label: outcomeCountEntryLabel(groupName, key),
      }))
      .filter((entry) => entry.count > 0),
  })).filter((section) => section.entries.length > 0);
}

export function isTrackingOnlyOutcome(outcome) {
  if (!outcome) return false;
  return outcome.execution_mode === "tracking_only" || outcome.tracking_recorded === true;
}

export function buildCanonicalStepOutcomeLabels(responseOutcomes) {
  const labelsByStep = {};
  if (!Array.isArray(responseOutcomes)) return labelsByStep;
  for (const event of responseOutcomes) {
    const stepIndex = event?.playbook_step_index;
    if (stepIndex === null || stepIndex === undefined) continue;
    const normalizedIndex = Number(stepIndex);
    if (!Number.isFinite(normalizedIndex) || labelsByStep[normalizedIndex]) continue;
    labelsByStep[normalizedIndex] = outcomeLabel({
      execution_mode: event.execution_mode,
      execution_state: event.execution_state,
      external_executed: event.external_executed,
      tracking_recorded: event.tracking_recorded,
      simulated: event.simulated,
    });
  }
  return labelsByStep;
}
