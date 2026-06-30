import { outcomeLabel } from "./ResponseOutcome";

function AlertResponseLog({ logs, variant = "inline" }) {
  const panelVariant = variant === "panel";

  return (
    <div style={{ marginTop: panelVariant ? "20px" : "10px" }}>
      <strong>Response Log:</strong>

      {logs && logs.length > 0 ? (
        logs.map((log) => {
          let color = "#999";
          const statusLabel = log.response_outcome
            ? outcomeLabel(log.response_outcome)
            : log.status;

          if (log.action === "block_ip") color = "#ff4d4f";
          else if (log.action === "flag_high_priority") color = "#faad14";
          else if (log.action === "monitor") color = "#52c41a";

          return (
            <div
              key={log.id}
              style={panelVariant ? {
                marginTop: "8px",
                padding: "8px",
                borderRadius: "8px",
                backgroundColor: "#1e293b",
                fontSize: "12px",
                display: "flex",
                justifyContent: "space-between"
              } : {
                marginTop: "5px",
                padding: "6px",
                borderRadius: "6px",
                backgroundColor: "#1e1e1e",
                color: "#fff",
                fontSize: "12px",
                display: "flex",
                justifyContent: "space-between"
              }}
            >
              <span>
                <strong style={{ color }}>{log.action.toUpperCase()}</strong>
                {" \u2192 "}
                {statusLabel}
              </span>
              <span style={{ opacity: 0.7 }}>
                {new Date(log.executed_at).toLocaleTimeString()}
              </span>
            </div>
          );
        })
      ) : (
        <div style={panelVariant ? { marginTop: "8px", fontSize: "12px", opacity: 0.7 } : { fontSize: "12px", opacity: 0.6 }}>
          No response actions logged
        </div>
      )}
    </div>
  );
}

export default AlertResponseLog;
