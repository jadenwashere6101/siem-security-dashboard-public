function humanizeLookupStatus(status) {
  const normalized = String(status || "").trim().toLowerCase();
  if (normalized === "pending") return "Refreshing now";
  if (normalized === "stale") return "Cached result expired";
  if (normalized === "provider_unavailable") return "Provider unavailable";
  if (normalized === "failed") return "Lookup failed";
  if (normalized === "succeeded") return "Lookup succeeded";
  return "Lookup neutral";
}

function buildAssessmentLabel(internetNoise) {
  const assessment = String(internetNoise?.assessment || "neutral").toLowerCase();
  const lookupStatus = String(internetNoise?.lookup_status || "unknown").toLowerCase();
  if (assessment === "commodity") return "Known commodity scanner";
  if (assessment === "malicious") return "Known malicious internet activity";
  if (lookupStatus === "pending") return "Internet-noise assessment pending";
  if (lookupStatus === "stale") return "Expired internet-noise assessment";
  if (lookupStatus === "provider_unavailable" || lookupStatus === "failed") {
    return "Internet-noise lookup unavailable";
  }
  return "No internet-noise classification";
}

function buildEffectLabel(internetNoise) {
  if (internetNoise?.local_evidence_override) {
    return "Local evidence kept the higher analyst priority.";
  }
  if (internetNoise?.applied_to_investigation) {
    return "Reduced investigation priority.";
  }
  if (internetNoise?.effect === "shadow_observation") {
    return "Shadow mode: would reduce investigation priority.";
  }
  if (internetNoise?.assessment === "malicious") {
    return "No priority reduction from provider classification alone.";
  }
  return "No prioritization change applied.";
}

export function shouldShowInternetNoise(internetNoise) {
  if (!internetNoise || typeof internetNoise !== "object") {
    return false;
  }
  const assessment = String(internetNoise.assessment || "neutral").toLowerCase();
  const lookupStatus = String(internetNoise.lookup_status || "unknown").toLowerCase();
  return (
    assessment !== "neutral" ||
    internetNoise.local_evidence_override === true ||
    internetNoise.would_reduce_urgency === true ||
    ["pending", "stale", "provider_unavailable", "failed"].includes(lookupStatus)
  );
}

function DetailRow({ label, value, subtle = false }) {
  if (!value) {
    return null;
  }
  return (
    <div style={rowStyle}>
      <span style={labelStyle}>{label}</span>
      <span style={subtle ? subtleValueStyle : valueStyle}>{value}</span>
    </div>
  );
}

function InternetNoiseSummary({ internetNoise, compact = false }) {
  if (!shouldShowInternetNoise(internetNoise)) {
    return null;
  }

  const overrideText = Array.isArray(internetNoise.override_reasons) && internetNoise.override_reasons.length > 0
    ? internetNoise.override_reasons[0].text
    : "";
  const showLookupStatus = ["pending", "stale", "provider_unavailable", "failed"].includes(
    String(internetNoise.lookup_status || "").toLowerCase()
  );

  return (
    <div style={panelStyle} data-testid="internet-noise-summary">
      <div style={headerStyle}>
        <strong>Internet Noise</strong>
        {internetNoise.policy_mode ? (
          <span style={modeBadgeStyle(internetNoise.policy_mode)}>
            {String(internetNoise.policy_mode).toUpperCase()}
          </span>
        ) : null}
      </div>
      <p style={assessmentStyle}>{buildAssessmentLabel(internetNoise)}</p>
      <DetailRow label="Provider" value={internetNoise.provider || "Unknown"} />
      <DetailRow label="Effect" value={buildEffectLabel(internetNoise)} />
      {overrideText ? (
        <DetailRow label="Override" value={overrideText} />
      ) : null}
      <p style={explanationStyle}>
        {internetNoise.explanation || "Internet-noise context is neutral."}
      </p>
      {showLookupStatus ? (
        <DetailRow label="Status" value={humanizeLookupStatus(internetNoise.lookup_status)} subtle />
      ) : null}
      {!compact && internetNoise.last_checked ? (
        <DetailRow label="Last checked" value={internetNoise.last_checked} subtle />
      ) : null}
    </div>
  );
}

const panelStyle = {
  display: "grid",
  gap: "8px",
};

const headerStyle = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: "10px",
};

const assessmentStyle = {
  margin: 0,
  color: "#f8fafc",
  fontWeight: 700,
};

const rowStyle = {
  display: "flex",
  justifyContent: "space-between",
  gap: "12px",
  fontSize: "12px",
};

const labelStyle = {
  color: "#94a3b8",
};

const valueStyle = {
  color: "#e5e7eb",
  fontWeight: 600,
  textAlign: "right",
};

const subtleValueStyle = {
  color: "#cbd5e1",
  textAlign: "right",
};

const explanationStyle = {
  margin: 0,
  color: "#cbd5e1",
  fontSize: "12px",
  lineHeight: 1.5,
};

const modeBadgeStyle = (mode) => ({
  padding: "2px 8px",
  borderRadius: "999px",
  fontSize: "10px",
  letterSpacing: "0.08em",
  border: mode === "policy" ? "1px solid rgba(56, 189, 248, 0.35)" : "1px solid rgba(250, 204, 21, 0.35)",
  color: mode === "policy" ? "#7dd3fc" : "#fde68a",
  backgroundColor: mode === "policy" ? "rgba(14, 116, 144, 0.18)" : "rgba(120, 53, 15, 0.18)",
});

export default InternetNoiseSummary;
