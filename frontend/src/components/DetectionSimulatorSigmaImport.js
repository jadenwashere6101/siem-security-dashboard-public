import React, { useState } from "react";

import {
  PLAYGROUND_INPUT_FORMAT_LABELS,
  PLAYGROUND_INPUT_FORMATS_BY_SOURCE,
  SIGMA_SUBSET_COMPATIBILITY_DISCLOSURE,
  SIMULATION_MODE_SIGMA_SUBSET_IMPORT,
} from "../utils/detectionSimulatorPlaygroundContract";
import {
  SAMPLE_SIGMA_BANK_APP_EVENTS_JSON,
  SAMPLE_SIGMA_BANK_APP_YAML,
} from "../utils/detectionSimulatorSigmaSamples";

const SIGMA_EVENT_FORMATS = Object.freeze(["json_array", "json_lines", "raw_text"]);

const emptyState = {
  sigmaYaml: "",
  inputFormat: "json_array",
  inputText: "",
};

// Assembles a sigma_subset_import request from analyst text fields and hands
// it to onRun. This component never parses Sigma YAML, never maps logsource
// or fields, never compiles a predicate tree, and never evaluates events —
// those steps happen only on the backend temporary-rule evaluator path.
function DetectionSimulatorSigmaImport({ running, onRun, onReset, onValidationError }) {
  const [state, setState] = useState(emptyState);

  const canSubmit =
    !running && state.sigmaYaml.trim().length > 0 && state.inputText.trim().length > 0 && !!state.inputFormat;

  const handleReset = () => {
    setState(emptyState);
    onReset();
  };

  const handleLoadSampleRule = () => {
    setState((prev) => ({
      ...prev,
      sigmaYaml: SAMPLE_SIGMA_BANK_APP_YAML,
      inputFormat: "json_array",
    }));
  };

  const handleLoadSampleEvents = () => {
    setState((prev) => ({
      ...prev,
      inputFormat: "json_array",
      inputText: SAMPLE_SIGMA_BANK_APP_EVENTS_JSON,
    }));
  };

  const handleSubmit = (event) => {
    event.preventDefault();
    if (!canSubmit) {
      onValidationError("Paste a Sigma YAML rule and at least one event before running a simulation.");
      return;
    }
    if (!SIGMA_EVENT_FORMATS.includes(state.inputFormat)) {
      onValidationError("Select a supported event input format.");
      return;
    }

    onRun({
      simulation_mode: SIMULATION_MODE_SIGMA_SUBSET_IMPORT,
      sigma_yaml: state.sigmaYaml,
      input_format: state.inputFormat,
      input_text: state.inputText,
    });
  };

  return (
    <form onSubmit={handleSubmit} style={formStyle} aria-label="Sigma subset import">
      <p style={disclosureStyle} role="note" data-testid="sigma-mode-disclosure">
        {SIGMA_SUBSET_COMPATIBILITY_DISCLOSURE} Pasted events are evaluated only inside a rollback-only
        transaction. Nothing is saved, promoted, or executed outside this preview. The UI does not evaluate
        Sigma rules client-side.
      </p>

      <div style={actionRowStyle}>
        <button type="button" onClick={handleLoadSampleRule} style={secondaryButtonStyle}>
          Load sample Sigma rule
        </button>
        <button type="button" onClick={handleLoadSampleEvents} style={secondaryButtonStyle}>
          Load sample events
        </button>
      </div>

      <label style={textAreaFieldStyle}>
        <span style={fieldLabelStyle}>Sigma YAML (strict subset)</span>
        <textarea
          value={state.sigmaYaml}
          onChange={(event) => setState((prev) => ({ ...prev, sigmaYaml: event.target.value }))}
          rows={14}
          style={textAreaStyle}
          aria-label="Sigma YAML input"
          placeholder="Paste a Version 3–supported Sigma rule…"
          spellCheck={false}
        />
      </label>

      <div style={fieldRowStyle}>
        <label style={fieldStyle}>
          <span style={fieldLabelStyle}>Event input format</span>
          <select
            value={state.inputFormat}
            onChange={(event) => setState((prev) => ({ ...prev, inputFormat: event.target.value }))}
            style={selectStyle}
            aria-label="Sigma event input format"
          >
            {SIGMA_EVENT_FORMATS.map((format) => (
              <option key={format} value={format}>
                {PLAYGROUND_INPUT_FORMAT_LABELS[format] || format}
              </option>
            ))}
          </select>
        </label>
        <p style={hintStyle} role="note">
          Canonical source is resolved from the Sigma <code>logsource</code> by the backend. Choose an event
          format compatible with that source
          {Object.keys(PLAYGROUND_INPUT_FORMATS_BY_SOURCE).length
            ? " (for example, json_array for bank_app)."
            : "."}
        </p>
      </div>

      <label style={textAreaFieldStyle}>
        <span style={fieldLabelStyle}>Pasted or sample events</span>
        <textarea
          value={state.inputText}
          onChange={(event) => setState((prev) => ({ ...prev, inputText: event.target.value }))}
          rows={8}
          style={textAreaStyle}
          aria-label="Sigma event input"
          placeholder="Paste events that match the resolved canonical source…"
          spellCheck={false}
        />
      </label>

      <div style={buttonRowStyle}>
        <button type="submit" disabled={!canSubmit} style={runButtonStyle}>
          {running ? "Running simulation…" : "Run Simulation"}
        </button>
        <button type="button" onClick={handleReset} style={secondaryButtonStyle}>
          Reset / Discard
        </button>
      </div>
    </form>
  );
}

const formStyle = {
  display: "flex",
  flexDirection: "column",
  gap: "14px",
  background: "#161b22",
  border: "1px solid #30363d",
  borderRadius: "12px",
  padding: "18px",
  marginBottom: "20px",
};
const disclosureStyle = {
  margin: 0,
  color: "#c9d1d9",
  background: "rgba(88,166,255,.08)",
  border: "1px solid rgba(88,166,255,.35)",
  borderRadius: "8px",
  padding: "10px 12px",
  fontSize: "13px",
};
const actionRowStyle = { display: "flex", flexWrap: "wrap", gap: "10px" };
const buttonRowStyle = { display: "flex", flexWrap: "wrap", gap: "10px", alignItems: "center" };
const fieldRowStyle = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
  gap: "14px",
  alignItems: "start",
};
const fieldStyle = { display: "flex", flexDirection: "column", gap: "6px", minWidth: 0 };
const textAreaFieldStyle = { display: "flex", flexDirection: "column", gap: "6px" };
const fieldLabelStyle = {
  color: "#8c96a1",
  fontSize: "12px",
  textTransform: "uppercase",
  letterSpacing: "0.05em",
};
const selectStyle = {
  background: "#0d1117",
  color: "#f0f6fc",
  border: "1px solid #30363d",
  borderRadius: "8px",
  padding: "8px 10px",
  fontSize: "14px",
};
const textAreaStyle = {
  background: "#0d1117",
  color: "#f0f6fc",
  border: "1px solid #30363d",
  borderRadius: "8px",
  padding: "10px",
  fontSize: "13px",
  fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
  resize: "vertical",
};
const hintStyle = { margin: "0", color: "#9da7b3", fontSize: "12px", alignSelf: "center" };
const runButtonStyle = {
  alignSelf: "flex-start",
  border: "1px solid #388bfd",
  background: "#1f6feb",
  color: "#fff",
  borderRadius: "8px",
  padding: "9px 18px",
  fontWeight: 600,
  cursor: "pointer",
};
const secondaryButtonStyle = {
  border: "1px solid #30363d",
  background: "#21262d",
  color: "#f0f6fc",
  borderRadius: "8px",
  padding: "9px 14px",
  fontWeight: 600,
  cursor: "pointer",
};

export default DetectionSimulatorSigmaImport;
