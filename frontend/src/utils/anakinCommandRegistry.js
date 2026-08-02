export const ANAKIN_COMMAND_INTENTS = Object.freeze({
  ask: "ask",
  quickExplain: "quick_explain",
  deepInvestigate: "deep_investigate",
  decisionSupport: "decision_support",
  generateArtifact: "generate_artifact",
  socBriefing: "soc_briefing",
  repoAssistant: "repo_assistant",
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
      id: "anakin.quick-explain",
      label: "Explain this alert",
      group: "Anakin",
      intent: ANAKIN_COMMAND_INTENTS.quickExplain,
      workflow: "quick_explain",
      description: "Fast explanation of why it fired and what to check next.",
      readOnly: true,
    },
    {
      id: "anakin.deep-investigate",
      label: "Investigate further",
      group: "Anakin",
      intent: ANAKIN_COMMAND_INTENTS.deepInvestigate,
      workflow: "deep_investigate",
      description: "Correlate related evidence, competing explanations, and gaps.",
      readOnly: true,
      requiresCanOperate: true,
    },
    {
      id: "anakin.decision-support",
      label: "Recommend next action",
      group: "Anakin",
      intent: ANAKIN_COMMAND_INTENTS.decisionSupport,
      workflow: "decision_support",
      description: "Read-only advice on monitor, escalate, or contain.",
      readOnly: true,
      requiresCanOperate: true,
    },
    {
      id: "anakin.generate-artifact",
      label: "Draft an analyst artifact",
      group: "Anakin",
      intent: ANAKIN_COMMAND_INTENTS.generateArtifact,
      workflow: "generate_artifact",
      description: "Create a preview-only analyst artifact for review.",
      readOnly: true,
      requiresCanOperate: true,
    },
    {
      id: "anakin.soc-briefing",
      label: "SOC Briefing",
      group: "Anakin",
      intent: ANAKIN_COMMAND_INTENTS.socBriefing,
      workflow: "soc_briefing",
      description: "Open SOC briefing controls.",
      readOnly: true,
      availability: (context) => context.workspace?.activeSection !== "soc-briefings",
    },
    {
      id: "anakin.repo-assistant",
      label: "Repo Assistant",
      group: "Anakin",
      intent: ANAKIN_COMMAND_INTENTS.repoAssistant,
      workflow: "repo_assistant",
      description: "Open cited repository architecture assistant.",
      readOnly: true,
      requiredRole: "super_admin",
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

  if (command.workflow === "soc_briefing" || command.workflow === "repo_assistant") return null;
  return {
    workflow: command.workflow || "auto",
    contextType: active,
    title: command.label,
    question: question || workflowQuestion(command.workflow, command.label),
    context: baseContext,
    artifactType: command.workflow === "generate_artifact" ? "investigation_checklist" : undefined,
    toolPolicy: command.workflow === "deep_investigate" ? { max_tool_calls: 5, time_window_hours: 24 } : undefined,
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
  if (options.workflow === "generate_artifact" || options.draftType || options.artifactType) return ANAKIN_COMMAND_INTENTS.generateArtifact;
  if (options.workflow === "deep_investigate" || options.investigation) return ANAKIN_COMMAND_INTENTS.deepInvestigate;
  if (options.workflow === "decision_support") return ANAKIN_COMMAND_INTENTS.decisionSupport;
  if (options.workflow === "quick_explain") return ANAKIN_COMMAND_INTENTS.quickExplain;
  return options.action || ANAKIN_COMMAND_INTENTS.ask;
}

function workflowQuestion(workflow, label) {
  if (workflow === "quick_explain") return "Explain the current SIEM context using loaded evidence.";
  if (workflow === "deep_investigate") return "Run a bounded read-only investigation of the current context with evidence, gaps, confidence, and next steps.";
  if (workflow === "decision_support") return "Recommend what the analyst should do next without drafting or taking action.";
  if (workflow === "generate_artifact") return "Generate a review-only investigation checklist from the current context.";
  return `Provide ${String(label || "Anakin help").toLowerCase()} for the current SIEM context.`;
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
