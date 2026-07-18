import React from "react";

function AiAssistantButton({ children, onClick, disabled = false, loading = false, title = "" }) {
  const unavailable = disabled || loading || typeof onClick !== "function";
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={unavailable}
      aria-busy={loading ? "true" : "false"}
      title={title}
      style={{
        border: "1px solid rgba(125, 211, 252, 0.45)",
        background: unavailable ? "rgba(30, 41, 59, 0.75)" : "linear-gradient(135deg, #0f766e, #0ea5e9)",
        color: unavailable ? "#94a3b8" : "#ecfeff",
        borderRadius: "999px",
        padding: "6px 11px",
        fontSize: "12px",
        fontWeight: 700,
        cursor: unavailable ? "not-allowed" : "pointer",
        boxShadow: unavailable ? "none" : "0 10px 24px rgba(14, 165, 233, 0.18)",
      }}
    >
      {loading ? "Asking AI..." : children || "Ask AI"}
    </button>
  );
}

export default AiAssistantButton;
