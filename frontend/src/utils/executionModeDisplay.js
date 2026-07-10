export function normalizeExecutionMode(...values) {
  for (const value of values) {
    const mode = String(value || "").trim().toLowerCase();
    if (mode === "real" || mode === "simulation" || mode === "read_only") {
      return mode;
    }
    if (mode === "read-only" || mode === "readonly") {
      return "read_only";
    }
  }
  return "unknown";
}

export function executionModeNoun(mode) {
  switch (normalizeExecutionMode(mode)) {
    case "real":
      return "real execution";
    case "simulation":
      return "simulation";
    case "read_only":
      return "read-only execution";
    default:
      return "execution";
  }
}

export function executionModeLabel(mode) {
  switch (normalizeExecutionMode(mode)) {
    case "real": return "Real";
    case "simulation": return "Simulation";
    case "read_only": return "Read-only";
    default: return "Unknown";
  }
}
