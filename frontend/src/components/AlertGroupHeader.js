import {
  groupCountBadgeStyle,
  groupHeaderContentStyle,
  groupHeaderMetaStyle,
  groupHeaderRowStyle,
  groupHeaderSubtextStyle,
  groupHeaderTitleStyle,
} from "./alertsTableStyles";

function AlertGroupHeader({
  group,
  isCollapsed,
  onToggle,
  getSeverityBadgeStyle,
  groupHeaderCellStyle,
}) {
  return (
    <tr
      style={groupHeaderRowStyle}
      onClick={onToggle}
      title={isCollapsed ? "Expand group" : "Collapse group"}
    >
      <td colSpan="9" style={groupHeaderCellStyle}>
        <div style={groupHeaderContentStyle}>
          <div style={groupHeaderMetaStyle}>
            <span style={groupHeaderTitleStyle}>
              {isCollapsed ? "▸" : "▾"} {group.sourceIp}
            </span>
            <span style={groupHeaderSubtextStyle}>{group.locationLabel}</span>
            <span style={groupCountBadgeStyle}>
              {group.alerts.length} {group.alerts.length === 1 ? "alert" : "alerts"}
            </span>
          </div>
          <div style={groupHeaderMetaStyle}>
            <span style={groupHeaderSubtextStyle}>Highest severity</span>
            <span style={getSeverityBadgeStyle(group.highestSeverity)}>
              {group.highestSeverity}
            </span>
          </div>
        </div>
      </td>
    </tr>
  );
}

export default AlertGroupHeader;
