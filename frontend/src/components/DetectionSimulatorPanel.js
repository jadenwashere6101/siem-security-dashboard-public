import React, { useEffect, useMemo, useState } from "react";

import { loadSimulatorRules, runDetectionSimulation } from "../services/detectionSimulatorService";
import { SOURCE_METADATA } from "../utils/sourceMetadata";
import { SIMULATOR_SOURCE_INPUT_FORMATS } from "../utils/detectionSimulatorStages";
import DetectionSimulatorPipeline from "./DetectionSimulatorPipeline";
import DetectionSimulatorExplainability from "./DetectionSimulatorExplainability";

const FORMAT_LABELS = { raw: "Raw log line(s)", json: "JSON event(s)" };

function DetectionSimulatorPanel() {
  const [rules, setRules] = useState([]);
  const [rulesLoading, setRulesLoading] = useState(true);
  const [rulesError, setRulesError] = useState("");

  const [source, setSource] = useState("");
  const [ruleId, setRuleId] = useState("");
  const [inputFormat, setInputFormat] = useState("");
  const [rawText, setRawText] = useState("");
  const [jsonText, setJsonText] = useState("");

  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState("");
  const [result, setResult] = useState(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        setRulesLoading(true);
        setRulesError("");
        const loaded = await loadSimulatorRules();
        if (cancelled) return;
        setRules(loaded);
      } catch (err) {
        if (cancelled) return;
        setRulesError(err.message || "Unable to load detection rules");
      } finally {
        if (!cancelled) setRulesLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const availableFormats = useMemo(
    () => (source ? SIMULATOR_SOURCE_INPUT_FORMATS[source] || [] : []),
    [source]
  );

  const handleSourceChange = (nextSource) => {
    setSource(nextSource);
    const formats = SIMULATOR_SOURCE_INPUT_FORMATS[nextSource] || [];
    setInputFormat(formats.length === 1 ? formats[0] : "");
  };

  const canSubmit =
    !running &&
    !!source &&
    !!ruleId &&
    !!inputFormat &&
    (inputFormat === "raw" ? rawText.trim().length > 0 : jsonText.trim().length > 0);

  const handleSubmit = async (event) => {
    event.preventDefault();
    setRunError("");

    if (!source || !ruleId || !inputFormat) {
      setRunError("Select a source, rule, and input format before running a simulation.");
      return;
    }

    const payload = { source, rule_id: ruleId, input_format: inputFormat };

    if (inputFormat === "raw") {
      const lines = rawText.split("\n").map((line) => line.trim()).filter(Boolean);
      if (lines.length === 0) {
        setRunError("Paste at least one non-empty raw log line.");
        return;
      }
      payload.raw_lines = lines;
    } else {
      let parsed;
      try {
        parsed = JSON.parse(jsonText);
      } catch (err) {
        setRunError("Pasted JSON input is not valid JSON.");
        return;
      }
      const events = Array.isArray(parsed) ? parsed : [parsed];
      if (events.length === 0 || !events.every((item) => item && typeof item === "object" && !Array.isArray(item))) {
        setRunError("JSON input must be one object or an array of objects.");
        return;
      }
      payload.json_events = events;
    }

    setRunning(true);
    setResult(null);
    try {
      const response = await runDetectionSimulation(payload);
      setResult(response);
    } catch (err) {
      setRunError(err.message || "Unable to run simulation");
    } finally {
      setRunning(false);
    }
  };

  return (
    <section aria-labelledby="detection-simulator-heading" style={panelStyle}>
      <header style={headerStyle}>
        <p style={eyebrowStyle}>SOC Tools</p>
        <h2 id="detection-simulator-heading" data-workspace-heading style={headingStyle}>
          Detection Simulator
        </h2>
        <p style={subtitleStyle}>
          Run pasted events through the real detection and SOAR-preview pipeline inside a transaction
          that is always rolled back. No event, alert, incident, playbook, or response action is ever
          created, queued, or executed by this workspace.
        </p>
      </header>

      <form onSubmit={handleSubmit} style={formStyle} aria-label="Simulation input">
        <div style={fieldRowStyle}>
          <label style={fieldStyle}>
            <span style={fieldLabelStyle}>Source</span>
            <select
              value={source}
              onChange={(event) => handleSourceChange(event.target.value)}
              style={selectStyle}
              aria-label="Event source"
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
            <span style={fieldLabelStyle}>Detection rule</span>
            <select
              value={ruleId}
              onChange={(event) => setRuleId(event.target.value)}
              style={selectStyle}
              aria-label="Detection rule"
              disabled={rulesLoading || !!rulesError}
            >
              <option value="">{rulesLoading ? "Loading rules…" : "Select a rule…"}</option>
              {rules.map((rule) => (
                <option key={rule.rule_id} value={rule.rule_id}>
                  {rule.display_name}
                </option>
              ))}
            </select>
          </label>

          <label style={fieldStyle}>
            <span style={fieldLabelStyle}>Input format</span>
            <select
              value={inputFormat}
              onChange={(event) => setInputFormat(event.target.value)}
              style={selectStyle}
              aria-label="Input format"
              disabled={!source}
            >
              <option value="">{source ? "Select a format…" : "Select a source first"}</option>
              {availableFormats.map((format) => (
                <option key={format} value={format}>
                  {FORMAT_LABELS[format] || format}
                </option>
              ))}
            </select>
          </label>
        </div>

        {rulesError && <p role="alert" style={inlineErrorStyle}>Unable to load detection rules: {rulesError}</p>}

        {inputFormat === "raw" && (
          <label style={textAreaFieldStyle}>
            <span style={fieldLabelStyle}>Raw log line(s) — one event per line</span>
            <textarea
              value={rawText}
              onChange={(event) => setRawText(event.target.value)}
              rows={8}
              style={textAreaStyle}
              aria-label="Raw log input"
              placeholder="Paste one or more raw log lines…"
            />
          </label>
        )}

        {inputFormat === "json" && (
          <label style={textAreaFieldStyle}>
            <span style={fieldLabelStyle}>JSON event(s) — a single object or an array of objects</span>
            <textarea
              value={jsonText}
              onChange={(event) => setJsonText(event.target.value)}
              rows={8}
              style={textAreaStyle}
              aria-label="JSON event input"
              placeholder='{"event_type": "failed_login", "source_ip": "203.0.113.5", ...}'
            />
          </label>
        )}

        {runError && <p role="alert" style={inlineErrorStyle}>{runError}</p>}

        <button type="submit" disabled={!canSubmit} style={runButtonStyle}>
          {running ? "Running simulation…" : "Run Simulation"}
        </button>
      </form>

      <div aria-live="polite">
        {running && <p role="status" style={stateStyle}>Running simulation…</p>}

        {!running && result && (
          <div style={resultsStyle} data-testid="detection-simulator-results">
            <h3 style={resultsHeadingStyle}>Simulation Pipeline</h3>
            <DetectionSimulatorPipeline stages={result.stages} />
            <h3 style={resultsHeadingStyle}>Explanation</h3>
            <DetectionSimulatorExplainability stages={result.stages} />
          </div>
        )}

        {!running && !result && !runError && (
          <p style={emptyStyle}>Select a source, rule, and input, then run a simulation to see results.</p>
        )}
      </div>
    </section>
  );
}

const panelStyle = { color: "#f0f6fc" };
const headerStyle = { marginBottom: "18px" };
const eyebrowStyle = { margin: "0 0 6px", color: "#58a6ff", fontSize: "12px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em" };
const headingStyle = { margin: 0, fontSize: "28px" };
const subtitleStyle = { margin: "8px 0 0", color: "#9da7b3", maxWidth: "760px" };
const formStyle = { display: "flex", flexDirection: "column", gap: "14px", background: "#161b22", border: "1px solid #30363d", borderRadius: "12px", padding: "18px", marginBottom: "20px" };
const fieldRowStyle = { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "14px" };
const fieldStyle = { display: "flex", flexDirection: "column", gap: "6px", minWidth: 0 };
const textAreaFieldStyle = { display: "flex", flexDirection: "column", gap: "6px" };
const fieldLabelStyle = { color: "#8c96a1", fontSize: "12px", textTransform: "uppercase", letterSpacing: "0.05em" };
const selectStyle = { background: "#0d1117", color: "#f0f6fc", border: "1px solid #30363d", borderRadius: "8px", padding: "8px 10px", fontSize: "14px" };
const textAreaStyle = { background: "#0d1117", color: "#f0f6fc", border: "1px solid #30363d", borderRadius: "8px", padding: "10px", fontSize: "13px", fontFamily: "monospace", resize: "vertical" };
const runButtonStyle = { alignSelf: "flex-start", border: "1px solid #388bfd", background: "#1f6feb", color: "#fff", borderRadius: "8px", padding: "9px 18px", fontWeight: 600, cursor: "pointer" };
const inlineErrorStyle = { border: "1px solid #f85149", background: "rgba(248,81,73,.12)", color: "#ffa198", padding: "10px 12px", borderRadius: "8px", margin: 0 };
const stateStyle = { color: "#9da7b3", padding: "12px 0" };
const emptyStyle = { color: "#c9d1d9", background: "#161b22", border: "1px solid #30363d", padding: "14px", borderRadius: "8px" };
const resultsStyle = { display: "flex", flexDirection: "column", gap: "10px" };
const resultsHeadingStyle = { margin: "18px 0 6px", fontSize: "16px", color: "#f0f6fc" };

export default DetectionSimulatorPanel;
