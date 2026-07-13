import React, { useEffect, useState } from "react";
import {
  loadDetectionRules,
  loadPfsenseDetectionHealth,
  updateDetectionRule,
} from "../services/detectionRulesService";
import { formatAdminTimestamp } from "../utils/adminPanelDisplay";
import { SOURCE_DISPLAY_LABELS } from "../utils/sourceMetadata";

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
  const [togglingRuleId, setTogglingRuleId] = useState("");
  const [healthRows, setHealthRows] = useState([]);
  const [healthLoading, setHealthLoading] = useState(true);
  const [healthError, setHealthError] = useState("");

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

  const loadHealth = async () => {
    try {
      setHealthLoading(true);
      setHealthError("");
      const data = await loadPfsenseDetectionHealth();
      setHealthRows(Array.isArray(data) ? data : []);
    } catch (err) {
      setHealthError(err.message || "Unable to load pfSense detection health");
      setHealthRows([]);
    } finally {
      setHealthLoading(false);
    }
  };

  useEffect(() => {
    loadRules();
    loadHealth();
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
      await loadHealth();
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

  const toggleRuleActive = async (rule) => {
    const nextActive = !rule.active;
    if (!nextActive && !window.confirm(`Disable ${rule.display_name}? Detection will stop for this rule.`)) {
      return;
    }

    const previousRules = rules;
    setRules((current) => current.map((item) => (
      item.rule_id === rule.rule_id ? { ...item, active: nextActive } : item
    )));
    setTogglingRuleId(rule.rule_id);
    setSaveError("");
    setSaveSuccess("");

    try {
      await updateDetectionRule(rule.rule_id, undefined, nextActive);
      await loadRules();
      await loadHealth();
      setSaveSuccess(`${nextActive ? "Enabled" : "Disabled"} ${rule.rule_id}`);
    } catch (err) {
      setRules(previousRules);
      setSaveError(err.message || "Unable to update detection rule");
    } finally {
      setTogglingRuleId("");
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

  const renderApplicableSources = (rule) => (
    <div style={sourcesWrapperStyle}>
      <div style={sourceBadgesStyle} aria-label={`Applicable sources for ${rule.display_name}`}>
        {(rule.applicable_sources || []).map(({ source, source_type: sourceType }) => {
          const evidence = `${source}/${sourceType}`;
          return (
            <span
              key={evidence}
              style={sourceBadgeStyle}
              title={evidence}
              aria-label={`${SOURCE_DISPLAY_LABELS[source] || source}: ${evidence}`}
            >
              {SOURCE_DISPLAY_LABELS[source] || source}
            </span>
          );
        })}
      </div>
      <span style={globalScopeNoteStyle}>One global configuration applies to all listed sources.</span>
    </div>
  );

  const navigateToRule = (ruleId) => {
    const row = document.getElementById(`detection-rule-row-${ruleId}`);
    if (!row) {
      return;
    }
    row.scrollIntoView?.({ block: "center", behavior: "smooth" });
    row.focus?.();
  };

  return (
    <section style={cardStyle}>
      <div style={cardHeaderStyle}>
        <div>
          <p style={sectionLabelStyle}>Administration</p>
          <h2 style={cardTitleStyle}>Detection Rules</h2>
          <p style={cardSubtitleStyle}>
            Manage global detection settings and review read-only source coverage.
          </p>
        </div>
      </div>

      <div style={panelContentStyle}>
        {saveSuccess ? <div style={successStateStyle}>{saveSuccess}</div> : null}
        {saveError && !editingRuleId ? <div role="alert" style={errorStateStyle}>{saveError}</div> : null}
        <section style={healthPanelStyle} aria-labelledby="pfsense-detection-health-heading">
          <div style={healthHeaderStyle}>
            <div>
              <p style={sectionLabelStyle}>Read-only</p>
              <h3 id="pfsense-detection-health-heading" style={healthTitleStyle}>pfSense Detection Health</h3>
            </div>
            <span style={healthWindowStyle}>24h UTC window</span>
          </div>
          {healthLoading ? (
            <p style={emptyTextStyle}>Loading detection health...</p>
          ) : healthError ? (
            <div role="alert" style={errorStateStyle}>{healthError}</div>
          ) : (
            <div style={healthListStyle}>
              {healthRows.map((row) => (
                <button
                  key={row.rule_id}
                  type="button"
                  onClick={() => navigateToRule(row.rule_id)}
                  style={healthRowButtonStyle}
                >
                  <span style={healthRuleNameStyle}>{row.rule_name}</span>
                  <span style={healthMetaStyle}>{row.fired_count_24h} fires</span>
                  <span style={healthMetaStyle}>Highest {row.highest_severity_24h || "none"}</span>
                  <span style={healthMetaStyle}>Last {row.last_fired_at || "never"}</span>
                  <span style={getHealthBadgeStyle(row.health_badge)}>{row.health_badge}</span>
                </button>
              ))}
            </div>
          )}
        </section>
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
                  <th style={{ ...headerCellStyle, width: "10%" }}>Status</th>
                  <th style={{ ...headerCellStyle, width: "18%" }}>Applicable Sources</th>
                  <th style={{ ...headerCellStyle, width: "16%" }}>Description</th>
                  <th style={{ ...headerCellStyle, width: "18%" }}>Global Parameters</th>
                  <th style={{ ...headerCellStyle, width: "8%" }}>Configuration</th>
                  <th style={{ ...headerCellStyle, width: "8%" }}>Last Modified</th>
                </tr>
              </thead>
              <tbody>
                {rules.map((rule) => (
                  <tr key={rule.rule_id} id={`detection-rule-row-${rule.rule_id}`} tabIndex={-1} style={rowStyle}>
                    <td style={bodyCellStyle}>{rule.display_name}</td>
                    <td style={{ ...bodyCellStyle, ...monoCellStyle }}>{rule.rule_id}</td>
                    <td style={bodyCellStyle}>
                      <span
                        style={rule.active ? activeBadgeStyle : inactiveBadgeStyle}
                      >
                        {rule.active ? "Active" : "Inactive"}
                      </span>
                      <button
                        type="button"
                        onClick={() => toggleRuleActive(rule)}
                        disabled={Boolean(togglingRuleId) || saving}
                        aria-label={`${rule.active ? "Disable" : "Enable"} ${rule.display_name}`}
                        aria-pressed={rule.active}
                        style={{
                          ...actionButtonStyle,
                          ...toggleActionButtonStyle,
                          opacity: togglingRuleId || saving ? 0.6 : 1,
                          cursor: togglingRuleId || saving ? "default" : "pointer",
                        }}
                      >
                        {togglingRuleId === rule.rule_id
                          ? "Updating..."
                          : rule.active ? "Disable" : "Enable"}
                      </button>
                    </td>
                    <td style={bodyCellStyle}>{renderApplicableSources(rule)}</td>
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
                      <span style={rule.has_override ? overriddenBadgeStyle : defaultBadgeStyle}>
                        {rule.has_override ? "Overridden" : "Default"}
                      </span>
                      <div style={modifiedDetailStyle}>
                      {rule.has_override ? (
                        rule.updated_by || <span style={mutedTextStyle}>Unknown</span>
                      ) : (
                        <span style={mutedTextStyle}>Defaults</span>
                      )}
                      </div>
                    </td>
                    <td style={bodyCellStyle}>
                      {rule.has_override ? (
                        formatAdminTimestamp(rule.updated_at, "Code defaults")
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

const healthPanelStyle = {
  marginBottom: "18px",
  border: "1px solid #233044",
  borderRadius: "12px",
  padding: "14px",
  backgroundColor: "#0f1621",
};

const healthHeaderStyle = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  gap: "12px",
  flexWrap: "wrap",
  marginBottom: "10px",
};

const healthTitleStyle = {
  margin: 0,
  color: "#e6edf3",
  fontSize: "18px",
};

const healthWindowStyle = {
  color: "#94a3b8",
  fontSize: "12px",
};

const healthListStyle = {
  display: "flex",
  flexDirection: "column",
  gap: "8px",
};

const healthRowButtonStyle = {
  display: "grid",
  gridTemplateColumns: "minmax(180px, 2fr) repeat(3, minmax(110px, 1fr)) auto",
  gap: "10px",
  alignItems: "center",
  width: "100%",
  padding: "10px 12px",
  borderRadius: "10px",
  border: "1px solid #263244",
  backgroundColor: "#111927",
  color: "#e6edf3",
  textAlign: "left",
  cursor: "pointer",
};

const healthRuleNameStyle = {
  fontWeight: "700",
};

const healthMetaStyle = {
  color: "#94a3b8",
  fontSize: "12px",
};

const getHealthBadgeStyle = (badge) => ({
  justifySelf: "end",
  padding: "4px 8px",
  borderRadius: "999px",
  fontSize: "12px",
  fontWeight: "700",
  border: "1px solid transparent",
  backgroundColor:
    badge === "Noisy"
      ? "rgba(248, 113, 113, 0.14)"
      : badge === "Needs Review"
        ? "rgba(250, 204, 21, 0.14)"
        : "rgba(74, 222, 128, 0.14)",
  color:
    badge === "Noisy"
      ? "#fca5a5"
      : badge === "Needs Review"
        ? "#fde68a"
        : "#86efac",
  borderColor:
    badge === "Noisy"
      ? "rgba(248, 113, 113, 0.28)"
      : badge === "Needs Review"
        ? "rgba(250, 204, 21, 0.28)"
        : "rgba(74, 222, 128, 0.28)",
});

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
  minWidth: "1280px",
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

const sourcesWrapperStyle = {
  display: "grid",
  gap: "8px",
};

const sourceBadgesStyle = {
  display: "flex",
  flexWrap: "wrap",
  gap: "6px",
};

const sourceBadgeStyle = {
  display: "inline-block",
  padding: "4px 7px",
  borderRadius: "999px",
  color: "#a5d6ff",
  backgroundColor: "rgba(56, 139, 253, 0.10)",
  border: "1px solid rgba(56, 139, 253, 0.28)",
  fontSize: "10px",
  fontWeight: "700",
};

const globalScopeNoteStyle = {
  color: "#8b949e",
  fontSize: "11px",
  lineHeight: "1.4",
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

const toggleActionButtonStyle = {
  display: "block",
  marginTop: "8px",
  padding: "5px 8px",
  backgroundColor: "#0d1117",
  color: "#c9d1d9",
};

const overriddenBadgeStyle = {
  ...activeBadgeStyle,
  color: "#d2a8ff",
  backgroundColor: "rgba(163, 113, 247, 0.10)",
  border: "1px solid rgba(163, 113, 247, 0.30)",
};

const defaultBadgeStyle = {
  ...inactiveBadgeStyle,
  color: "#c9d1d9",
};

const modifiedDetailStyle = {
  marginTop: "8px",
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
