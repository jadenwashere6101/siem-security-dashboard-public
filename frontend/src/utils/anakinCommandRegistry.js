export const ANAKIN_COMMAND_INTENTS = Object.freeze({
  ask: "ask",
  summarize: "summarize",
  investigate: "investigate",
  explain: "explain",
  draft: "draft",
  suggestedActions: "suggested_actions",
  navigate: "navigate",
  lookup: "lookup",
  filter: "filter",
  extension: "extension",
});

export const ANAKIN_EXTENSION_SLOTS = Object.freeze({
  analystWorkspace: "analyst_workspace",
  investigationDrawer: "investigation_drawer",
  threatStory: "threat_story",
  futureAiTools: "future_ai_tools",
});

const MUTATION_KEYWORDS = [
  "approve",
  "block",
  "delete",
  "disable",
  "enable",
  "execute",
  "mutate",
  "promote",
  "retry",
  "restart",
  "resolve",
  "save",
];

export function createCommandRegistry(commands = []) {
  const byId = new Map();
  const normalized = [];
  for (const command of commands.filter(Boolean)) {
    const normalizedCommand = {
      readOnly: true,
      group: "Anakin",
      contextTypes: [],
      keywords: [],
      ...command,
    };
    if (!normalizedCommand.id || byId.has(normalizedCommand.id)) continue;
    byId.set(normalizedCommand.id, normalizedCommand);
    normalized.push(normalizedCommand);
  }

  return {
    all: () => normalized,
    get: (id) => byId.get(id) || null,
    available: (context = {}) =>
      normalized.filter((command) => isCommandAvailable(command, context)),
    byGroup: (context = {}) => groupCommands(normalized.filter((command) => isCommandAvailable(command, context))),
  };
}

export function isCommandAvailable(command, context = {}) {
  if (!command) return false;
  if (command.requiredRole && command.requiredRole !== context.user?.role) return false;
  if (command.requiresCanOperate && !context.user?.canTakeAlertActions) return false;
  if (typeof command.availability === "function") {
    return command.availability(context) !== false;
  }
  return true;
}

export function groupCommands(commands = []) {
  const groups = new Map();
  for (const command of commands) {
    const group = command.group || "Other";
    if (!groups.has(group)) groups.set(group, []);
    groups.get(group).push(command);
  }
  return Array.from(groups.entries()).map(([group, items]) => ({ group, items }));
}

export function sanitizeCommandContext(context = {}) {
  const workspace = context.workspace || {};
  const object = context.object || {};
  const data = context.data || {};
  const user = context.user || {};

  return {
    workspace: {
      activeSection: workspace.activeSection || "",
      filters: workspace.filters || {},
      operationalScope: workspace.operationalScope || "",
    },
    object: {
      selectedAlertId: object.selectedAlertId || null,
      alert: sanitizeAlert(object.alert),
      sourceIp: object.sourceIp || "",
      incident: sanitizeIncident(object.incident),
      reconActivity: sanitizeReconActivity(object.reconActivity),
    },
    data: {
      metrics: data.metrics || null,
      visibleAlerts: Array.isArray(data.visibleAlerts)
        ? data.visibleAlerts.slice(0, 12).map(sanitizeAlert)
        : [],
      threatBrief: data.threatBrief || null,
      loading: Boolean(data.loading),
      error: data.error || "",
    },
    user: {
      username: user.username || "",
      role: user.role || "",
      canTakeAlertActions: Boolean(user.canTakeAlertActions),
    },
  };
}

export function buildCommandContext({
  activeSection,
  alertView,
  selectedAlertId,
  alerts,
  metrics,
  currentUsername,
  userRole,
  canTakeAlertActions,
  threatBrief,
} = {}) {
  const selectedAlert = Array.isArray(alerts)
    ? alerts.find((alert) => String(alert.alert_id ?? alert.id) === String(selectedAlertId))
    : null;

  return sanitizeCommandContext({
    workspace: {
      activeSection,
      filters: alertView,
      operationalScope: alertView?.operationalScope,
    },
    object: {
      selectedAlertId,
      alert: selectedAlert,
      sourceIp: selectedAlert?.source_ip || alertView?.exactSourceIp || "",
    },
    data: {
      metrics,
      visibleAlerts: alerts,
      threatBrief,
    },
    user: {
      username: currentUsername,
      role: userRole,
      canTakeAlertActions,
    },
  });
}

export function assertReadOnlyPaletteCommand(command) {
  const haystack = [
    command?.id,
    command?.label,
    command?.intent,
    ...(command?.keywords || []),
  ].join(" ").toLowerCase();
  const tokens = haystack.split(/[^a-z0-9]+/).filter(Boolean);
  const unsafe = command?.readOnly === false || MUTATION_KEYWORDS.some((word) => tokens.includes(word));
  return !unsafe;
}

export function createDefaultAnakinCommands() {
  return [
    {
      id: "anakin.ask",
      label: "Ask Anakin",
      group: "Anakin",
      intent: ANAKIN_COMMAND_INTENTS.ask,
      description: "Ask a read-only question using the current workspace context.",
      readOnly: true,
    },
    {
      id: "anakin.summarize",
      label: "Summarize",
      group: "Anakin",
      intent: ANAKIN_COMMAND_INTENTS.summarize,
      description: "Summarize the active analyst surface.",
      readOnly: true,
    },
    {
      id: "anakin.investigate",
      label: "Investigate",
      group: "Anakin",
      intent: ANAKIN_COMMAND_INTENTS.investigate,
      description: "Run a bounded read-only investigation.",
      readOnly: true,
      requiresCanOperate: true,
    },
    {
      id: "anakin.explain",
      label: "Explain",
      group: "Anakin",
      intent: ANAKIN_COMMAND_INTENTS.explain,
      description: "Explain selected data or the active workflow.",
      readOnly: true,
    },
    {
      id: "anakin.draft",
      label: "Draft",
      group: "Anakin",
      intent: ANAKIN_COMMAND_INTENTS.draft,
      description: "Draft a checklist or response recommendation without saving anything.",
      readOnly: true,
      requiresCanOperate: true,
    },
    {
      id: "anakin.suggested-actions",
      label: "Suggested Actions",
      group: "Anakin",
      intent: ANAKIN_COMMAND_INTENTS.suggestedActions,
      description: "Review deterministic next steps with optional AI explanation.",
      readOnly: true,
    },
  ];
}

export function createExtensionCommandSlots() {
  return Object.values(ANAKIN_EXTENSION_SLOTS).map((slot) => ({
    id: `extension.${slot}`,
    label: slot.replaceAll("_", " "),
    group: "Extensions",
    intent: ANAKIN_COMMAND_INTENTS.extension,
    extensionSlot: slot,
    readOnly: true,
    disabled: true,
    description: "Reserved extension point for a later OpenSpec phase.",
    availability: () => false,
  }));
}

export function commandToAiOptions(command, context = {}, question = "") {
  const active = context.workspace?.activeSection || "workspace";
  const baseContext = {
    command_id: command.id,
    command_intent: command.intent,
    workspace: context.workspace,
    object: context.object,
    data: context.data,
  };

  if (command.intent === ANAKIN_COMMAND_INTENTS.ask) {
    return {
      contextType: active,
      action: "ask_anakin",
      title: "Ask Anakin",
      question: question || "Answer a read-only analyst question about the current SIEM workspace.",
      context: baseContext,
    };
  }
  if (command.intent === ANAKIN_COMMAND_INTENTS.investigate) {
    return {
      contextType: active,
      action: "investigate",
      investigation: true,
      title: "Anakin investigation",
      question: "Run a bounded read-only investigation of the current context and identify source-cited next steps.",
      context: baseContext,
      toolPolicy: { max_tool_calls: 5, time_window_hours: 24 },
    };
  }
  if (command.intent === ANAKIN_COMMAND_INTENTS.draft) {
    return {
      contextType: active,
      draftType: "investigation_checklist",
      title: "Anakin draft",
      instruction: "Draft a read-only analyst checklist from the current context. Do not save or execute anything.",
      context: baseContext,
    };
  }
  return {
    contextType: active,
    action: command.intent,
    title: command.label,
    question: `Provide a read-only ${command.label.toLowerCase()} for the current SIEM context.`,
    context: baseContext,
  };
}

export function normalizeContextualAiOptions(options = {}) {
  const intent = contextualIntent(options);
  return {
    id: options.commandId || `contextual.${options.contextType || "workspace"}.${options.action || options.draftType || "ask"}`,
    label: options.title || options.action || options.draftType || "Ask Anakin",
    group: "Contextual AI",
    intent,
    readOnly: true,
    options,
  };
}

function contextualIntent(options) {
  if (options.draftType) return ANAKIN_COMMAND_INTENTS.draft;
  if (options.investigation) return ANAKIN_COMMAND_INTENTS.investigate;
  return options.action || ANAKIN_COMMAND_INTENTS.ask;
}

function sanitizeAlert(alert) {
  if (!alert) return null;
  return {
    id: alert.alert_id ?? alert.id ?? null,
    alert_type: alert.alert_type || "",
    severity: alert.severity || "",
    status: alert.status || "",
    source_ip: alert.source_ip || "",
    target_ip: alert.target_ip || "",
    timestamp: alert.timestamp || alert.created_at || "",
  };
}

function sanitizeIncident(incident) {
  if (!incident) return null;
  return {
    id: incident.id || incident.incident_id || null,
    title: incident.title || "",
    severity: incident.severity || "",
    status: incident.status || "",
    source_ip: incident.source_ip || "",
  };
}

function sanitizeReconActivity(activity) {
  if (!activity) return null;
  return {
    id: activity.id || null,
    label: activity.label || activity.display?.headline || "",
    status: activity.status || "",
    severity: activity.severity || "",
  };
}
