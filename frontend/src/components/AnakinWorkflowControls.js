import React from "react";

import AiAssistantButton from "./AiAssistantButton";

export const ANAKIN_WORKFLOWS = Object.freeze({
  auto: "auto",
  quickExplain: "quick_explain",
  deepInvestigate: "deep_investigate",
  decisionSupport: "decision_support",
  generateArtifact: "generate_artifact",
});

const WORKFLOW_LABELS = {
  [ANAKIN_WORKFLOWS.auto]: "Ask Anakin",
  [ANAKIN_WORKFLOWS.quickExplain]: "Quick Explain",
  [ANAKIN_WORKFLOWS.deepInvestigate]: "Deep Investigate",
  [ANAKIN_WORKFLOWS.decisionSupport]: "Decision Support",
  [ANAKIN_WORKFLOWS.generateArtifact]: "Generate Artifact",
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
        <AiAssistantButton key={workflow} onClick={() => runWorkflow(workflow)}>
          {WORKFLOW_LABELS[workflow] || workflow}
        </AiAssistantButton>
      ))}
      {visibleArtifacts.length ? (
        <label style={artifactLabelStyle}>
          <span style={srOnlyStyle}>Generate Artifact</span>
          <select
            aria-label="Generate Artifact"
            defaultValue=""
            onChange={(event) => {
              runArtifact(event.target.value);
              event.target.value = "";
            }}
            style={selectStyle}
          >
            <option value="" disabled>Generate Artifact</option>
            {visibleArtifacts.map((artifact) => (
              <option key={artifact.type} value={artifact.type}>{artifact.label}</option>
            ))}
          </select>
        </label>
      ) : null}
    </div>
  );
}

function workflowTitle(workflow, titlePrefix) {
  if (workflow === ANAKIN_WORKFLOWS.auto) return `Ask Anakin: ${titlePrefix}`;
  if (workflow === ANAKIN_WORKFLOWS.quickExplain) return `Quick explain: ${titlePrefix}`;
  if (workflow === ANAKIN_WORKFLOWS.deepInvestigate) return `Deep investigate: ${titlePrefix}`;
  if (workflow === ANAKIN_WORKFLOWS.decisionSupport) return `Decision support: ${titlePrefix}`;
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
