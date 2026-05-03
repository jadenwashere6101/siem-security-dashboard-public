function AlertsToast({ toastMessage, toastType }) {
  return (
    toastMessage && (
      <div
        style={{
          position: "fixed",
          top: "20px",
          right: "20px",
          backgroundColor: toastType === "error" ? "#2d1117" : "#111827",
          color: toastType === "error" ? "#ffb4b4" : "#fff",
          padding: "10px 14px",
          borderRadius: "8px",
          border: toastType === "error" ? "1px solid #f85149" : "1px solid #374151",
          boxShadow: "0 4px 12px rgba(0,0,0,0.3)",
          zIndex: 9999,
          fontSize: "14px",
          fontWeight: "600",
          whiteSpace: "pre-line",
          maxWidth: "340px",
          lineHeight: "1.45",
        }}
      >
        {toastMessage}
      </div>
    )
  );
}

export default AlertsToast;
