import React from "react";

export const OPERATIONAL_SCOPE_SINCE_TUNING = "since_tuning";
export const OPERATIONAL_SCOPE_ALL_HISTORY = "all_history";

function OperationalScopeToggle({
  value,
  onChange,
  label = "Scope",
  compact = false,
}) {
  return (
    <fieldset style={{ ...fieldSetStyle, ...(compact ? compactFieldSetStyle : null) }}>
      <legend style={legendStyle}>{label}</legend>
      <div style={buttonRowStyle} role="group" aria-label={label}>
        <button
          type="button"
          onClick={() => onChange(OPERATIONAL_SCOPE_SINCE_TUNING)}
          aria-pressed={value === OPERATIONAL_SCOPE_SINCE_TUNING}
          style={value === OPERATIONAL_SCOPE_SINCE_TUNING ? activeButtonStyle : buttonStyle}
        >
          Since Tuning
        </button>
        <button
          type="button"
          onClick={() => onChange(OPERATIONAL_SCOPE_ALL_HISTORY)}
          aria-pressed={value === OPERATIONAL_SCOPE_ALL_HISTORY}
          style={value === OPERATIONAL_SCOPE_ALL_HISTORY ? activeButtonStyle : buttonStyle}
        >
          All History
        </button>
      </div>
    </fieldset>
  );
}

const fieldSetStyle = {
  margin: 0,
  padding: 0,
  border: "none",
  minWidth: "fit-content",
};

const compactFieldSetStyle = {
  width: "100%",
};

const legendStyle = {
  marginBottom: "6px",
  color: "#94a3b8",
  fontSize: "11px",
  fontWeight: 700,
  letterSpacing: "0.08em",
  textTransform: "uppercase",
};

const buttonRowStyle = {
  display: "inline-flex",
  alignItems: "center",
  gap: "6px",
  flexWrap: "wrap",
};

const buttonStyle = {
  padding: "7px 12px",
  borderRadius: "999px",
  border: "1px solid #30363d",
  backgroundColor: "#0d1117",
  color: "#c9d1d9",
  cursor: "pointer",
  fontSize: "12px",
  fontWeight: 700,
};

const activeButtonStyle = {
  ...buttonStyle,
  borderColor: "rgba(59, 130, 246, 0.5)",
  backgroundColor: "rgba(37, 99, 235, 0.18)",
  color: "#dbeafe",
};

export default OperationalScopeToggle;
