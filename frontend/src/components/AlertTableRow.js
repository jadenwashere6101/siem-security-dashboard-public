import AlertResponseIndicator from "./AlertResponseIndicator";
import {
  sourceBadgeStackStyle,
  sourceBadgeStyle,
  sourceTypeTextStyle,
} from "./alertsTableStyles";
import {
  getBehavioralReputation,
  getExternalReputation,
  getReputationBadgeStyle,
} from "../utils/alertDisplay";

function AlertTableRow({
  alert,
  sourceBadge,
  targetedAlertMeta,
  operationalHistoryBadge,
  isSelected,
  isHovered,
  onRowClick,
  onHoverStart,
  onHoverEnd,
  onResolve,
  canTakeAlertActions,
  getActionButtonStyle,
  getSeverityBadgeStyle,
  formatTimestamp = (value) => value,
  visibleColumns = {
    id: true,
    type: true,
    source: true,
    sourceIp: true,
    behavior: true,
    severity: true,
    message: true,
    createdAt: true,
    action: true,
  },
  tableRowStyle,
  bodyCellStyle,
  monoCellStyle,
}) {
  const externalReputation = getExternalReputation(alert);
  const behavioralReputation = getBehavioralReputation(alert);
  const cooldownActive = Boolean(alert.pfsense_quality?.cooldown?.active);
  const suppressedRollup = Boolean(alert.pfsense_quality?.suppressed_rollup);
  const investigationValue = alert.investigation_value;
  const alertStory = alert.alert_story;
  const visibleReasons = Array.isArray(investigationValue?.reasons)
    ? investigationValue.reasons.slice(0, 2)
    : [];

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

      {visibleColumns.type && (
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
      )}

      {visibleColumns.source && (
      <td style={bodyCellStyle}>
        <div style={sourceBadgeStackStyle}>
          <span style={{ ...sourceBadgeStyle, ...sourceBadge.style }} title={`Source: ${sourceBadge.label}`}>
            {sourceBadge.label}
          </span>
          <span style={sourceTypeTextStyle}>{sourceBadge.subLabel}</span>
        </div>
      </td>
      )}

      {visibleColumns.sourceIp && (
      <td style={{ ...bodyCellStyle, ...monoCellStyle }}>
        <div>{alert.source_ip}</div>
        <div style={{ fontSize: "12px", color: "#94a3b8", marginTop: "4px" }}>
          {alert.city && alert.country
            ? `${alert.city}, ${alert.country}`
            : "Location unavailable"}
        </div>
      </td>
      )}

      {visibleColumns.behavior && (
      <td style={bodyCellStyle}>
        <div style={sourceBadgeStackStyle}>
          <span
            style={{ ...sourceBadgeStyle, ...getReputationBadgeStyle(externalReputation.label) }}
            title={`External threat intelligence: ${externalReputation.label} (${externalReputation.score ?? "n/a"}) via ${externalReputation.source}`}
          >
            Threat Intel: {externalReputation.label}
          </span>
          <span style={sourceTypeTextStyle}>
            Score {externalReputation.score ?? "n/a"} · {externalReputation.source}
          </span>
          <span
            style={{ ...sourceBadgeStyle, ...getReputationBadgeStyle(behavioralReputation.label) }}
            title={`Behavioral reputation: ${behavioralReputation.label} (${behavioralReputation.score})`}
          >
            Behavioral: {behavioralReputation.label}
          </span>
          <span style={sourceTypeTextStyle}>Score {behavioralReputation.score}</span>
        </div>
      </td>
      )}

      {visibleColumns.severity && (
      <td style={bodyCellStyle}>
        <div>
          <span style={getSeverityBadgeStyle(alert.severity)}>
            {alert.severity}
          </span>
        </div>
        {investigationValue?.label ? (
          <div style={{ fontSize: "12px", color: "#cbd5e1", marginTop: "6px" }}>
            {investigationValue.label}
          </div>
        ) : null}
      </td>
      )}

      {visibleColumns.message && (
      <td style={bodyCellStyle}>
        <div>{alert.message}</div>
        {alertStory?.headline ? (
          <div style={{ fontSize: "12px", color: "#e2e8f0", marginTop: "6px" }}>
            {alertStory.headline}
            {alertStory.disposition ? ` · ${alertStory.disposition}` : ""}
          </div>
        ) : null}
        {visibleReasons.length > 0 ? (
          <div style={{ fontSize: "12px", color: "#94a3b8", marginTop: "6px" }}>
            {visibleReasons.map((reason) => reason.text).join(" · ")}
          </div>
        ) : null}
        {cooldownActive || suppressedRollup || operationalHistoryBadge ? (
          <div style={{ display: "flex", gap: "6px", flexWrap: "wrap", marginTop: "8px" }}>
            {operationalHistoryBadge ? (
              <span
                style={{
                  ...sourceBadgeStyle,
                  backgroundColor: "rgba(244, 114, 182, 0.12)",
                  color: "#fbcfe8",
                  borderColor: "rgba(244, 114, 182, 0.28)",
                }}
              >
                {operationalHistoryBadge}
              </span>
            ) : null}
            {cooldownActive ? (
              <span
                style={{
                  ...sourceBadgeStyle,
                  backgroundColor: "rgba(250, 204, 21, 0.12)",
                  color: "#fde68a",
                  borderColor: "rgba(250, 204, 21, 0.32)",
                }}
              >
                Cooldown active
              </span>
            ) : null}
            {suppressedRollup ? (
              <span
                style={{
                  ...sourceBadgeStyle,
                  backgroundColor: "rgba(96, 165, 250, 0.12)",
                  color: "#bfdbfe",
                  borderColor: "rgba(96, 165, 250, 0.32)",
                }}
              >
                Suppressed roll-up
              </span>
            ) : null}
          </div>
        ) : null}
      </td>
      )}

      {visibleColumns.createdAt && (
      <td style={{ ...bodyCellStyle, ...monoCellStyle }}>
        {formatTimestamp(alert.created_at)}
      </td>
      )}

      {visibleColumns.action && (
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
      )}
    </tr>
  );
}

export default AlertTableRow;
