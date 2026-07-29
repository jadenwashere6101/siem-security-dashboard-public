export const BREAKPOINTS = Object.freeze({
  mobileMax: 639,
  tabletMin: 640,
  tabletMax: 1023,
  desktopMin: 1024,
});

export const viewportModes = Object.freeze({
  mobile: "mobile",
  tablet: "tablet",
  desktop: "desktop",
});

export function getViewportMode(width) {
  const value = Number(width);
  if (!Number.isFinite(value)) return viewportModes.desktop;
  if (value < BREAKPOINTS.tabletMin) return viewportModes.mobile;
  if (value < BREAKPOINTS.desktopMin) return viewportModes.tablet;
  return viewportModes.desktop;
}

export const theme = Object.freeze({
  color: {
    bg: "#0d1117",
    bgRaised: "#161b22",
    bgInset: "#0f1720",
    bgInput: "#0d1117",
    border: "#30363d",
    borderSubtle: "rgba(139, 148, 158, 0.24)",
    text: "#e6edf3",
    textMuted: "#8b949e",
    textSoft: "#c9d1d9",
    ai: "#0ea5e9",
    aiSoft: "#93c5fd",
    aiBg: "rgba(14, 165, 233, 0.14)",
    aiBorder: "rgba(125, 211, 252, 0.45)",
    review: "#d29922",
    reviewSoft: "#f5d487",
    reviewBg: "rgba(217, 164, 65, 0.14)",
    danger: "#f85149",
    dangerSoft: "#fca5a5",
    dangerBg: "rgba(248, 81, 73, 0.14)",
    success: "#3fb950",
    successSoft: "#86efac",
    successBg: "rgba(63, 185, 80, 0.14)",
    neutralBg: "rgba(139, 148, 158, 0.12)",
  },
  spacing: {
    xs: 4,
    sm: 8,
    md: 12,
    lg: 16,
    xl: 20,
    xxl: 24,
    shellDesktop: 32,
    shellTablet: 20,
    shellMobile: 16,
  },
  radius: {
    sm: 8,
    md: 10,
    lg: 12,
    pill: 999,
  },
  typography: {
    label: {
      fontSize: "11px",
      fontWeight: 800,
      letterSpacing: "0.06em",
      textTransform: "uppercase",
    },
    body: {
      fontSize: "13px",
      lineHeight: 1.4,
    },
  },
  shadow: {
    overlay: "0 18px 48px rgba(0, 0, 0, 0.45)",
    raised: "0 10px 30px rgba(0, 0, 0, 0.28)",
    focus: "0 0 0 3px rgba(14, 165, 233, 0.28)",
  },
  zIndex: {
    mobileBackdrop: 9990,
    mobileSidebar: 9991,
  },
});

export const toneStyles = Object.freeze({
  info: {
    color: theme.color.aiSoft,
    backgroundColor: theme.color.aiBg,
    borderColor: "rgba(88, 166, 255, 0.35)",
  },
  warning: {
    color: theme.color.reviewSoft,
    backgroundColor: theme.color.reviewBg,
    borderColor: "rgba(217, 164, 65, 0.36)",
  },
  danger: {
    color: theme.color.dangerSoft,
    backgroundColor: theme.color.dangerBg,
    borderColor: "rgba(248, 81, 73, 0.38)",
  },
  success: {
    color: theme.color.successSoft,
    backgroundColor: theme.color.successBg,
    borderColor: "rgba(63, 185, 80, 0.36)",
  },
  neutral: {
    color: theme.color.textSoft,
    backgroundColor: theme.color.neutralBg,
    borderColor: theme.color.borderSubtle,
  },
});

export function toneForSeverity(severity) {
  const normalized = String(severity || "").toLowerCase();
  if (normalized === "critical" || normalized === "high") return "danger";
  if (normalized === "medium") return "warning";
  if (normalized === "low") return "success";
  return "neutral";
}

export function toneForStatus(status) {
  const normalized = String(status || "").toLowerCase();
  if (["failed", "failure", "blocked", "error", "critical", "danger"].includes(normalized)) {
    return "danger";
  }
  if (["pending", "awaiting_approval", "review", "warning", "retrying"].includes(normalized)) {
    return "warning";
  }
  if (["healthy", "success", "succeeded", "clear", "resolved", "closed"].includes(normalized)) {
    return "success";
  }
  if (["running", "open", "investigating", "info"].includes(normalized)) {
    return "info";
  }
  return "neutral";
}
