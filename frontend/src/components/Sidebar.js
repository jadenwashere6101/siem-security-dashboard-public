import React from "react";

import { theme } from "../theme";

export const SIDEBAR_NAV_ID = "sidebar-shell-nav";

const SECTION_ICONS = {
  dashboard: "▦",
  "source-health": "●",
  "soc-command-center": "⌁",
  "soc-briefings": "▤",
  "recon-history": "⌕",
  "severity-response-matrix": "◆",
  "response-registry": "◎",
  "threat-hunt": "⌖",
  "detection-simulator": "◇",
  "detection-rules": "≡",
  "pfsense-ingest-filters": "▥",
  "notification-policy": "✉",
  "admin-users": "◉",
  "admin-audit-logs": "◷",
  "repo-architecture-assistant": "AI",
  "soar-queue": "↻",
  "soar-incidents": "!",
  "soar-approvals": "✓",
  "soar-playbooks": "▶",
  "soar-playbook-metrics": "▧",
  "soar-integrations": "⇄",
  "soar-operations": "⚙",
  settings: "⚙",
};

function iconForSection(section) {
  if (SECTION_ICONS[section.id]) return SECTION_ICONS[section.id];
  if (section.group === "live logs") return "≋";
  return "•";
}

function Sidebar({
  sections = [],
  roleFlags = {},
  activeSectionId,
  onNavigate,
  isCollapsed = false,
  isOverlay = false,
  isOpen = true,
  statusLabel,
  versionLabel,
}) {
  const sidebarWidth = isOverlay ? 280 : getDockedSidebarWidth(isCollapsed);
  const visibleSections = sections.filter((section) =>
    typeof section.visibleWhen === "function" ? section.visibleWhen(roleFlags) : true
  );

  const groups = [];
  const groupIndexByName = new Map();

  visibleSections.forEach((section) => {
    const groupName = section.group || "";

    if (!groupIndexByName.has(groupName)) {
      groupIndexByName.set(groupName, groups.length);
      groups.push({ name: groupName, sections: [] });
    }

    groups[groupIndexByName.get(groupName)].sections.push(section);
  });

  return (
    <aside
      style={{
        ...asideStyle,
        ...(isOverlay ? overlayAsideStyle : null),
        width: sidebarWidth,
        borderRight: asideStyle.borderRight,
        transform: isOverlay && !isOpen ? "translateX(-100%)" : "translateX(0)",
      }}
      data-collapsed={isCollapsed ? "true" : "false"}
      data-overlay={isOverlay ? "true" : "false"}
      aria-hidden={isOverlay && !isOpen ? "true" : undefined}
    >
      <nav id={SIDEBAR_NAV_ID} aria-label="Primary" style={{ ...navStyle, ...(isCollapsed ? collapsedNavStyle : null) }}>
        {groups.map((group) => (
            <div
              key={group.name || "ungrouped"}
              role="group"
              aria-label={group.name || undefined}
              style={groupStyle}
            >
              {group.name && !isCollapsed && (
                <p aria-hidden="true" style={groupHeadingStyle}>
                  {group.name}
                </p>
              )}

              {group.sections.map((section) => {
                const isActive = section.id === activeSectionId;

                return (
                  <button
                    key={section.id}
                    type="button"
                    onClick={() => onNavigate(section.id)}
                    aria-current={isActive ? "page" : undefined}
                    title={section.label}
                    aria-label={section.label}
                    style={{
                      ...navButtonStyle,
                      ...(isCollapsed ? collapsedNavButtonStyle : null),
                      ...(isActive ? activeNavButtonStyle : {}),
                    }}
                  >
                    <span aria-hidden="true" style={navIconStyle}>{iconForSection(section)}</span>
                    {!isCollapsed ? <span>{section.label}</span> : null}
                  </button>
                );
              })}
            </div>
          ))}
      </nav>

      {(!isCollapsed || isOverlay) && (
        <div data-testid="sidebar-status-panel" style={statusPanelStyle}>
          {statusLabel && (
            <p style={statusLabelStyle} title={statusLabel}>
              {statusLabel}
            </p>
          )}
          {versionLabel && (
            <p style={versionLabelStyle} title={versionLabel}>
              {versionLabel}
            </p>
          )}
        </div>
      )}
    </aside>
  );
}

function getDockedSidebarWidth(isCollapsed) {
  return isCollapsed ? 68 : 256;
}

const asideStyle = {
  display: "flex",
  flexDirection: "column",
  justifyContent: "space-between",
  flex: "0 0 auto",
  height: "100%",
  backgroundColor: theme.color.bg,
  borderRight: `1px solid ${theme.color.border}`,
  transition: "width 120ms ease, transform 160ms ease",
  overflow: "hidden",
  boxSizing: "border-box",
};

const overlayAsideStyle = {
  position: "fixed",
  inset: "0 auto 0 0",
  zIndex: theme.zIndex.mobileSidebar,
  boxShadow: theme.shadow.overlay,
};

const navStyle = {
  display: "flex",
  flexDirection: "column",
  gap: "18px",
  padding: "16px 12px",
  overflowY: "auto",
};

const collapsedNavStyle = {
  alignItems: "center",
  gap: "12px",
};

const groupStyle = {
  display: "flex",
  flexDirection: "column",
  gap: "4px",
};

const groupHeadingStyle = {
  margin: "0 0 6px 8px",
  color: theme.color.textMuted,
  fontSize: "11px",
  fontWeight: "700",
  textTransform: "uppercase",
  letterSpacing: "0.06em",
};

const navButtonStyle = {
  display: "flex",
  alignItems: "center",
  gap: "10px",
  width: "100%",
  minHeight: "38px",
  padding: "10px 14px",
  borderWidth: "1px",
  borderStyle: "solid",
  borderColor: "transparent",
  borderRadius: theme.radius.sm,
  backgroundColor: "transparent",
  color: theme.color.textSoft,
  fontSize: "13px",
  fontWeight: "600",
  textAlign: "left",
  cursor: "pointer",
  whiteSpace: "nowrap",
  overflow: "hidden",
  textOverflow: "ellipsis",
  boxSizing: "border-box",
};

const collapsedNavButtonStyle = {
  justifyContent: "center",
  width: "42px",
  minHeight: "42px",
  padding: 0,
};

const navIconStyle = {
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  width: "18px",
  minWidth: "18px",
  fontSize: "13px",
  fontWeight: 900,
};

const activeNavButtonStyle = {
  backgroundColor: "#1f6feb",
  borderColor: "#1f6feb",
  color: "#ffffff",
};

const statusPanelStyle = {
  padding: "14px 12px",
  borderTop: `1px solid ${theme.color.border}`,
};

const statusLabelStyle = {
  margin: "0 0 4px 0",
  color: theme.color.success,
  fontSize: "12px",
  fontWeight: "700",
  whiteSpace: "nowrap",
  overflow: "hidden",
  textOverflow: "ellipsis",
};

const versionLabelStyle = {
  margin: 0,
  color: theme.color.textMuted,
  fontSize: "11px",
  whiteSpace: "nowrap",
  overflow: "hidden",
  textOverflow: "ellipsis",
};

export default Sidebar;
