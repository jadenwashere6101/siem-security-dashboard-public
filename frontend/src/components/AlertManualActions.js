function AlertManualActions({
  alertId,
  sourceIp = "",
  executeAction,
  executingActionId,
  canTakeAlertActions,
  getActionButtonStyle,
  variant = "row",
  lockReason = "Requires analyst or super-admin privileges",
}) {
  const panelVariant = variant === "panel";
  const isExecuting = executingActionId === alertId;
  const missingTarget = !String(sourceIp || "").trim() && !alertId;
  const isLocked = !canTakeAlertActions || missingTarget || isExecuting;
  const effectiveLockReason = !canTakeAlertActions
    ? lockReason
    : missingTarget
      ? "Missing indicator context (source IP / alert)"
      : isExecuting
        ? "Action already in progress"
        : "";

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
      lockedLabel: "Block IP (locked)",
      backgroundColor: "#ff4d4f",
      color: "white",
      accent: "#ff4d4f",
    },
    {
      id: "flag_high_priority",
      label: "Escalate",
      lockedLabel: "Escalate (locked)",
      backgroundColor: "#b45309",
      color: "#ffffff",
      accent: "#f59e0b",
    },
    {
      id: "monitor",
      label: "Monitor",
      lockedLabel: "Monitor (locked)",
      backgroundColor: "#52c41a",
      color: "white",
      accent: "#22c55e",
    },
  ];

  return (
    <div
      style={{
        marginTop: panelVariant ? "20px" : "10px",
        color: "#e5e7eb",
      }}
      data-testid="alert-manual-actions"
    >
      <strong>Manual Actions:</strong>
      {isLocked && (
        <div style={manualActionNoticeStyle} title={effectiveLockReason}>
          {effectiveLockReason || "Actions locked"}
        </div>
      )}

      <div style={buttonRowStyle}>
        {actions.map((action) => {
          const baseStyle = {
            backgroundColor: action.backgroundColor,
            color: action.color,
            border: "none",
            padding: "6px 10px",
            borderRadius: "6px",
            cursor: isLocked ? "not-allowed" : "pointer",
            fontWeight: "bold",
            opacity: isLocked ? 0.55 : 1,
            transition: "opacity 120ms ease, border-color 120ms ease, background-color 120ms ease",
          };
          const style = getActionButtonStyle
            ? {
                ...getActionButtonStyle(baseStyle, action.accent),
                opacity: isLocked ? 0.55 : canTakeAlertActions ? 1 : 0.55,
                cursor: isLocked ? "not-allowed" : "pointer",
              }
            : baseStyle;

          return (
            <button
              key={action.id}
              type="button"
              disabled={isLocked}
              aria-disabled={isLocked}
              title={isLocked ? effectiveLockReason : action.label}
              onClick={() => {
                if (isLocked) return;
                executeAction(alertId, action.id);
              }}
              style={style}
            >
              {isExecuting
                ? "Executing..."
                : canTakeAlertActions
                  ? action.label
                  : action.lockedLabel}
            </button>
          );
        })}
      </div>
    </div>
  );
}

export default AlertManualActions;
