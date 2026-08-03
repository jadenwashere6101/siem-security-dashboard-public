const ENTITY_CONTEXT_TYPES = new Set([
  "alert",
  "source_ip",
  "incident",
  "recon_activity",
  "response_registry",
  "detection",
]);

const ASYNC_WORKFLOWS = new Set([
  "auto",
  "deep_investigate",
  "decision_support",
  "generate_artifact",
]);

export function normalizeAnakinContextType(value) {
  return String(value || "").trim().toLowerCase().replaceAll("-", "_");
}

export function stableAnakinEntityId(context = {}) {
  if (!context || typeof context !== "object") return null;
  return (
    context.alert_id ??
    context.incident_id ??
    context.source_ip ??
    context.activity_id ??
    context.recon_activity_id ??
    context.registry_id ??
    context.investigation_id ??
    context.id ??
    context.rule_id ??
    null
  );
}

export function anakinConversationEntity(contextType, context = {}, activeSection = "dashboard") {
  const normalizedType = normalizeAnakinContextType(contextType);
  const entityId = stableAnakinEntityId(context);
  if (ENTITY_CONTEXT_TYPES.has(normalizedType) && entityId !== null) {
    const numericOnlyTypes = new Set([
      "alert",
      "incident",
      "recon_activity",
      "response_registry",
      "detection",
    ]);
    if (!numericOnlyTypes.has(normalizedType) || /^\d+$/.test(String(entityId))) {
      return { type: normalizedType, id: String(entityId) };
    }
  }
  if (normalizedType === "dashboard") return { type: "dashboard", id: "dashboard" };
  return { type: "general", id: String(entityId || activeSection || "workspace") };
}

export function isAsyncAnakinWorkflow(workflow) {
  return ASYNC_WORKFLOWS.has(workflow);
}

export function buildAnakinRequestContext({
  contextType,
  entityContext,
  activeSection,
  visibleContext,
  contextualCommand,
}) {
  const normalizedContextType = normalizeAnakinContextType(contextType);
  const shouldIncludeVisibleContext = !ENTITY_CONTEXT_TYPES.has(normalizedContextType);
  return {
    ...(shouldIncludeVisibleContext ? visibleContext : { active_section: activeSection }),
    command: {
      id: contextualCommand.id,
      label: contextualCommand.label,
      intent: contextualCommand.intent,
      read_only: contextualCommand.readOnly,
    },
    ...entityContext,
  };
}

export function buildAnakinWorkflowSubmission({
  options,
  activeSection,
  visibleContext,
  contextualCommand,
  conversation,
  clientRequestId,
}) {
  const normalizedContextType = normalizeAnakinContextType(options.contextType);
  const entityContext = options.context && typeof options.context === "object" ? options.context : {};
  const requestedWorkflow = options.artifactType ? "generate_artifact" : (options.workflow || "auto");
  const context = buildAnakinRequestContext({
    contextType: normalizedContextType,
    entityContext,
    activeSection,
    visibleContext,
    contextualCommand,
  });
  const entity = anakinConversationEntity(normalizedContextType, entityContext, activeSection);
  const payload = {
    workflow: requestedWorkflow,
    prompt: options.prompt || options.question || options.instruction || "",
    context_type: options.contextType,
    entity,
    context,
    artifact: options.artifactType ? { type: options.artifactType } : options.artifact,
    tool_policy: options.toolPolicy || (
      options.workflow === "deep_investigate"
        ? { max_tool_calls: 5, time_window_hours: 24 }
        : undefined
    ),
    client_request_id: clientRequestId,
    conversation,
  };
  return {
    payload,
    normalizedContextType,
    requestedWorkflow,
    usesAsyncWorkflowRoute: isAsyncAnakinWorkflow(requestedWorkflow),
    contextKey: JSON.stringify({
      contextType: normalizedContextType || "general",
      workflow: options.workflow || "",
      action: options.action || "",
      draftType: options.draftType || "",
      artifactType: options.artifactType || "",
      investigation: Boolean(options.investigation),
      entityId: stableAnakinEntityId(entityContext),
      command: contextualCommand.id,
    }),
    entityContext,
  };
}
