import React from "react";

import AiAssistantButton from "./AiAssistantButton";

export const ANAKIN_WORKFLOWS = Object.freeze({
  auto: "auto",
  quickExplain: "quick_explain",
  deepInvestigate: "deep_investigate",
  decisionSupport: "decision_support",
  generateArtifact: "generate_artifact",
});

export const WORKFLOW_TASKS = {
  [ANAKIN_WORKFLOWS.auto]: "Ask Anakin",
  [ANAKIN_WORKFLOWS.quickExplain]: "Explain this alert",
  [ANAKIN_WORKFLOWS.deepInvestigate]: "Investigate further",
  [ANAKIN_WORKFLOWS.decisionSupport]: "Recommend next action",
  [ANAKIN_WORKFLOWS.generateArtifact]: "Draft an analyst artifact",
};

export const WORKFLOW_TASK_DESCRIPTIONS = {
  [ANAKIN_WORKFLOWS.quickExplain]: "Fast explanation of why it fired and what to check next.",
  [ANAKIN_WORKFLOWS.deepInvestigate]: "Correlate related evidence, competing explanations, and gaps.",
  [ANAKIN_WORKFLOWS.decisionSupport]: "Read-only advice on monitor, escalate, or contain.",
  [ANAKIN_WORKFLOWS.generateArtifact]: "Create a preview-only analyst artifact for review.",
};

function AnakinWorkflowControls({
  contextType,
  context = {},
  controls = [],
  artifacts = [],
  titlePrefix = "Anakin",
  subject = "this SIEM context",
  onAskAi,
  showLabel = true,
}) {
  if (typeof onAskAi !== "function") return null;
  const visibleArtifacts = artifacts.filter(Boolean);

  const runWorkflow = (workflow) => {
    onAskAi({
      workflow,
      contextType,
      context,
      title: workflowTitle(workflow, titlePrefix),
      question: workflowQuestion(workflow, subject),
      toolPolicy: workflow === ANAKIN_WORKFLOWS.deepInvestigate
        ? { max_tool_calls: 5, time_window_hours: 24 }
        : undefined,
    });
  };

  const runArtifact = (artifactType) => {
    const artifact = visibleArtifacts.find((item) => item.type === artifactType);
    if (!artifact) return;
    onAskAi({
      workflow: ANAKIN_WORKFLOWS.generateArtifact,
      contextType: artifact.contextType || contextType,
      context,
      artifactType: artifact.type,
      title: artifact.title || `${artifact.label} for ${titlePrefix}`,
      instruction: artifact.instruction || `Generate a ${artifact.label.toLowerCase()} for analyst review only.`,
      toolPolicy: { max_tool_calls: 3, time_window_hours: 24 },
    });
  };

  return (
    <div style={controlsStyle}>
      {showLabel ? <span style={labelStyle}>Anakin</span> : null}
      {controls.map((workflow) => (
        <AiAssistantButton
          key={workflow}
          onClick={() => runWorkflow(workflow)}
          title={WORKFLOW_TASK_DESCRIPTIONS[workflow] || "Ask a question using the current context."}
          variant={workflow === ANAKIN_WORKFLOWS.auto ? "primary" : "secondary"}
        >
          {taskLabel(workflow, contextType)}
        </AiAssistantButton>
      ))}
      {visibleArtifacts.length ? (
        <label style={artifactLabelStyle}>
          <span style={srOnlyStyle}>Draft an analyst artifact</span>
          <select
            aria-label="Draft an analyst artifact"
            title={WORKFLOW_TASK_DESCRIPTIONS[ANAKIN_WORKFLOWS.generateArtifact]}
            defaultValue=""
            onChange={(event) => {
              runArtifact(event.target.value);
              event.target.value = "";
            }}
            style={selectStyle}
          >
            <option value="" disabled>Draft artifact</option>
            {visibleArtifacts.map((artifact) => (
              <option key={artifact.type} value={artifact.type}>{artifact.label}</option>
            ))}
          </select>
        </label>
      ) : null}
    </div>
  );
}

function taskLabel(workflow, contextType) {
  if (workflow !== ANAKIN_WORKFLOWS.quickExplain) {
    return WORKFLOW_TASKS[workflow] || workflow;
  }
  const nouns = {
    alert: "alert",
    source_ip: "source IP",
    incident: "incident",
    recon_activity: "activity",
    response_registry: "indicator",
    detection: "detection",
    dashboard: "current activity",
    general: "investigation",
  };
  return `Explain ${nouns[contextType] || "this context"}`;
}

function workflowTitle(workflow, titlePrefix) {
  if (workflow === ANAKIN_WORKFLOWS.auto) return `Ask Anakin: ${titlePrefix}`;
  if (workflow === ANAKIN_WORKFLOWS.quickExplain) return `Explain: ${titlePrefix}`;
  if (workflow === ANAKIN_WORKFLOWS.deepInvestigate) return `Investigate: ${titlePrefix}`;
  if (workflow === ANAKIN_WORKFLOWS.decisionSupport) return `Next action: ${titlePrefix}`;
  return titlePrefix;
}

function workflowQuestion(workflow, subject) {
  if (workflow === ANAKIN_WORKFLOWS.auto) {
    return `Review ${subject} and route this request to the safest useful Anakin workflow.`;
  }
  if (workflow === ANAKIN_WORKFLOWS.quickExplain) {
    return `Explain what matters about ${subject} using only the loaded SIEM context.`;
  }
  if (workflow === ANAKIN_WORKFLOWS.deepInvestigate) {
    return `Investigate ${subject}. Gather approved evidence, correlate it, identify benign explanations, missing evidence, confidence, and read-only next steps.`;
  }
  if (workflow === ANAKIN_WORKFLOWS.decisionSupport) {
    return `What should an analyst do about ${subject}: block, monitor, escalate, ignore, or gather more evidence? Explain reasoning and confidence without generating artifacts.`;
  }
  return `Review ${subject}.`;
}

const controlsStyle = {
  display: "flex",
  alignItems: "center",
  justifyContent: "flex-end",
  gap: "8px",
  flexWrap: "wrap",
};

const labelStyle = {
  color: "#93c5fd",
  fontSize: "11px",
  fontWeight: 800,
  letterSpacing: "0.04em",
  textTransform: "uppercase",
};

const artifactLabelStyle = { display: "inline-flex" };

const selectStyle = {
  border: "1px solid rgba(125, 211, 252, 0.45)",
  background: "#0f172a",
  color: "#ecfeff",
  borderRadius: "999px",
  padding: "7px 11px",
  fontSize: "12px",
  fontWeight: 800,
  cursor: "pointer",
};

const srOnlyStyle = {
  position: "absolute",
  width: "1px",
  height: "1px",
  padding: 0,
  margin: "-1px",
  overflow: "hidden",
  clip: "rect(0, 0, 0, 0)",
  whiteSpace: "nowrap",
  border: 0,
};

export default AnakinWorkflowControls;
