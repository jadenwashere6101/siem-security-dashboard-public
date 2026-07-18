import React, { useState } from "react";

function FloatingSiemChat({ onAsk, disabled = false }) {
  const [open, setOpen] = useState(false);
  const [message, setMessage] = useState("");

  const submit = (event) => {
    event.preventDefault();
    const trimmed = message.trim();
    if (!trimmed || typeof onAsk !== "function") return;
    onAsk(trimmed);
    setMessage("");
    setOpen(true);
  };

  return (
    <div style={containerStyle}>
      {open ? (
        <form onSubmit={submit} style={formStyle} aria-label="General SIEM AI chat">
          <div style={formHeaderStyle}>
            <strong>Ask about this SIEM</strong>
            <button type="button" onClick={() => setOpen(false)} style={closeButtonStyle} aria-label="Close AI chat">
              ×
            </button>
          </div>
          <textarea
            value={message}
            onChange={(event) => setMessage(event.target.value)}
            placeholder="Ask a general question about what you are seeing..."
            rows={3}
            style={textareaStyle}
          />
          <button type="submit" disabled={disabled || !message.trim()} style={submitButtonStyle(disabled || !message.trim())}>
            Ask AI
          </button>
        </form>
      ) : null}
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        disabled={disabled}
        style={fabStyle(disabled)}
        aria-label="Open general SIEM AI chat"
      >
        Ask AI
      </button>
    </div>
  );
}

const containerStyle = { position: "fixed", right: "18px", bottom: "18px", zIndex: 9996 };
const formStyle = {
  width: "min(360px, calc(100vw - 28px))",
  marginBottom: "12px",
  padding: "14px",
  borderRadius: "16px",
  border: "1px solid rgba(125, 211, 252, 0.35)",
  background: "rgba(15, 23, 42, 0.98)",
  color: "#e2e8f0",
  boxShadow: "0 20px 60px rgba(0,0,0,0.45)",
};
const formHeaderStyle = { display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "10px" };
const closeButtonStyle = { background: "transparent", border: "none", color: "#e2e8f0", fontSize: "20px", cursor: "pointer" };
const textareaStyle = {
  width: "100%",
  boxSizing: "border-box",
  border: "1px solid #334155",
  borderRadius: "10px",
  background: "#020617",
  color: "#e2e8f0",
  padding: "10px",
  resize: "vertical",
};
const submitButtonStyle = (disabled) => ({
  marginTop: "10px",
  width: "100%",
  border: "none",
  borderRadius: "999px",
  padding: "9px 12px",
  background: disabled ? "#334155" : "#0ea5e9",
  color: "#fff",
  cursor: disabled ? "not-allowed" : "pointer",
  fontWeight: 700,
});
const fabStyle = (disabled) => ({
  border: "1px solid rgba(125, 211, 252, 0.5)",
  borderRadius: "999px",
  padding: "12px 16px",
  background: disabled ? "#334155" : "linear-gradient(135deg, #0f766e, #0ea5e9)",
  color: "#fff",
  fontWeight: 800,
  cursor: disabled ? "not-allowed" : "pointer",
  boxShadow: "0 18px 40px rgba(14, 165, 233, 0.26)",
});

export default FloatingSiemChat;
