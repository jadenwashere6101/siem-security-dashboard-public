function AlertManualActions({
  alertId,
  executeAction,
  executingActionId,
  canTakeAlertActions,
  getActionButtonStyle,
  variant = "row",
}) {
  const panelVariant = variant === "panel";
  const isExecuting = executingActionId === alertId;
  const manualActionNoticeStyle = panelVariant
    ? { marginTop: "6px", fontSize: "12px", color: "#94a3b8" }
    : { fontSize: "12px", color: "#8b949e", marginTop: "4px" };
  const buttonRowStyle = panelVariant
    ? { display: "flex", gap: "8px", marginTop: "8px", flexWrap: "wrap" }
    : { display: "flex", gap: "8px", marginTop: "6px", flexWrap: "wrap" };

  const actions = [
    {
      id: "block_ip",
      label: "Block IP",
      lockedLabel: "🔒 Block IP",
      backgroundColor: "#ff4d4f",
      color: "white",
      accent: "#ff4d4f",
    },
    {
      id: "flag_high_priority",
      label: "Escalate",
      lockedLabel: "🔒 Escalate",
      backgroundColor: "#faad14",
      color: "black",
      accent: "#f59e0b",
    },
    {
      id: "monitor",
      label: "Monitor",
      lockedLabel: "🔒 Monitor",
      backgroundColor: "#52c41a",
      color: "white",
      accent: "#22c55e",
    },
  ];

  return (
    <div style={{ marginTop: panelVariant ? "20px" : "10px" }}>
      <strong>Manual Actions:</strong>
      {!canTakeAlertActions && (
        <div style={manualActionNoticeStyle}>
          Requires elevated privileges
        </div>
      )}

      <div style={buttonRowStyle}>
        {actions.map((action) => {
          const buttonProps = panelVariant
            ? {}
            : {
                onMouseOver: (e) => e.target.style.opacity = "0.85",
                onMouseOut: (e) => e.target.style.opacity = "1",
                disabled: isExecuting,
              };
          const baseStyle = panelVariant
            ? {
                backgroundColor: action.backgroundColor,
                color: action.color,
                border: "none",
                padding: "6px 10px",
                borderRadius: "6px",
                cursor: "pointer",
                fontWeight: "bold",
                transition: "opacity 120ms ease, border-color 120ms ease, background-color 120ms ease",
              }
            : {
                backgroundColor: action.backgroundColor,
                color: action.color,
                border: "none",
                padding: "6px 10px",
                borderRadius: "6px",
                cursor: isExecuting ? "not-allowed" : "pointer",
                fontWeight: "bold",
                opacity: isExecuting ? 0.6 : 1,
                transition: "opacity 120ms ease, border-color 120ms ease, background-color 120ms ease",
              };
          const style = panelVariant
            ? getActionButtonStyle(baseStyle, action.accent)
            : {
                ...getActionButtonStyle(baseStyle, action.accent),
                opacity: isExecuting ? 0.6 : 1,
              };

          return (
            <button
              key={action.id}
              onClick={() => executeAction(alertId, action.id)}
              title={canTakeAlertActions ? action.label : "Requires elevated privileges"}
              style={style}
              {...buttonProps}
            >
              {isExecuting ? "Executing..." : canTakeAlertActions ? action.label : action.lockedLabel}
            </button>
          );
        })}
      </div>
    </div>
  );
}

export default AlertManualActions;
