import React, { useEffect, useState } from "react";

import { loadSeverityResponseMatrix } from "../services/severityResponseMatrixService";

function SeverityResponseMatrixPanel({
  cardStyle,
  cardHeaderStyle,
  cardTitleStyle,
  cardSubtitleStyle,
  onNavigate,
}) {
  const [matrix, setMatrix] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    const run = async () => {
      setLoading(true);
      setError("");
      try {
        const data = await loadSeverityResponseMatrix();
        if (active) {
          setMatrix(data);
        }
      } catch (requestError) {
        if (active) {
          setError(requestError.message || "Unable to load severity and response matrix");
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    };
    run();
    return () => {
      active = false;
    };
  }, []);

  return (
    <section style={cardStyle} aria-labelledby="severity-response-matrix-title">
      <div style={cardHeaderStyle}>
        <div>
          <p style={sectionLabelStyle}>SOC</p>
          <h2 id="severity-response-matrix-title" style={cardTitleStyle}>
            Severity & Response Matrix
          </h2>
          <p style={cardSubtitleStyle}>
            Backend-authored severity philosophy, notification behavior, and live playbook response
            expectations.
          </p>
        </div>
      </div>

      {loading ? <p style={mutedStyle}>Loading matrix…</p> : null}
      {error ? <div role="alert" style={errorStyle}>{error}</div> : null}

      {!loading && !error && matrix ? (
        <div style={contentStyle}>
          <div style={statementStyle}>{matrix.page_statement}</div>

          <div style={linkRowStyle}>
            <button
              type="button"
              onClick={() => onNavigate?.(matrix.links?.detection_rules_section_id || "detection-rules")}
              style={linkButtonStyle}
            >
              Detection Rules
            </button>
            <button
              type="button"
              onClick={() => onNavigate?.(matrix.links?.notification_policy_section_id || "notification-policy")}
              style={linkButtonStyle}
            >
              Notification Policy
            </button>
          </div>

          <div style={definitionGridStyle}>
            {(matrix.severity_definitions || []).map((definition) => (
              <article key={definition.severity} style={definitionCardStyle}>
                <h3 style={definitionTitleStyle}>{String(definition.severity || "").toUpperCase()}</h3>
                <DefinitionRow label="Definition" value={definition.definition} />
                <DefinitionRow label="Analyst expectation" value={definition.analyst_expectation} />
                <DefinitionRow label="Incident behavior / priority" value={definition.incident_behavior} />
                <DefinitionRow label="Slack eligibility / timing" value={definition.slack_eligibility_timing} />
                <DefinitionRow label="Approval requirement" value={definition.approval_requirement} />
                <DefinitionRow label="Containment behavior" value={definition.containment_behavior} />
              </article>
            ))}
          </div>

          <div style={tableShellStyle}>
            <table style={tableStyle}>
              <thead>
                <tr>
                  {[
                    "Detection",
                    "Default severity",
                    "Escalation conditions",
                    "Maximum severity",
                    "Creates incident",
                    "Notification behavior",
                    "Response / playbook behavior",
                    "Why",
                  ].map((label) => (
                    <th key={label} scope="col" style={headerCellStyle}>
                      {label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(matrix.rules || []).map((rule) => (
                  <tr key={rule.rule_id}>
                    <td style={cellStyle}>
                      <div style={detectionNameStyle}>{rule.display_name}</div>
                      <div style={detectionMetaStyle}>{rule.rule_id}</div>
                    </td>
                    <td style={cellStyle}>{rule.default_severity}</td>
                    <td style={cellStyle}>{rule.escalation_conditions}</td>
                    <td style={cellStyle}>{rule.maximum_severity}</td>
                    <td style={cellStyle}>{rule.creates_incident}</td>
                    <td style={cellStyle}>{rule.notification_behavior}</td>
                    <td style={cellStyle}>{rule.response_playbook_behavior}</td>
                    <td style={cellStyle}>{rule.why}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </section>
  );
}

function DefinitionRow({ label, value }) {
  return (
    <div style={definitionRowStyle}>
      <div style={definitionLabelStyle}>{label}</div>
      <div style={definitionValueStyle}>{value}</div>
    </div>
  );
}

const sectionLabelStyle = { margin: "0 0 6px", color: "#67e8f9", fontSize: 12, fontWeight: 800, letterSpacing: "0.12em", textTransform: "uppercase" };
const mutedStyle = { color: "#94a3b8", marginTop: 16 };
const errorStyle = { marginTop: 14, padding: 12, borderRadius: 8, background: "#450a0a", color: "#fecaca" };
const contentStyle = { display: "grid", gap: 18, paddingTop: 16 };
const statementStyle = { padding: 14, borderRadius: 10, background: "#082f49", color: "#e0f2fe", lineHeight: 1.6, fontWeight: 600 };
const linkRowStyle = { display: "flex", gap: 10, flexWrap: "wrap" };
const linkButtonStyle = { padding: "10px 14px", borderRadius: 8, border: "1px solid #38bdf8", background: "#0f172a", color: "#e0f2fe", fontWeight: 700, cursor: "pointer" };
const definitionGridStyle = { display: "grid", gap: 14, gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))" };
const definitionCardStyle = { borderRadius: 12, padding: 16, background: "linear-gradient(180deg, #0f172a 0%, #111827 100%)", border: "1px solid #1e293b", display: "grid", gap: 10 };
const definitionTitleStyle = { margin: 0, color: "#f8fafc", fontSize: 16, letterSpacing: "0.08em" };
const definitionRowStyle = { display: "grid", gap: 4 };
const definitionLabelStyle = { color: "#67e8f9", fontSize: 12, fontWeight: 800, textTransform: "uppercase", letterSpacing: "0.08em" };
const definitionValueStyle = { color: "#dbeafe", lineHeight: 1.6 };
const tableShellStyle = { overflowX: "auto", border: "1px solid #1e293b", borderRadius: 12 };
const tableStyle = { width: "100%", borderCollapse: "collapse", minWidth: 1180, background: "#020617" };
const headerCellStyle = { textAlign: "left", padding: 14, borderBottom: "1px solid #1e293b", color: "#bae6fd", fontSize: 12, textTransform: "uppercase", letterSpacing: "0.08em", verticalAlign: "top" };
const cellStyle = { padding: 14, borderBottom: "1px solid #172554", color: "#e2e8f0", lineHeight: 1.6, verticalAlign: "top" };
const detectionNameStyle = { fontWeight: 800, color: "#f8fafc" };
const detectionMetaStyle = { marginTop: 4, color: "#94a3b8", fontSize: 12, fontFamily: "monospace" };

export default SeverityResponseMatrixPanel;
