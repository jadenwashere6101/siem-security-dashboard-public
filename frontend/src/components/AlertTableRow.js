import AlertResponseIndicator from "./AlertResponseIndicator";
import {
  sourceBadgeStackStyle,
  sourceBadgeStyle,
  sourceTypeTextStyle,
} from "./alertsTableStyles";
import { getReputationBadgeStyle } from "../utils/alertDisplay";

function AlertTableRow({
  alert,
  sourceBadge,
  targetedAlertMeta,
  isSelected,
  isHovered,
  onRowClick,
  onHoverStart,
  onHoverEnd,
  onResolve,
  canTakeAlertActions,
  getActionButtonStyle,
  getSeverityBadgeStyle,
  tableRowStyle,
  bodyCellStyle,
  monoCellStyle,
}) {
  return (
    <tr
      style={{
        ...tableRowStyle,
        cursor: "pointer",
        backgroundColor:
          isSelected
            ? targetedAlertMeta
              ? targetedAlertMeta.rowStyle.backgroundColor === "#19150d"
                ? "#1f1a11"
                : targetedAlertMeta.rowStyle.backgroundColor
              : "#111827"
            : targetedAlertMeta
              ? targetedAlertMeta.rowStyle.backgroundColor
              : isHovered
                ? "#1b2230"
                : "#161b22",
        borderLeft: targetedAlertMeta
          ? targetedAlertMeta.rowStyle.borderLeft
          : tableRowStyle.borderLeft,
        transition: "background-color 120ms ease",
      }}
      onMouseEnter={onHoverStart}
      onMouseLeave={onHoverEnd}
      onClick={onRowClick}
    >
      <td style={bodyCellStyle}>{alert.id}</td>

      <td style={{ ...bodyCellStyle, ...monoCellStyle }}>
        <div style={sourceBadgeStackStyle}>
          <span>{alert.alert_type}</span>
          {targetedAlertMeta?.badge && (
            <span style={targetedAlertMeta.badgeStyle} title={targetedAlertMeta.description || targetedAlertMeta.badge}>
              {targetedAlertMeta.badge}
            </span>
          )}
        </div>
      </td>

      <td style={bodyCellStyle}>
        <div style={sourceBadgeStackStyle}>
          <span style={{ ...sourceBadgeStyle, ...sourceBadge.style }} title={`Source: ${sourceBadge.label}`}>
            {sourceBadge.label}
          </span>
          <span style={sourceTypeTextStyle}>{sourceBadge.subLabel}</span>
        </div>
      </td>

      <td style={{ ...bodyCellStyle, ...monoCellStyle }}>
        <div>{alert.source_ip}</div>
        <div style={{ fontSize: "12px", color: "#666", marginTop: "4px" }}>
          {alert.city && alert.country
            ? `${alert.city}, ${alert.country}`
            : "Location unavailable"}
        </div>
      </td>

      <td style={bodyCellStyle}>
        <div style={sourceBadgeStackStyle}>
          <span
            style={{ ...sourceBadgeStyle, ...getReputationBadgeStyle(alert.reputation_label) }}
            title={`Behavioral reputation: ${alert.reputation_label || "Normal"} (${alert.reputation_score ?? 0})`}
          >
            {alert.reputation_label || "Normal"}
          </span>
          <span style={sourceTypeTextStyle}>Score {alert.reputation_score ?? 0}</span>
        </div>
      </td>

      <td style={bodyCellStyle}>
        <div>
          <span style={getSeverityBadgeStyle(alert.severity)}>
            {alert.severity}
          </span>
        </div>
      </td>

      <td style={bodyCellStyle}>{alert.message}</td>

      <td style={{ ...bodyCellStyle, ...monoCellStyle }}>
        {alert.created_at}
      </td>

      <td style={bodyCellStyle}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "10px",
            flexWrap: "wrap",
          }}
        >
          <AlertResponseIndicator responseAction={alert.response_action} />
          {alert.status === "open" && (
            <button
              onClick={(e) => onResolve(e)}
              title={canTakeAlertActions ? "Resolve alert" : "Requires elevated privileges"}
              style={getActionButtonStyle(
                {
                  padding: "6px 10px",
                  backgroundColor: "#238636",
                  color: "white",
                  border: "none",
                  borderRadius: "6px",
                  cursor: "pointer",
                  fontWeight: "700",
                  transition: "opacity 120ms ease, border-color 120ms ease, background-color 120ms ease",
                },
                "#f59e0b"
              )}
            >
              {canTakeAlertActions ? "Resolve" : "🔒 Resolve"}
            </button>
          )}
        </div>
      </td>
    </tr>
  );
}

export default AlertTableRow;
