import React from "react";

import { SIDEBAR_NAV_ID } from "./Sidebar";
import { theme } from "../theme";

function TopBar({
  isCollapsed = false,
  onToggleCollapse,
  title,
  eyebrow,
  navigationControls = null,
  children,
  viewportMode = "desktop",
  toggleButtonRef = null,
}) {
  const compact = viewportMode !== "desktop";
  return (
    <header style={topBarStyle} data-viewport-mode={viewportMode}>
      <div style={leftGroupStyle}>
        <button
          ref={toggleButtonRef}
          type="button"
          onClick={onToggleCollapse}
          aria-expanded={!isCollapsed}
          aria-controls={SIDEBAR_NAV_ID}
          aria-label="Toggle navigation"
          style={hamburgerButtonStyle}
        >
          <span aria-hidden="true">☰</span>
        </button>

        {navigationControls ? (
          <div style={{ ...navigationControlsStyle, ...(compact ? compactNavigationControlsStyle : null) }}>
            {navigationControls}
          </div>
        ) : null}

        {(eyebrow || title) && (
          <div style={titleBlockStyle}>
            {eyebrow && <p style={eyebrowStyle}>{eyebrow}</p>}
            {title && <h1 style={titleStyle}>{title}</h1>}
          </div>
        )}
      </div>

      <div style={{ ...rightSlotStyle, ...(compact ? compactRightSlotStyle : null) }}>{children}</div>
    </header>
  );
}

const topBarStyle = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: "12px",
  padding: "10px 16px",
  backgroundColor: theme.color.bg,
  borderBottom: `1px solid ${theme.color.border}`,
  boxSizing: "border-box",
  minWidth: 0,
  flexWrap: "wrap",
};

const leftGroupStyle = {
  display: "flex",
  alignItems: "center",
  gap: "12px",
  minWidth: 0,
  flex: "1 1 auto",
};

const hamburgerButtonStyle = {
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  width: "36px",
  height: "36px",
  padding: 0,
  borderRadius: theme.radius.sm,
  border: `1px solid ${theme.color.border}`,
  backgroundColor: theme.color.bgRaised,
  color: theme.color.text,
  fontSize: "16px",
  cursor: "pointer",
  flexShrink: 0,
};

const navigationControlsStyle = {
  display: "inline-flex",
  alignItems: "center",
  gap: "6px",
  flexShrink: 0,
};

const compactNavigationControlsStyle = {
  order: 3,
  width: "100%",
  overflowX: "auto",
};

const titleBlockStyle = {
  minWidth: 0,
};

const eyebrowStyle = {
  margin: "0 0 2px 0",
  color: theme.color.textMuted,
  fontSize: "10px",
  fontWeight: "700",
  letterSpacing: "0.14em",
  textTransform: "uppercase",
};

const titleStyle = {
  margin: 0,
  fontSize: "16px",
  fontWeight: "600",
  color: theme.color.text,
  whiteSpace: "nowrap",
  overflow: "hidden",
  textOverflow: "ellipsis",
};

const rightSlotStyle = {
  display: "flex",
  alignItems: "center",
  gap: "12px",
  flex: "0 1 auto",
  justifyContent: "flex-end",
  minWidth: 0,
  flexWrap: "wrap",
};

const compactRightSlotStyle = {
  width: "100%",
  justifyContent: "flex-start",
};

export default TopBar;
