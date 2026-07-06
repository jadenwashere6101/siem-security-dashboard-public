import React from "react";

import { SIDEBAR_NAV_ID } from "./Sidebar";

function TopBar({ isCollapsed = false, onToggleCollapse, title, eyebrow, children }) {
  return (
    <header style={topBarStyle}>
      <div style={leftGroupStyle}>
        <button
          type="button"
          onClick={onToggleCollapse}
          aria-expanded={!isCollapsed}
          aria-controls={SIDEBAR_NAV_ID}
          aria-label="Toggle navigation"
          style={hamburgerButtonStyle}
        >
          <span aria-hidden="true">☰</span>
        </button>

        {(eyebrow || title) && (
          <div>
            {eyebrow && <p style={eyebrowStyle}>{eyebrow}</p>}
            {title && <h1 style={titleStyle}>{title}</h1>}
          </div>
        )}
      </div>

      <div style={rightSlotStyle}>{children}</div>
    </header>
  );
}

const topBarStyle = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: "12px",
  padding: "10px 16px",
  backgroundColor: "#0d1117",
  borderBottom: "1px solid #30363d",
  boxSizing: "border-box",
};

const leftGroupStyle = {
  display: "flex",
  alignItems: "center",
  gap: "12px",
  minWidth: 0,
};

const hamburgerButtonStyle = {
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  width: "36px",
  height: "36px",
  padding: 0,
  borderRadius: "8px",
  border: "1px solid #30363d",
  backgroundColor: "#161b22",
  color: "#e6edf3",
  fontSize: "16px",
  cursor: "pointer",
  flexShrink: 0,
};

const eyebrowStyle = {
  margin: "0 0 2px 0",
  color: "#8b949e",
  fontSize: "10px",
  fontWeight: "700",
  letterSpacing: "0.14em",
  textTransform: "uppercase",
};

const titleStyle = {
  margin: 0,
  fontSize: "16px",
  fontWeight: "600",
  color: "#e6edf3",
  whiteSpace: "nowrap",
  overflow: "hidden",
  textOverflow: "ellipsis",
};

const rightSlotStyle = {
  display: "flex",
  alignItems: "center",
  gap: "12px",
  flexShrink: 0,
};

export default TopBar;
