import React, { useEffect, useMemo, useState } from "react";

import { SOURCE_METADATA, SOURCE_METADATA_BY_ID } from "../utils/sourceMetadata";
import {
  PLAYGROUND_CONDITION_FIELDS_BY_SOURCE,
  PLAYGROUND_EVENT_TYPES_BY_SOURCE,
  PLAYGROUND_GROUP_BY_FIELDS_BY_SOURCE,
  PLAYGROUND_INPUT_FORMATS_BY_SOURCE,
  PLAYGROUND_INPUT_FORMAT_LABELS,
  PLAYGROUND_MITRE_PATTERN,
  PLAYGROUND_NUMERIC_FIELDS,
  PLAYGROUND_OPERATOR_LABELS,
  PLAYGROUND_SEVERITIES,
  SIMULATION_MODE_TEMPORARY_PLAYGROUND_RULE,
  buildPlainLanguageSummary,
  operatorsForField,
} from "../utils/detectionSimulatorPlaygroundContract";
import { getPlaygroundSampleText } from "../utils/detectionSimulatorPlaygroundSamples";

const emptyBuilderState = {
  source: "",
  inputFormat: "",
  inputText: "",
  eventType: "",
  conditionField: "",
  conditionOperator: "",
  conditionValue: "",
  groupByField: "",
  threshold: "3",
  windowMinutes: "15",
  severity: "medium",
  mitreTechniqueId: "",
};

// This component only assembles a `temporary_rule` request object from the
// analyst's form selections and hands it to `onRun`. It never parses pasted
// events, never computes a condition match, and never computes a threshold
// outcome -- all of that evidence comes back from the backend and is
// rendered by the shared DetectionSimulatorPipeline / Explainability
// components, exactly like Version 1's production-rule mode.
function DetectionSimulatorPlaygroundBuilder({ running, onRun, onReset, onValidationError }) {
  const [state, setState] = useState(emptyBuilderState);

  const availableFormats = useMemo(
    () => (state.source ? PLAYGROUND_INPUT_FORMATS_BY_SOURCE[state.source] || [] : []),
    [state.source]
  );
  const availableConditionFields = useMemo(
    () => (state.source ? PLAYGROUND_CONDITION_FIELDS_BY_SOURCE[state.source] || [] : []),
    [state.source]
  );
  const availableGroupByFields = useMemo(
    () => (state.source ? PLAYGROUND_GROUP_BY_FIELDS_BY_SOURCE[state.source] || [] : []),
    [state.source]
  );
  const availableEventTypes = useMemo(
    () => (state.source ? PLAYGROUND_EVENT_TYPES_BY_SOURCE[state.source] || [] : []),
    [state.source]
  );
  const availableOperators = useMemo(
    () => (state.conditionField ? operatorsForField(state.conditionField) : []),
    [state.conditionField]
  );
  const isNumericField = PLAYGROUND_NUMERIC_FIELDS.includes(state.conditionField);
  const isInList = state.conditionOperator === "in_list";

  useEffect(() => {
    setState((prev) => ({
      ...prev,
      conditionOperator: availableOperators.includes(prev.conditionOperator) ? prev.conditionOperator : "",
    }));
  }, [availableOperators]);

  const summary = useMemo(
    () =>
      buildPlainLanguageSummary({
        source: state.source,
        eventType: state.eventType,
        conditionField: state.conditionField,
        conditionOperator: state.conditionOperator,
        conditionValue: isInList
          ? state.conditionValue.split(",").map((item) => item.trim()).filter(Boolean)
          : state.conditionValue,
        groupByField: state.groupByField,
        threshold: state.threshold,
        windowMinutes: state.windowMinutes,
        severity: state.severity,
        mitreTechniqueId: state.mitreTechniqueId,
      }),
    [state, isInList]
  );

  const handleSourceChange = (nextSource) => {
    const formats = PLAYGROUND_INPUT_FORMATS_BY_SOURCE[nextSource] || [];
    setState((prev) => ({
      ...emptyBuilderState,
      threshold: prev.threshold,
      windowMinutes: prev.windowMinutes,
      severity: prev.severity,
      source: nextSource,
      inputFormat: formats.length === 1 ? formats[0] : "",
    }));
  };

  const handleLoadSampleEvents = () => {
    const sample = getPlaygroundSampleText(state.source, state.inputFormat);
    if (sample) {
      setState((prev) => ({ ...prev, inputText: sample }));
    }
  };

  const canLoadSample = !!getPlaygroundSampleText(state.source, state.inputFormat);

  const canSubmit =
    !running &&
    !!state.source &&
    !!state.inputFormat &&
    state.inputText.trim().length > 0 &&
    !!state.conditionField &&
    !!state.conditionOperator &&
    state.conditionValue.trim().length > 0 &&
    !!state.groupByField &&
    state.threshold.trim().length > 0 &&
    state.windowMinutes.trim().length > 0 &&
    !!state.severity;

  const handleReset = () => {
    setState(emptyBuilderState);
    onReset();
  };

  const handleSubmit = (event) => {
    event.preventDefault();

    if (!canSubmit) {
      onValidationError("Fill in the source, input, condition, grouping, threshold, and window before running a simulation.");
      return;
    }

    const thresholdNumber = Number(state.threshold);
    const windowNumber = Number(state.windowMinutes);
    if (!Number.isInteger(thresholdNumber) || thresholdNumber < 1 || thresholdNumber > 100) {
      onValidationError("Threshold must be a whole number between 1 and 100.");
      return;
    }
    if (!Number.isInteger(windowNumber) || windowNumber < 1 || windowNumber > 1440) {
      onValidationError("Window (minutes) must be a whole number between 1 and 1440.");
      return;
    }

    let conditionValue;
    if (isInList) {
      const items = state.conditionValue.split(",").map((item) => item.trim()).filter(Boolean);
      if (items.length === 0) {
        onValidationError("Provide at least one comma-separated value for the 'is one of' operator.");
        return;
      }
      if (isNumericField) {
        conditionValue = items.map((item) => Number(item));
        if (conditionValue.some((item) => !Number.isInteger(item))) {
          onValidationError(`${state.conditionField} values must be whole numbers.`);
          return;
        }
      } else {
        conditionValue = items;
      }
    } else if (isNumericField) {
      conditionValue = Number(state.conditionValue.trim());
      if (!Number.isInteger(conditionValue)) {
        onValidationError(`${state.conditionField} must be a whole number.`);
        return;
      }
    } else {
      conditionValue = state.conditionValue.trim();
    }

    let mitreTechniqueId = null;
    if (state.mitreTechniqueId.trim().length > 0) {
      mitreTechniqueId = state.mitreTechniqueId.trim();
      if (!PLAYGROUND_MITRE_PATTERN.test(mitreTechniqueId)) {
        onValidationError("MITRE technique ID must match Txxxx or Txxxx.xxx (for example, T1110 or T1110.001).");
        return;
      }
    }

    const sourceType = SOURCE_METADATA_BY_ID[state.source]?.sourceType;

    const temporaryRule = {
      source: state.source,
      source_type: sourceType,
      input_format: state.inputFormat,
      event_type: state.eventType || null,
      condition: {
        field: state.conditionField,
        operator: state.conditionOperator,
        value: conditionValue,
      },
      aggregation: { type: "count", group_by_field: state.groupByField },
      threshold: thresholdNumber,
      window_minutes: windowNumber,
      severity: state.severity,
      mitre_technique_id: mitreTechniqueId,
    };

    onRun({
      simulation_mode: SIMULATION_MODE_TEMPORARY_PLAYGROUND_RULE,
      temporary_rule: temporaryRule,
      input_text: state.inputText,
    });
  };

  return (
    <form onSubmit={handleSubmit} style={formStyle} aria-label="Temporary playground rule builder">
      <p style={disclosureStyle} role="note">
        Temporary playground semantics: this rule is evaluated only against the pasted or sample events in this
        request. Nothing is saved, promoted, or persisted — every run executes inside a rollback-only transaction and
        no rule, draft, event, alert, or response action is ever created, queued, or executed outside this preview.
      </p>

      <div style={fieldRowStyle}>
        <label style={fieldStyle}>
          <span style={fieldLabelStyle}>Source</span>
          <select
            value={state.source}
            onChange={(event) => handleSourceChange(event.target.value)}
            style={selectStyle}
            aria-label="Playground source"
          >
            <option value="">Select a source…</option>
            {SOURCE_METADATA.map((item) => (
              <option key={item.source} value={item.source}>
                {item.displayLabel}
              </option>
            ))}
          </select>
        </label>

        <label style={fieldStyle}>
          <span style={fieldLabelStyle}>Input format</span>
          <select
            value={state.inputFormat}
            onChange={(event) => setState((prev) => ({ ...prev, inputFormat: event.target.value }))}
            style={selectStyle}
            aria-label="Playground input format"
            disabled={!state.source}
          >
            <option value="">{state.source ? "Select a format…" : "Select a source first"}</option>
            {availableFormats.map((format) => (
              <option key={format} value={format}>
                {PLAYGROUND_INPUT_FORMAT_LABELS[format] || format}
              </option>
            ))}
          </select>
        </label>

        <label style={fieldStyle}>
          <span style={fieldLabelStyle}>Event type filter (optional)</span>
          <select
            value={state.eventType}
            onChange={(event) => setState((prev) => ({ ...prev, eventType: event.target.value }))}
            style={selectStyle}
            aria-label="Playground event type filter"
            disabled={!state.source}
          >
            <option value="">Any event type</option>
            {availableEventTypes.map((eventType) => (
              <option key={eventType} value={eventType}>
                {eventType}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div style={textAreaFieldStyle}>
        <label style={textAreaFieldStyle}>
          <span style={fieldLabelStyle}>Pasted or sample event(s)</span>
          <textarea
            value={state.inputText}
            onChange={(event) => setState((prev) => ({ ...prev, inputText: event.target.value }))}
            rows={8}
            style={textAreaStyle}
            aria-label="Playground event input"
            placeholder="Select a source and input format, then paste events or load a sample…"
            disabled={!state.inputFormat}
          />
        </label>
        <button
          type="button"
          onClick={handleLoadSampleEvents}
          disabled={!canLoadSample}
          style={sampleButtonStyle}
        >
          Load sample events
        </button>
      </div>

      <fieldset style={fieldsetStyle}>
        <legend style={legendStyle}>Condition</legend>
        <div style={fieldRowStyle}>
          <label style={fieldStyle}>
            <span style={fieldLabelStyle}>Field</span>
            <select
              value={state.conditionField}
              onChange={(event) =>
                setState((prev) => ({ ...prev, conditionField: event.target.value, conditionOperator: "" }))
              }
              style={selectStyle}
              aria-label="Condition field"
              disabled={!state.source}
            >
              <option value="">Select a field…</option>
              {availableConditionFields.map((field) => (
                <option key={field} value={field}>
                  {field}
                </option>
              ))}
            </select>
          </label>

          <label style={fieldStyle}>
            <span style={fieldLabelStyle}>Operator</span>
            <select
              value={state.conditionOperator}
              onChange={(event) => setState((prev) => ({ ...prev, conditionOperator: event.target.value }))}
              style={selectStyle}
              aria-label="Condition operator"
              disabled={!state.conditionField}
            >
              <option value="">Select an operator…</option>
              {availableOperators.map((operator) => (
                <option key={operator} value={operator}>
                  {PLAYGROUND_OPERATOR_LABELS[operator] || operator}
                </option>
              ))}
            </select>
          </label>

          <label style={fieldStyle}>
            <span style={fieldLabelStyle}>{isInList ? "Value(s), comma-separated" : "Value"}</span>
            <input
              type="text"
              value={state.conditionValue}
              onChange={(event) => setState((prev) => ({ ...prev, conditionValue: event.target.value }))}
              style={inputStyle}
              aria-label="Condition value"
              disabled={!state.conditionOperator}
              placeholder={isNumericField ? "e.g. 443" : "e.g. 203.0.113.5"}
            />
          </label>
        </div>
      </fieldset>

      <div style={fieldRowStyle}>
        <label style={fieldStyle}>
          <span style={fieldLabelStyle}>Group by</span>
          <select
            value={state.groupByField}
            onChange={(event) => setState((prev) => ({ ...prev, groupByField: event.target.value }))}
            style={selectStyle}
            aria-label="Group by field"
            disabled={!state.source}
          >
            <option value="">Select a field…</option>
            {availableGroupByFields.map((field) => (
              <option key={field} value={field}>
                {field}
              </option>
            ))}
          </select>
        </label>

        <label style={fieldStyle}>
          <span style={fieldLabelStyle}>Threshold (1-100)</span>
          <input
            type="number"
            min="1"
            max="100"
            value={state.threshold}
            onChange={(event) => setState((prev) => ({ ...prev, threshold: event.target.value }))}
            style={inputStyle}
            aria-label="Threshold"
          />
        </label>

        <label style={fieldStyle}>
          <span style={fieldLabelStyle}>Window (minutes, 1-1440)</span>
          <input
            type="number"
            min="1"
            max="1440"
            value={state.windowMinutes}
            onChange={(event) => setState((prev) => ({ ...prev, windowMinutes: event.target.value }))}
            style={inputStyle}
            aria-label="Window minutes"
          />
        </label>
      </div>

      <div style={fieldRowStyle}>
        <label style={fieldStyle}>
          <span style={fieldLabelStyle}>Severity</span>
          <select
            value={state.severity}
            onChange={(event) => setState((prev) => ({ ...prev, severity: event.target.value }))}
            style={selectStyle}
            aria-label="Playground severity"
          >
            {PLAYGROUND_SEVERITIES.map((severity) => (
              <option key={severity} value={severity}>
                {severity}
              </option>
            ))}
          </select>
        </label>

        <label style={fieldStyle}>
          <span style={fieldLabelStyle}>MITRE ATT&amp;CK technique (optional)</span>
          <input
            type="text"
            value={state.mitreTechniqueId}
            onChange={(event) => setState((prev) => ({ ...prev, mitreTechniqueId: event.target.value }))}
            style={inputStyle}
            aria-label="MITRE technique ID"
            placeholder="e.g. T1110 or T1110.001"
          />
        </label>
      </div>

      <div style={summaryStyle} data-testid="playground-rule-summary" aria-live="polite">
        <span style={fieldLabelStyle}>Plain-language summary</span>
        <p style={summaryTextStyle}>{summary}</p>
      </div>

      <div style={actionsRowStyle}>
        <button type="submit" disabled={!canSubmit} style={runButtonStyle}>
          {running ? "Running simulation…" : "Run Simulation"}
        </button>
        <button type="button" onClick={handleReset} disabled={running} style={resetButtonStyle}>
          Reset Rule
        </button>
      </div>
    </form>
  );
}

const formStyle = { display: "flex", flexDirection: "column", gap: "14px", background: "#161b22", border: "1px solid #30363d", borderRadius: "12px", padding: "18px", marginBottom: "20px" };
const disclosureStyle = { margin: 0, color: "#d29922", background: "rgba(210,153,34,.1)", border: "1px solid #9e6a03", borderRadius: "8px", padding: "10px 12px", fontSize: "13px", lineHeight: 1.5 };
const fieldRowStyle = { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "14px" };
const fieldStyle = { display: "flex", flexDirection: "column", gap: "6px", minWidth: 0 };
const textAreaFieldStyle = { display: "flex", flexDirection: "column", gap: "6px" };
const fieldLabelStyle = { color: "#8c96a1", fontSize: "12px", textTransform: "uppercase", letterSpacing: "0.05em" };
const selectStyle = { background: "#0d1117", color: "#f0f6fc", border: "1px solid #30363d", borderRadius: "8px", padding: "8px 10px", fontSize: "14px" };
const inputStyle = { background: "#0d1117", color: "#f0f6fc", border: "1px solid #30363d", borderRadius: "8px", padding: "8px 10px", fontSize: "14px" };
const textAreaStyle = { background: "#0d1117", color: "#f0f6fc", border: "1px solid #30363d", borderRadius: "8px", padding: "10px", fontSize: "13px", fontFamily: "monospace", resize: "vertical" };
const fieldsetStyle = { border: "1px solid #30363d", borderRadius: "8px", padding: "12px", margin: 0 };
const legendStyle = { color: "#8c96a1", fontSize: "12px", textTransform: "uppercase", letterSpacing: "0.05em", padding: "0 4px" };
const sampleButtonStyle = { alignSelf: "flex-start", border: "1px solid #30363d", background: "#0d1117", color: "#c9d1d9", borderRadius: "8px", padding: "6px 12px", fontSize: "12px", fontWeight: 600, cursor: "pointer" };
const summaryStyle = { display: "flex", flexDirection: "column", gap: "6px", background: "#0d1117", border: "1px solid #30363d", borderRadius: "8px", padding: "12px" };
const summaryTextStyle = { margin: 0, color: "#c9d1d9", fontSize: "13px", lineHeight: 1.5 };
const actionsRowStyle = { display: "flex", gap: "12px" };
const runButtonStyle = { border: "1px solid #388bfd", background: "#1f6feb", color: "#fff", borderRadius: "8px", padding: "9px 18px", fontWeight: 600, cursor: "pointer" };
const resetButtonStyle = { border: "1px solid #30363d", backgroundColor: "#161b22", color: "#c9d1d9", borderRadius: "8px", padding: "9px 18px", fontWeight: 600, cursor: "pointer" };

export default DetectionSimulatorPlaygroundBuilder;
