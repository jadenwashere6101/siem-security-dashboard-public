function AlertSidePanel({ onClose, children }) {
  return (
    <div
      style={{
        position: "fixed",
        top: 0,
        right: 0,
        width: "420px",
        height: "100vh",
        backgroundColor: "#0f172a",
        color: "#fff",
        boxShadow: "-4px 0 20px rgba(0,0,0,0.35)",
        zIndex: 9998,
        borderLeft: "1px solid #1f2937",
        display: "flex",
        flexDirection: "column"
      }}
    >
      <div
        onWheel={(e) => {
          e.stopPropagation();
        }}
        style={{
          height: "100%",
          overflowY: "auto",
          overflowX: "hidden",
          WebkitOverflowScrolling: "touch",
          padding: "20px"
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: "16px"
          }}
        >
          <h2 style={{ margin: 0, fontSize: "20px" }}>Alert Details</h2>

          <button
            onClick={onClose}
            style={{
              background: "transparent",
              color: "#fff",
              border: "none",
              fontSize: "22px",
              cursor: "pointer"
            }}
          >
            ×
          </button>
        </div>

        {children}
      </div>
    </div>
  );
}

export default AlertSidePanel;
