import React from "react";

// Renders backend-authored Sigma compilation preview only. This component
// never parses YAML, never maps fields, and never evaluates a rule against
// events — it displays the normalized_internal_rule_preview and related
// response fields returned by the Detection Simulator API.

function formatPredicate(predicate, depth = 0) {
  if (!predicate || typeof predicate !== "object") return String(predicate);
  if (predicate.field) {
    const value = Array.isArray(predicate.value)
      ? `[${predicate.value.map((item) => JSON.stringify(item)).join(", ")}]`
      : JSON.stringify(predicate.value);
    return `${predicate.field} ${predicate.operator} ${value}`;
  }
  if (predicate.all) {
    return `all (${predicate.all.map((child) => formatPredicate(child, depth + 1)).join("; ")})`;
  }
  if (predicate.any) {
    return `any (${predicate.any.map((child) => formatPredicate(child, depth + 1)).join("; ")})`;
  }
  if (predicate.not) {
    return `not (${formatPredicate(predicate.not, depth + 1)})`;
  }
  return JSON.stringify(predicate);
}

function DetectionSimulatorSigmaPreview({ result }) {
  if (!result || result.simulation_mode !== "sigma_subset_import") {
    return null;
  }

  const preview = result.normalized_internal_rule_preview;
  const compatibility =
    result.sigma_subset_compatibility ||
    (preview && preview.compatibility) ||
    "Strict Sigma subset import — not full Sigma compatibility.";

  return (
    <section aria-labelledby="sigma-preview-heading" data-testid="sigma-internal-rule-preview" style={sectionStyle}>
      <h3 id="sigma-preview-heading" style={headingStyle}>
        Normalized Internal-Rule Preview
      </h3>
      <p role="note" style={compatibilityStyle} data-testid="sigma-compatibility-disclosure">
        {compatibility}
      </p>

      {!preview && (
        <p style={mutedStyle}>No normalized internal-rule preview was returned by the backend.</p>
      )}

      {preview && (
        <>
          <dl style={metaGridStyle} data-testid="sigma-metadata-preview">
            <div style={metaItemStyle}>
              <dt style={dtStyle}>Title</dt>
              <dd style={ddStyle}>{preview.title || "—"}</dd>
            </div>
            <div style={metaItemStyle}>
              <dt style={dtStyle}>ID</dt>
              <dd style={ddStyle}>{preview.id || "—"}</dd>
            </div>
            <div style={metaItemStyle}>
              <dt style={dtStyle}>Level / severity</dt>
              <dd style={ddStyle}>
                {preview.level || "—"} / {preview.severity || "—"}
              </dd>
            </div>
            <div style={metaItemStyle}>
              <dt style={dtStyle}>Canonical source</dt>
              <dd style={ddStyle}>
                {preview.source || "—"} ({preview.source_type || "—"})
              </dd>
            </div>
            <div style={metaItemStyle}>
              <dt style={dtStyle}>Status</dt>
              <dd style={ddStyle}>{preview.status || "—"}</dd>
            </div>
            <div style={metaItemStyle}>
              <dt style={dtStyle}>Author / date</dt>
              <dd style={ddStyle}>
                {preview.author || "—"} / {preview.date || "—"}
              </dd>
            </div>
            <div style={metaItemStyle}>
              <dt style={dtStyle}>Tags</dt>
              <dd style={ddStyle}>{(preview.tags || []).join(", ") || "—"}</dd>
            </div>
            <div style={metaItemStyle}>
              <dt style={dtStyle}>ATT&amp;CK tags</dt>
              <dd style={ddStyle}>{(preview.attack_tags || []).join(", ") || "—"}</dd>
            </div>
            <div style={metaItemStyle}>
              <dt style={dtStyle}>Logsource</dt>
              <dd style={ddStyle}>
                {preview.logsource
                  ? Object.entries(preview.logsource)
                      .map(([key, value]) => `${key}=${value}`)
                      .join(", ")
                  : "—"}
              </dd>
            </div>
            <div style={metaItemStyle}>
              <dt style={dtStyle}>Evaluator</dt>
              <dd style={ddStyle}>{preview.evaluator || "temporary_playground_rule"}</dd>
            </div>
          </dl>

          {preview.description && (
            <p style={descriptionStyle}>
              <strong style={strongStyle}>Description:</strong> {preview.description}
            </p>
          )}

          <div style={predicateBlockStyle}>
            <h4 style={subheadingStyle}>Compiled predicate</h4>
            <pre style={preStyle} data-testid="sigma-compiled-predicate">
              {formatPredicate(preview.condition)}
            </pre>
          </div>
        </>
      )}
    </section>
  );
}

const sectionStyle = {
  background: "#161b22",
  border: "1px solid #30363d",
  borderRadius: "12px",
  padding: "16px",
  marginBottom: "8px",
};
const headingStyle = { margin: "0 0 10px", fontSize: "16px", color: "#f0f6fc" };
const subheadingStyle = { margin: "0 0 8px", fontSize: "13px", color: "#c9d1d9" };
const compatibilityStyle = {
  margin: "0 0 14px",
  color: "#ffa657",
  background: "rgba(255,166,87,.08)",
  border: "1px solid rgba(255,166,87,.35)",
  borderRadius: "8px",
  padding: "10px 12px",
  fontSize: "13px",
};
const metaGridStyle = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
  gap: "12px",
  margin: "0 0 12px",
};
const metaItemStyle = { margin: 0 };
const dtStyle = {
  margin: 0,
  color: "#8c96a1",
  fontSize: "11px",
  textTransform: "uppercase",
  letterSpacing: "0.05em",
};
const ddStyle = { margin: "4px 0 0", color: "#f0f6fc", fontSize: "13px", wordBreak: "break-word" };
const descriptionStyle = { margin: "0 0 12px", color: "#c9d1d9", fontSize: "13px" };
const strongStyle = { color: "#f0f6fc" };
const predicateBlockStyle = { marginTop: "4px" };
const preStyle = {
  margin: 0,
  background: "#0d1117",
  border: "1px solid #30363d",
  borderRadius: "8px",
  padding: "10px",
  color: "#f0f6fc",
  fontSize: "12px",
  whiteSpace: "pre-wrap",
  wordBreak: "break-word",
  fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
};
const mutedStyle = { margin: 0, color: "#9da7b3", fontSize: "13px" };

export default DetectionSimulatorSigmaPreview;
