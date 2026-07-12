// Presentation-only metadata for the Detection Simulator pipeline. This is
// NOT simulation logic: stage order/labels mirror the backend's response
// contract (openspec/changes/add-detection-simulator-workspace/specs), and
// SIMULATOR_SOURCE_INPUT_FORMATS mirrors engines/detection_simulator.py's
// SUPPORTED_INPUT_FORMATS purely so the UI can guide input selection; the
// backend independently validates and is the sole source of truth.

export const SIMULATOR_STAGE_DEFINITIONS = Object.freeze([
  Object.freeze({ id: "raw_input", label: "Raw Input" }),
  Object.freeze({ id: "parser", label: "Parser" }),
  Object.freeze({ id: "normalized_event", label: "Normalized Event" }),
  Object.freeze({ id: "detection_applicability", label: "Detection Applicability" }),
  Object.freeze({ id: "detection_evaluation", label: "Detection Evaluation" }),
  Object.freeze({ id: "threshold_window_evaluation", label: "Threshold / Window Evaluation" }),
  Object.freeze({ id: "alert_preview", label: "Alert Preview" }),
  Object.freeze({ id: "mitre_mapping", label: "MITRE Mapping" }),
  Object.freeze({ id: "soar_preview", label: "SOAR Preview" }),
]);

export const SIMULATOR_SOURCE_INPUT_FORMATS = Object.freeze({
  pfsense: Object.freeze(["raw", "json"]),
  nginx: Object.freeze(["raw"]),
  honeypot: Object.freeze(["json"]),
  bank_app: Object.freeze(["json"]),
  azure_insights: Object.freeze(["json"]),
  opentelemetry: Object.freeze(["json"]),
});

export const SIMULATOR_STAGE_REASON_TEXT = Object.freeze({
  not_reached: "This stage was not reached.",
  parser_failed: "No input line or event could be parsed for this source.",
  rule_not_applicable_to_source: "The selected rule does not apply to the selected source.",
  no_alert_created_for_selected_rule: "The selected rule did not produce an alert for this input.",
});

export const describeStageReason = (reason) => {
  if (!reason) return null;
  return SIMULATOR_STAGE_REASON_TEXT[reason] || reason;
};
