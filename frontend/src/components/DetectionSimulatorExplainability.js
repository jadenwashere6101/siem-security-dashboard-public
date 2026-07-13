import React from "react";

// Pure presentation over the backend's stage payload. Every fact rendered
// here (matched/not-matched, threshold values, disclosures, alert/MITRE/SOAR
// fields) is read directly from the response the real pipeline produced --
// this component explains that outcome, it never recomputes or guesses one.
function DetectionSimulatorExplainability({ stages }) {
  if (!stages) return null;

  const entries = [
    parserExplanation(stages.parser),
    normalizedEventExplanation(stages.normalized_event, stages.parser),
    applicabilityExplanation(stages.detection_applicability),
    thresholdExplanation(stages.threshold_window_evaluation),
    alertExplanation(stages.alert_preview),
    mitreExplanation(stages.mitre_mapping),
    soarExplanation(stages.soar_preview),
  ].filter(Boolean);

  if (entries.length === 0) {
    return <p style={emptyStyle}>No explanation available for this run.</p>;
  }

  return (
    <dl style={listStyle} data-testid="detection-simulator-explainability">
      {entries.map((entry) => (
        <div key={entry.key} style={entryStyle} data-explain={entry.key}>
          <dt style={termStyle}>{entry.title}</dt>
          <dd style={descriptionStyle}>{entry.body}</dd>
        </div>
      ))}
    </dl>
  );
}

function parserExplanation(parserStage) {
  if (!parserStage) return null;
  if (parserStage.status === "succeeded") {
    const failedCount = (parserStage.results || []).filter((r) => r.status === "failed").length;
    return {
      key: "parser",
      title: "Parser",
      body: failedCount > 0
        ? `Parsed successfully, but ${failedCount} pasted item(s) failed to parse and were skipped.`
        : "All pasted input parsed successfully using the real production parser for this source.",
    };
  }
  if (parserStage.status === "failed") {
    const errors = (parserStage.results || [])
      .filter((r) => r.status === "failed")
      .map((r) => r.error)
      .filter(Boolean);
    return {
      key: "parser",
      title: "Parser failure",
      body: errors.length > 0
        ? `No pasted input could be parsed: ${errors.join("; ")}`
        : "No pasted input could be parsed by the selected source's parser.",
    };
  }
  return null;
}

function normalizedEventExplanation(normalizedStage, parserStage) {
  if (!normalizedStage) return null;
  if (normalizedStage.status === "succeeded") {
    const count = (normalizedStage.events || []).length;
    return {
      key: "normalized_event",
      title: "Normalization",
      body: `${count} event${count === 1 ? "" : "s"} normalized into the internal event schema using the real production normalizer.`,
    };
  }
  if (normalizedStage.status === "skipped" && parserStage?.status === "failed") {
    return {
      key: "normalized_event",
      title: "Normalization failure",
      body: "Normalization did not run because no pasted input parsed successfully.",
    };
  }
  return null;
}

function applicabilityExplanation(stage) {
  if (!stage) return null;
  const isTemporaryRule = Array.isArray(stage.allowed_condition_fields);
  if (stage.status === "failed") {
    return {
      key: "detection_applicability",
      title: "Rule not applicable",
      body: stage.reason || "The selected rule does not apply to the selected source.",
    };
  }
  if (stage.status === "succeeded" && isTemporaryRule) {
    return {
      key: "detection_applicability",
      title: "Playground rule applicability",
      body: `This temporary rule's condition and group-by fields are supported for source "${stage.source}".`,
    };
  }
  if (stage.status === "succeeded") {
    return {
      key: "detection_applicability",
      title: "Rule applicability",
      body: "The selected rule applies to the selected source.",
    };
  }
  return null;
}

function thresholdExplanation(stage) {
  if (!stage || stage.status !== "succeeded") return null;
  const parameters = stage.rule_parameters || {};
  const parameterText = Object.entries(parameters)
    .map(([key, value]) => `${key}=${value}`)
    .join(", ");

  const parts = [];
  if (stage.matched) {
    parts.push("Detection matched: this rule's threshold was reached and an alert would be created.");
  } else {
    parts.push("Detection not matched: this rule's threshold was not reached, so no alert would be created.");
  }
  if (parameterText) {
    parts.push(`Configured rule parameters: ${parameterText}.`);
  }
  if (Number.isInteger(stage.evaluated_window_minutes)) {
    parts.push(`Evaluated window: ${stage.evaluated_window_minutes} minute(s).`);
  }
  // Numeric evidence always comes from the backend's real detector
  // evaluation (see engines/detection_simulator.py's evidence-call
  // instrumentation) -- this component only renders it, never computes it.
  const isTemporaryRule = Array.isArray(stage.grouped_results);
  if (stage.evidence_available && Number.isInteger(stage.observed_value)) {
    const label = stage.observed_value_label ? stage.observed_value_label.replace(/_/g, " ") : "observed value";
    const thresholdText = Number.isInteger(stage.configured_threshold)
      ? ` (required: ${stage.configured_threshold})`
      : "";
    parts.push(`Observed ${label}: ${stage.observed_value}${thresholdText}.`);
  } else if (!stage.matched && !stage.existing_open_alert_for_rule && !isTemporaryRule) {
    parts.push("An exact observed value was not available for this evaluation.");
  }
  if (stage.existing_open_alert_for_rule) {
    parts.push(
      stage.note ||
        "An open alert already exists for this source and rule, which suppresses a new alert regardless of this simulation's threshold outcome."
    );
  }
  if (stage.blended_with_real_history) {
    parts.push(
      "This result reflects real, already-committed production events for this source within the rule's window, not only the pasted input."
    );
  }

  if (isTemporaryRule) {
    if (stage.grouped_results.length > 0) {
      const groupSummary = stage.grouped_results
        .slice(0, 5)
        .map((group) => `${stage.group_by_field || "group"}=${group.group_value} (${group.match_count})`)
        .join(", ");
      parts.push(`Grouped evidence: ${groupSummary}.`);
    } else {
      parts.push("No grouped entity matched the condition in the pasted or sample events.");
    }
  }
  if (stage.pasted_event_only) {
    parts.push(
      "This result reflects only the pasted or sample events included in this request; no committed production event history was blended."
    );
  }
  if (stage.nothing_persisted) {
    parts.push("Nothing was persisted or executed by this evaluation.");
  }

  return {
    key: "threshold_window_evaluation",
    title: "Threshold / window evaluation",
    body: parts.join(" "),
  };
}

function alertExplanation(stage) {
  if (!stage || stage.status !== "succeeded") return null;
  const isTemporaryRule =
    stage.reason === "temporary_rule_threshold_not_reached" || stage.temporary_rule_semantics === true;
  if (!stage.alert) {
    return {
      key: "alert_preview",
      title: "Alert preview",
      body: isTemporaryRule
        ? "No alert would be created: the temporary rule's threshold was not reached for any grouped entity in the pasted or sample events."
        : "No alert would be created for the selected rule with this input.",
    };
  }
  const alert = stage.alert;
  const persistenceNote = isTemporaryRule
    ? " This preview is request-scoped only; nothing was persisted or executed."
    : "";
  return {
    key: "alert_preview",
    title: "Alert preview",
    body: `Would create a ${alert.severity || "unspecified"}-severity "${alert.alert_type}" alert: "${alert.message}". Reputation source: ${alert.reputation_source} (stubbed for simulation, not the source IP's real reputation).${persistenceNote}`,
  };
}

function mitreExplanation(stage) {
  if (!stage) return null;
  if (stage.status === "skipped") return null;
  if (stage.status === "succeeded" && !stage.mitre_technique_id) {
    return {
      key: "mitre_mapping",
      title: "MITRE mapping",
      body:
        stage.reason === "no_temporary_rule_mitre_selected"
          ? "No MITRE ATT&CK technique was selected for this temporary rule."
          : "This alert type does not have a specific MITRE ATT&CK technique mapping.",
    };
  }
  if (stage.status === "succeeded") {
    return {
      key: "mitre_mapping",
      title: "MITRE mapping",
      body: `${stage.mitre_technique_id} — ${stage.mitre_technique_name} (${stage.mitre_tactic}).`,
    };
  }
  return null;
}

function soarExplanation(stage) {
  if (!stage || stage.status !== "succeeded") return null;
  const parts = [];
  if (stage.no_playbook_match) {
    parts.push("No enabled playbook's trigger configuration matched this alert.");
  } else {
    const playbookSummaries = (stage.matched_playbooks || []).map((playbook) => {
      const approval = playbook.approval_required
        ? ` (requires approval: ${playbook.approval_risk_levels.join(", ")})`
        : "";
      return `"${playbook.name || playbook.playbook_id}"${approval}`;
    });
    parts.push(`Matched playbook(s): ${playbookSummaries.join(", ")}.`);
  }
  if (stage.selected_response_action) {
    parts.push(`Selected response action: ${stage.selected_response_action}. ${stage.response_action_basis || ""}`.trim());
  }
  parts.push("No playbook execution, queue entry, or external integration was created or invoked.");

  return {
    key: "soar_preview",
    title: "SOAR preview",
    body: parts.join(" "),
  };
}

const listStyle = { margin: 0 };
const entryStyle = { background: "#161b22", border: "1px solid #30363d", borderRadius: "8px", padding: "10px 14px", marginBottom: "8px" };
const termStyle = { margin: 0, color: "#58a6ff", fontSize: "13px", fontWeight: 700 };
const descriptionStyle = { margin: "4px 0 0", color: "#c9d1d9", fontSize: "13px", lineHeight: 1.5 };
const emptyStyle = { color: "#9da7b3" };

export default DetectionSimulatorExplainability;
