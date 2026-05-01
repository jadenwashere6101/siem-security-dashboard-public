import React, { useEffect, useState } from "react";
import {
  loadDetectionRules,
  updateDetectionRule,
} from "../services/detectionRulesService";

function DetectionRulesPanel({
  cardStyle,
  cardHeaderStyle,
  cardTitleStyle,
  cardSubtitleStyle,
}) {
  const [rules, setRules] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [editingRuleId, setEditingRuleId] = useState("");
  const [draftParameters, setDraftParameters] = useState({});
  const [saveError, setSaveError] = useState("");
  const [saveSuccess, setSaveSuccess] = useState("");
  const [saving, setSaving] = useState(false);

  const formatUpdatedAt = (value) => {
    if (!value) {
      return "Code defaults";
    }

    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return value;
    }

    return new Intl.DateTimeFormat("en-US", {
      month: "short",
      day: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
      timeZone: "UTC",
      timeZoneName: "short",
    }).format(date);
  };

  const loadRules = async () => {
    try {
      setLoading(true);
      setError("");

      const data = await loadDetectionRules();

      setRules(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(err.message || "Unable to load detection rules");
      setRules([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadRules();
  }, []);

  useEffect(() => {
    if (!saveSuccess) {
      return undefined;
    }

    const timeout = setTimeout(() => {
      setSaveSuccess("");
    }, 2500);

    return () => clearTimeout(timeout);
  }, [saveSuccess]);

  const startEditingRule = (rule) => {
    setEditingRuleId(rule.rule_id);
    setDraftParameters(
      Object.fromEntries(
        Object.entries(rule.parameters || {}).map(([key, value]) => [key, String(value)])
      )
    );
    setSaveError("");
    setSaveSuccess("");
  };

  const cancelEditingRule = () => {
    setEditingRuleId("");
    setDraftParameters({});
    setSaveError("");
    setSaveSuccess("");
    setSaving(false);
  };

  const handleDraftParameterChange = (key, value) => {
    setDraftParameters((prev) => ({
      ...prev,
      [key]: value,
    }));
  };

  const saveRule = async (ruleId) => {
    try {
      setSaving(true);
      setSaveError("");
      setSaveSuccess("");

      const payloadParameters = Object.fromEntries(
        Object.entries(draftParameters).map(([key, value]) => [key, Number(value)])
      );

      await updateDetectionRule(ruleId, payloadParameters);

      await loadRules();
      setEditingRuleId("");
      setDraftParameters({});
      setSaveError("");
      setSaveSuccess(`Saved ${ruleId}`);
    } catch (err) {
      setSaveError(err.message || "Unable to update detection rule");
    } finally {
      setSaving(false);
    }
  };

  const formatParameters = (parameters) =>
    Object.entries(parameters || {}).map(([key, value]) => (
      <div key={key} style={parameterRowStyle}>
        <span style={parameterKeyStyle}>{key}</span>
        <span style={parameterValueStyle}>{String(value)}</span>
      </div>
    ));

  const renderEditableParameters = (rule) =>
    Object.entries(rule.parameters || {}).map(([key]) => (
      <div key={key} style={parameterRowStyle}>
        <label style={parameterKeyStyle} htmlFor={`${rule.rule_id}-${key}`}>
          {key}
        </label>
        <input
          id={`${rule.rule_id}-${key}`}
          type="number"
          inputMode="numeric"
          step="1"
          value={draftParameters[key] ?? ""}
          onChange={(e) => handleDraftParameterChange(key, e.target.value)}
          style={parameterInputStyle}
        />
      </div>
    ));

  return (
    <section style={cardStyle}>
      <div style={cardHeaderStyle}>
        <div>
          <p style={sectionLabelStyle}>Administration</p>
          <h2 style={cardTitleStyle}>Detection Rules</h2>
          <p style={cardSubtitleStyle}>
            Read-only view of the current backend detection rule settings.
          </p>
        </div>
      </div>

      <div style={panelContentStyle}>
        {saveSuccess ? <div style={successStateStyle}>{saveSuccess}</div> : null}
        {loading ? (
          <p style={emptyTextStyle}>Loading detection rules...</p>
        ) : error ? (
          <div style={errorStateStyle}>{error}</div>
        ) : rules.length === 0 ? (
          <p style={emptyTextStyle}>No detection rules found.</p>
        ) : (
          <div style={tableWrapperStyle}>
            <table style={tableStyle}>
              <thead>
                <tr>
                  <th style={{ ...headerCellStyle, width: "15%" }}>Rule Name</th>
                  <th style={{ ...headerCellStyle, width: "15%" }}>Rule ID</th>
                  <th style={{ ...headerCellStyle, width: "8%" }}>Active</th>
                  <th style={{ ...headerCellStyle, width: "22%" }}>Description</th>
                  <th style={{ ...headerCellStyle, width: "20%" }}>Parameters</th>
                  <th style={{ ...headerCellStyle, width: "10%" }}>Last Modified By</th>
                  <th style={{ ...headerCellStyle, width: "10%" }}>Last Modified At</th>
                </tr>
              </thead>
              <tbody>
                {rules.map((rule) => (
                  <tr key={rule.rule_id} style={rowStyle}>
                    <td style={bodyCellStyle}>{rule.display_name}</td>
                    <td style={{ ...bodyCellStyle, ...monoCellStyle }}>{rule.rule_id}</td>
                    <td style={bodyCellStyle}>
                      <span
                        style={rule.active ? activeBadgeStyle : inactiveBadgeStyle}
                      >
                        {rule.active ? "Active" : "Inactive"}
                      </span>
                    </td>
                    <td style={bodyCellStyle}>{rule.description}</td>
                    <td style={bodyCellStyle}>
                      <div style={parametersWrapperStyle}>
                        {editingRuleId === rule.rule_id
                          ? renderEditableParameters(rule)
                          : formatParameters(rule.parameters)}
                        {editingRuleId === rule.rule_id ? (
                          <>
                            {saveError ? <div style={inlineErrorStyle}>{saveError}</div> : null}
                            <div style={actionsRowStyle}>
                              <button
                                type="button"
                                onClick={() => saveRule(rule.rule_id)}
                                disabled={saving}
                                style={{
                                  ...actionButtonStyle,
                                  ...primaryActionButtonStyle,
                                  opacity: saving ? 0.7 : 1,
                                  cursor: saving ? "default" : "pointer",
                                }}
                              >
                                {saving ? "Saving..." : "Save"}
                              </button>
                              <button
                                type="button"
                                onClick={cancelEditingRule}
                                disabled={saving}
                                style={{
                                  ...actionButtonStyle,
                                  ...secondaryActionButtonStyle,
                                  opacity: saving ? 0.7 : 1,
                                  cursor: saving ? "default" : "pointer",
                                }}
                              >
                                Cancel
                              </button>
                            </div>
                          </>
                        ) : (
                          <div style={actionsRowStyle}>
                            <button
                              type="button"
                              onClick={() => startEditingRule(rule)}
                              disabled={Boolean(editingRuleId)}
                              style={{
                                ...actionButtonStyle,
                                ...secondaryActionButtonStyle,
                                opacity: editingRuleId ? 0.55 : 1,
                                cursor: editingRuleId ? "default" : "pointer",
                              }}
                            >
                              Edit
                            </button>
                          </div>
                        )}
                      </div>
                    </td>
                    <td style={bodyCellStyle}>
                      {rule.has_override ? (
                        rule.updated_by || <span style={mutedTextStyle}>Unknown</span>
                      ) : (
                        <span style={mutedTextStyle}>Defaults</span>
                      )}
                    </td>
                    <td style={bodyCellStyle}>
                      {rule.has_override ? (
                        formatUpdatedAt(rule.updated_at)
                      ) : (
                        <span style={mutedTextStyle}>Code defaults</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}

const panelContentStyle = {
  padding: "24px 20px 22px",
};

const sectionLabelStyle = {
  margin: "0 0 8px 0",
  color: "#8b949e",
  fontSize: "10px",
  fontWeight: "700",
  letterSpacing: "0.14em",
  textTransform: "uppercase",
};

const emptyTextStyle = {
  margin: 0,
  color: "#8b949e",
  fontSize: "14px",
};

const errorStateStyle = {
  padding: "12px 14px",
  borderRadius: "10px",
  backgroundColor: "rgba(248, 81, 73, 0.12)",
  border: "1px solid rgba(248, 81, 73, 0.28)",
  color: "#ffa198",
  fontSize: "13px",
};

const successStateStyle = {
  marginBottom: "14px",
  padding: "12px 14px",
  borderRadius: "10px",
  backgroundColor: "rgba(34, 197, 94, 0.10)",
  border: "1px solid rgba(34, 197, 94, 0.25)",
  color: "#86efac",
  fontSize: "13px",
};

const tableWrapperStyle = {
  overflowX: "auto",
};

const tableStyle = {
  width: "100%",
  minWidth: "980px",
  borderCollapse: "collapse",
};

const headerCellStyle = {
  textAlign: "left",
  padding: "12px 14px",
  color: "#8b949e",
  fontSize: "12px",
  fontWeight: "700",
  letterSpacing: "0.04em",
  textTransform: "uppercase",
  borderBottom: "1px solid #30363d",
};

const bodyCellStyle = {
  padding: "14px",
  color: "#e6edf3",
  borderBottom: "1px solid #30363d",
  fontSize: "13px",
  verticalAlign: "top",
};

const rowStyle = {
  backgroundColor: "#161b22",
};

const monoCellStyle = {
  fontFamily: "'Courier New', monospace",
  fontSize: "12px",
  color: "#d29922",
};

const mutedTextStyle = {
  color: "#8b949e",
  fontSize: "12px",
};

const activeBadgeStyle = {
  display: "inline-block",
  padding: "4px 8px",
  borderRadius: "999px",
  fontSize: "10px",
  fontWeight: "700",
  textTransform: "uppercase",
  color: "#86efac",
  backgroundColor: "rgba(34, 197, 94, 0.10)",
  border: "1px solid rgba(34, 197, 94, 0.25)",
};

const inactiveBadgeStyle = {
  display: "inline-block",
  padding: "4px 8px",
  borderRadius: "999px",
  fontSize: "10px",
  fontWeight: "700",
  textTransform: "uppercase",
  color: "#8b949e",
  backgroundColor: "#0d1117",
  border: "1px solid #30363d",
};

const parametersWrapperStyle = {
  display: "grid",
  gap: "8px",
};

const parameterRowStyle = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: "12px",
  padding: "8px 10px",
  borderRadius: "8px",
  backgroundColor: "#0d1117",
  border: "1px solid #21262d",
};

const parameterKeyStyle = {
  color: "#8b949e",
  fontSize: "12px",
  fontWeight: "700",
  fontFamily: "'Courier New', monospace",
};

const parameterValueStyle = {
  color: "#e6edf3",
  fontSize: "12px",
  fontWeight: "600",
};

const parameterInputStyle = {
  width: "96px",
  padding: "6px 8px",
  borderRadius: "8px",
  border: "1px solid #30363d",
  backgroundColor: "#161b22",
  color: "#e6edf3",
  fontSize: "12px",
  outline: "none",
  boxSizing: "border-box",
};

const actionsRowStyle = {
  display: "flex",
  alignItems: "center",
  gap: "8px",
  marginTop: "6px",
  flexWrap: "wrap",
};

const actionButtonStyle = {
  padding: "7px 12px",
  borderRadius: "8px",
  fontSize: "12px",
  fontWeight: "700",
  border: "1px solid #30363d",
  transition: "opacity 120ms ease",
};

const primaryActionButtonStyle = {
  backgroundColor: "#1f6feb",
  borderColor: "#1f6feb",
  color: "#ffffff",
};

const secondaryActionButtonStyle = {
  backgroundColor: "#0d1117",
  color: "#c9d1d9",
};

const inlineErrorStyle = {
  padding: "10px 12px",
  borderRadius: "8px",
  backgroundColor: "rgba(248, 81, 73, 0.12)",
  border: "1px solid rgba(248, 81, 73, 0.28)",
  color: "#ffa198",
  fontSize: "12px",
};

export default DetectionRulesPanel;
