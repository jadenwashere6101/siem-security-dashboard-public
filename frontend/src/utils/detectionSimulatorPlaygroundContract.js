export const SIMULATION_MODE_EXISTING_PRODUCTION_RULE = "existing_production_rule";
export const SIMULATION_MODE_TEMPORARY_PLAYGROUND_RULE = "temporary_playground_rule";
export const SIMULATION_MODE_SIGMA_SUBSET_IMPORT = "sigma_subset_import";

// Presentation-only label. The frontend never claims full Sigma compatibility.
export const SIGMA_SUBSET_COMPATIBILITY_DISCLOSURE =
  "Strict Sigma subset import for Detection Playground Version 3 — not full Sigma compatibility. Unsupported constructs are rejected by the backend.";

// Presentation/UI-guidance-only mirror of engines/detection_simulator.py's
// temporary-rule contract constants (TEMPORARY_RULE_ALLOWED_FIELDS_BY_SOURCE,
// TEMPORARY_RULE_GROUPABLE_FIELDS_BY_SOURCE, TEMPORARY_RULE_SUPPORTED_INPUT_FORMATS,
// TEMPORARY_RULE_ALLOWED_EVENT_TYPES_BY_SOURCE, TEMPORARY_RULE_ALLOWED_OPERATORS,
// TEMPORARY_RULE_*_OPERATORS, TEMPORARY_RULE_NUMERIC_FIELDS, VALID_SEVERITIES).
// This narrows the builder's choices to reduce round-trip validation errors;
// it is NOT the source of truth. The backend independently validates every
// field with the same fail-closed rules regardless of what this file allows,
// and this module never evaluates a rule against an event.

export const PLAYGROUND_CONDITION_FIELDS_BY_SOURCE = Object.freeze({
  honeypot: Object.freeze(["source_ip", "username", "event_type", "severity"]),
  bank_app: Object.freeze(["source_ip", "username", "event_type", "event_outcome", "severity"]),
  pfsense: Object.freeze(["source_ip", "destination_ip", "destination_port", "event_type", "action", "severity"]),
  nginx: Object.freeze(["source_ip", "event_type", "http_status", "severity"]),
  azure_insights: Object.freeze(["source_ip", "username", "event_type", "event_outcome", "http_status", "severity"]),
  opentelemetry: Object.freeze(["source_ip", "event_type", "http_status", "severity"]),
});

export const PLAYGROUND_GROUP_BY_FIELDS_BY_SOURCE = Object.freeze({
  honeypot: Object.freeze(["source_ip", "username"]),
  bank_app: Object.freeze(["source_ip", "username"]),
  pfsense: Object.freeze(["source_ip", "destination_ip", "destination_port"]),
  nginx: Object.freeze(["source_ip"]),
  azure_insights: Object.freeze(["source_ip", "username"]),
  opentelemetry: Object.freeze(["source_ip"]),
});

export const PLAYGROUND_INPUT_FORMATS_BY_SOURCE = Object.freeze({
  honeypot: Object.freeze(["json_lines", "json_array"]),
  bank_app: Object.freeze(["json_lines", "json_array"]),
  pfsense: Object.freeze(["raw_text", "json_lines", "json_array"]),
  nginx: Object.freeze(["raw_text"]),
  azure_insights: Object.freeze(["json_lines", "json_array"]),
  opentelemetry: Object.freeze(["json_lines", "json_array"]),
});

export const PLAYGROUND_EVENT_TYPES_BY_SOURCE = Object.freeze({
  honeypot: Object.freeze(["env_probe", "admin_probe", "scanner_detected", "credential_stuffing", "http_error"]),
  bank_app: Object.freeze([
    "failed_login",
    "login_failure",
    "successful_login",
    "port_scan",
    "normal_activity",
    "env_probe",
    "admin_probe",
    "scanner_detected",
    "credential_stuffing",
  ]),
  pfsense: Object.freeze(["firewall_block", "firewall_allow"]),
  nginx: Object.freeze(["unauthorized_access", "http_error", "normal_activity"]),
  azure_insights: Object.freeze([
    "failed_login",
    "successful_login",
    "application_exception",
    "availability_failure",
    "http_error",
    "normal_activity",
  ]),
  opentelemetry: Object.freeze(["unauthorized_access", "http_error", "application_exception", "normal_activity"]),
});

export const PLAYGROUND_NUMERIC_FIELDS = Object.freeze(["destination_port", "http_status"]);

export const PLAYGROUND_STRING_OPERATORS = Object.freeze([
  "equals",
  "not_equals",
  "contains",
  "starts_with",
  "ends_with",
  "in_list",
]);

export const PLAYGROUND_NUMERIC_OPERATORS = Object.freeze([
  "equals",
  "not_equals",
  "greater_than",
  "greater_than_or_equal",
  "less_than",
  "less_than_or_equal",
  "in_list",
]);

export const PLAYGROUND_OPERATOR_LABELS = Object.freeze({
  equals: "equals",
  not_equals: "does not equal",
  contains: "contains",
  starts_with: "starts with",
  ends_with: "ends with",
  greater_than: "is greater than",
  greater_than_or_equal: "is greater than or equal to",
  less_than: "is less than",
  less_than_or_equal: "is less than or equal to",
  in_list: "is one of",
});

export const PLAYGROUND_INPUT_FORMAT_LABELS = Object.freeze({
  raw_text: "Raw log line(s)",
  json_lines: "JSON lines (one event per line)",
  json_array: "JSON array of events",
});

export const PLAYGROUND_SEVERITIES = Object.freeze(["low", "medium", "high", "critical"]);

export const PLAYGROUND_MITRE_PATTERN = /^T\d{4}(?:\.\d{3})?$/;

export const operatorsForField = (fieldName) =>
  PLAYGROUND_NUMERIC_FIELDS.includes(fieldName) ? PLAYGROUND_NUMERIC_OPERATORS : PLAYGROUND_STRING_OPERATORS;

// Pure, derived-from-form-state description only. This never inspects or
// evaluates pasted/sample events -- it describes the rule the analyst is
// building, exactly as SIMULATOR_SOURCE_INPUT_FORMATS already mirrors backend
// enums for guidance elsewhere in this workspace.
export const buildPlainLanguageSummary = ({
  source,
  eventType,
  conditionField,
  conditionOperator,
  conditionValue,
  groupByField,
  threshold,
  windowMinutes,
  severity,
  mitreTechniqueId,
}) => {
  if (!source || !conditionField || !conditionOperator || !groupByField || !threshold || !windowMinutes || !severity) {
    return "Select a source and fill in the condition, grouping, threshold, and window to see a plain-language summary of this temporary rule.";
  }

  const operatorLabel = PLAYGROUND_OPERATOR_LABELS[conditionOperator] || conditionOperator;
  const valueText = Array.isArray(conditionValue) ? conditionValue.join(", ") : conditionValue;
  const eventTypeText = eventType ? ` and event type equals "${eventType}"` : "";
  const mitreText = mitreTechniqueId ? ` Tag matching alerts with MITRE ATT&CK technique ${mitreTechniqueId}.` : "";

  return (
    `IF ${conditionField} ${operatorLabel} "${valueText}"${eventTypeText} for ${source} events, ` +
    `GROUP BY ${groupByField}, THEN raise a ${severity}-severity temporary alert preview when ` +
    `${threshold} or more matching event(s) from the same ${groupByField} occur within ${windowMinutes} minute(s) ` +
    `of the pasted or sample events in this request.${mitreText}`
  );
};
