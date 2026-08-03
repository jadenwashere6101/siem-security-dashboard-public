import {
  buildCommandContext,
  commandToAiOptions,
  createDefaultAnakinCommands,
  normalizeContextualAiOptions,
} from "./anakinCommandRegistry";
import {
  anakinConversationEntity,
  buildAnakinWorkflowSubmission,
} from "./anakinConversationRequest";

const conversation = {
  thread_id: "thread-production-shape",
  expected_version: 1,
  client_request_id: "client-production-shape",
};

const threatBrief = {
  headline: "Scanning increased against internet-facing services",
  sections: [
    {
      title: "Network activity",
      items: [
        {
          alert: {
            id: 101,
            source: { ip: "198.51.100.10", metadata: { provider: "pfsense", labels: ["scan"] } },
          },
        },
      ],
    },
  ],
};

function visibleContext(activeSection = "dashboard") {
  return {
    active_section: activeSection,
    dashboard_summary: { totalAlerts: 37, highCount: 4, uniqueIPs: 8 },
    timeline: [{ bucket: "2026-08-02T12:00:00Z", count: 7 }],
    recent_alerts: [{ alert_id: 101, source_ip: "198.51.100.10" }],
    threat_brief: threatBrief,
  };
}

function submission(options, activeSection = "dashboard") {
  const contextualCommand = normalizeContextualAiOptions(options);
  return buildAnakinWorkflowSubmission({
    options,
    activeSection,
    visibleContext: visibleContext(activeSection),
    contextualCommand,
    conversation,
    clientRequestId: conversation.client_request_id,
  });
}

test("the real dashboard command path preserves rich workflow context", () => {
  const commandContext = buildCommandContext({
    activeSection: "dashboard",
    alertView: { operationalScope: "since_tuning" },
    selectedAlertId: 101,
    alerts: [{ id: 101, alert_type: "port_scan", source_ip: "198.51.100.10" }],
    metrics: { totalAlerts: 37 },
    currentUsername: "analyst1",
    userRole: "analyst",
    canTakeAlertActions: true,
    threatBrief,
  });
  const explain = createDefaultAnakinCommands().find((item) => item.workflow === "quick_explain");
  const options = commandToAiOptions(explain, commandContext, "Explain the current scan activity.");
  const result = submission(options);

  expect(result.payload.context.data.threatBrief.sections[0].items[0].alert.source.ip).toBe("198.51.100.10");
  expect(result.payload.entity).toEqual({ type: "dashboard", id: "dashboard" });
  expect(result.payload.conversation).toEqual(conversation);
});

test.each([
  ["Dashboard Ask Anakin", "dashboard", {}, "auto", "dashboard", "dashboard"],
  ["Dashboard Explain this alert", "alert", { alert_id: 101 }, "quick_explain", "alert", "101"],
  ["Alert Details", "alert", { alert_id: 101, alert: threatBrief.sections[0].items[0].alert }, "deep_investigate", "alert", "101"],
  ["Source IP", "source_ip", { source_ip: "198.51.100.10", events: threatBrief.sections }, "quick_explain", "source_ip", "198.51.100.10"],
  ["Incident", "incident", { incident_id: 44, incident: { evidence: threatBrief } }, "decision_support", "incident", "44"],
  ["SOC Command Center / Recon", "recon_activity", { activity_id: 90, activity: threatBrief }, "deep_investigate", "recon_activity", "90"],
  ["Response Registry", "response_registry", { registry_id: 12, response: threatBrief }, "decision_support", "response_registry", "12"],
  ["Analyst Workspace", "general", { investigation_id: 7, workspace: threatBrief }, "auto", "general", "7"],
  ["Generate Artifact preview", "alert", { alert_id: 101, alert: threatBrief }, "generate_artifact", "alert", "101"],
])("%s uses the canonical workflow submission", (_label, contextType, context, workflow, entityType, entityId) => {
  const options = {
    workflow,
    contextType,
    context,
    question: "What should I investigate next?",
    ...(workflow === "generate_artifact" ? { artifactType: "investigation_checklist" } : {}),
  };
  const result = submission(options, contextType);

  expect(result.payload.workflow).toBe(workflow);
  expect(result.payload.context_type).toBe(contextType);
  expect(result.payload.context).toMatchObject(context);
  expect(result.payload.entity).toEqual({ type: entityType, id: entityId });
  expect(result.payload.conversation.client_request_id).toBe(conversation.client_request_id);
  expect(anakinConversationEntity(contextType, context, contextType)).toEqual({ type: entityType, id: entityId });
  if (workflow === "generate_artifact") {
    expect(result.payload.artifact).toEqual({ type: "investigation_checklist" });
  }
});
