import React from "react";

import { canonicalOutcomeCountSections } from "../utils/responseOutcomeDisplay";

function CanonicalOutcomeBreakdown({ counts, title = "Canonical outcome counts" }) {
  const sections = canonicalOutcomeCountSections(counts);
  if (sections.length === 0) {
    return (
      <section aria-label={title} style={panelStyle}>
        <h4 style={headingStyle}>{title}</h4>
        <p style={emptyTextStyle}>No canonical outcome counts recorded.</p>
      </section>
    );
  }

  return (
    <section aria-label={title} style={panelStyle}>
      <h4 style={headingStyle}>{title}</h4>
      <div style={gridStyle}>
        {sections.map((section) => (
          <div key={section.groupName} style={sectionStyle}>
            <p style={sectionTitleStyle}>{section.title}</p>
            <ul style={listStyle}>
              {section.entries.map((entry) => (
                <li key={`${section.groupName}-${entry.key}`} style={listItemStyle}>
                  <span>{entry.label}</span>
                  <strong>{entry.count}</strong>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </section>
  );
}

const panelStyle = {
  border: "1px solid #30363d",
  borderRadius: "10px",
  backgroundColor: "#161b22",
  padding: "14px",
};

const headingStyle = {
  margin: "0 0 12px 0",
  color: "#e6edf3",
  fontSize: "14px",
  fontWeight: "800",
};

const emptyTextStyle = {
  margin: 0,
  color: "#8b949e",
  fontSize: "12px",
};

const gridStyle = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
  gap: "10px",
};

const sectionStyle = {
  border: "1px solid #30363d",
  borderRadius: "8px",
  backgroundColor: "#0d1117",
  padding: "10px",
};

const sectionTitleStyle = {
  margin: "0 0 8px 0",
  color: "#8b949e",
  fontSize: "11px",
  fontWeight: "800",
  letterSpacing: "0.06em",
  textTransform: "uppercase",
};

const listStyle = {
  listStyle: "none",
  margin: 0,
  padding: 0,
  display: "grid",
  gap: "6px",
};

const listItemStyle = {
  display: "flex",
  justifyContent: "space-between",
  gap: "8px",
  color: "#c9d1d9",
  fontSize: "12px",
};

export default CanonicalOutcomeBreakdown;
