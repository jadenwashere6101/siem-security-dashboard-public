const PRESET_STYLES = {
  default: {
    critical: {
      color: "#fca5a5",
      backgroundColor: "rgba(239, 68, 68, 0.12)",
      border: "1px solid rgba(239, 68, 68, 0.28)",
    },
    high: {
      color: "#f87171",
      backgroundColor: "rgba(248, 113, 113, 0.10)",
      border: "1px solid rgba(248, 113, 113, 0.28)",
    },
    medium: {
      color: "#fbbf24",
      backgroundColor: "rgba(251, 191, 36, 0.10)",
      border: "1px solid rgba(251, 191, 36, 0.26)",
    },
    low: {
      color: "#86efac",
      backgroundColor: "rgba(74, 222, 128, 0.10)",
      border: "1px solid rgba(74, 222, 128, 0.26)",
    },
    unknown: {
      color: "#c9d1d9",
      backgroundColor: "rgba(148, 163, 184, 0.08)",
      border: "1px solid rgba(148, 163, 184, 0.20)",
    },
  },
  colorblindSafe: {
    critical: {
      color: "#f6d32d",
      backgroundColor: "rgba(246, 211, 45, 0.16)",
      border: "1px solid rgba(246, 211, 45, 0.38)",
    },
    high: {
      color: "#ffb000",
      backgroundColor: "rgba(255, 176, 0, 0.12)",
      border: "1px solid rgba(255, 176, 0, 0.34)",
    },
    medium: {
      color: "#7aa6ff",
      backgroundColor: "rgba(122, 166, 255, 0.14)",
      border: "1px solid rgba(122, 166, 255, 0.34)",
    },
    low: {
      color: "#7de3a6",
      backgroundColor: "rgba(125, 227, 166, 0.14)",
      border: "1px solid rgba(125, 227, 166, 0.34)",
    },
    unknown: {
      color: "#d0d7de",
      backgroundColor: "rgba(208, 215, 222, 0.10)",
      border: "1px solid rgba(208, 215, 222, 0.28)",
    },
  },
  highContrast: {
    critical: {
      color: "#ffffff",
      backgroundColor: "#b30000",
      border: "1px solid #ff6666",
    },
    high: {
      color: "#ffffff",
      backgroundColor: "#d9480f",
      border: "1px solid #ff922b",
    },
    medium: {
      color: "#0b1020",
      backgroundColor: "#ffd43b",
      border: "1px solid #fff3bf",
    },
    low: {
      color: "#0b1020",
      backgroundColor: "#69db7c",
      border: "1px solid #b2f2bb",
    },
    unknown: {
      color: "#ffffff",
      backgroundColor: "#495057",
      border: "1px solid #adb5bd",
    },
  },
};

export const getSeverityBadgeStyle = (severity, preset = "default") => {
  const styleSet = PRESET_STYLES[preset] || PRESET_STYLES.default;
  const normalized = String(severity || "").toLowerCase();
  if (normalized === "critical") return styleSet.critical;
  if (normalized === "high") return styleSet.high;
  if (normalized === "medium") return styleSet.medium;
  if (normalized === "low") return styleSet.low;
  return styleSet.unknown;
};
