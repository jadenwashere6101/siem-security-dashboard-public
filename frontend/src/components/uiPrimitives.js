import React from "react";

import { theme, toneForSeverity, toneForStatus, toneStyles } from "../theme";

const merge = (...styles) => Object.assign({}, ...styles.filter(Boolean));

export function Card({ children, style, tone = "neutral", ...props }) {
  const toneStyle = toneStyles[tone] || toneStyles.neutral;
  return (
    <section
      style={merge(cardStyle, tone !== "neutral" ? { borderColor: toneStyle.borderColor } : null, style)}
      {...props}
    >
      {children}
    </section>
  );
}

export function Panel({ children, style, ...props }) {
  return (
    <div style={merge(panelStyle, style)} {...props}>
      {children}
    </div>
  );
}

export function SectionHeader({ eyebrow, title, subtitle, actions = null, id }) {
  return (
    <div style={sectionHeaderStyle}>
      <div style={{ minWidth: 0 }}>
        {eyebrow ? <p style={eyebrowStyle}>{eyebrow}</p> : null}
        {title ? <h2 id={id} style={sectionTitleStyle}>{title}</h2> : null}
        {subtitle ? <p style={sectionSubtitleStyle}>{subtitle}</p> : null}
      </div>
      {actions ? <div style={sectionActionsStyle}>{actions}</div> : null}
    </div>
  );
}

export function Button({ children, variant = "secondary", disabled = false, style, ...props }) {
  const variantStyle = variant === "primary" ? primaryButtonStyle : secondaryButtonStyle;
  return (
    <button
      type="button"
      disabled={disabled}
      style={merge(buttonBaseStyle, variantStyle, disabled ? disabledButtonStyle : null, style)}
      {...props}
    >
      {children}
    </button>
  );
}

export function IconButton({ children, label, title, style, ...props }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={title || label}
      style={merge(iconButtonStyle, style)}
      {...props}
    >
      {children}
    </button>
  );
}

export function Chip({ children, tone = "neutral", style, ...props }) {
  const toneStyle = toneStyles[tone] || toneStyles.neutral;
  return (
    <span style={merge(chipStyle, toneStyle, style)} {...props}>
      {children}
    </span>
  );
}

export const Badge = Chip;

export function StatusPill({ status, children, ...props }) {
  return (
    <Chip tone={toneForStatus(status)} {...props}>
      {children || String(status || "unknown").replaceAll("_", " ")}
    </Chip>
  );
}

export function SeverityPill({ severity, children, ...props }) {
  return (
    <Chip tone={toneForSeverity(severity)} {...props}>
      {children || String(severity || "unknown")}
    </Chip>
  );
}

export function MetricCard({
  label,
  value,
  tone = "neutral",
  summary,
  why,
  trend,
  freshness,
  confidence,
}) {
  return (
    <Card tone={tone} style={metricCardStyle}>
      <div style={metricHeaderStyle}>
        <p style={metricLabelStyle}>{label}</p>
        {tone !== "neutral" ? <span aria-hidden="true" style={metricAccentStyle(tone)} /> : null}
      </div>
      <h3 style={metricValueStyle}>{value}</h3>
      {summary ? <CompactSummary>{summary}</CompactSummary> : null}
      <div style={indicatorRowStyle}>
        {trend ? <TrendIndicator {...trend} /> : null}
        {freshness ? <FreshnessIndicator {...freshness} /> : null}
        {confidence ? <ConfidenceIndicator {...confidence} /> : null}
      </div>
      {why ? <WhyThisMatters>{why}</WhyThisMatters> : null}
    </Card>
  );
}

export function TrendIndicator({ label, direction = "neutral" }) {
  const symbol = trendSymbol(direction);
  return <Chip tone="neutral" aria-label={`Trend ${label}`}>{symbol} {label}</Chip>;
}

function trendSymbol(direction) {
  if (direction === "up") return "↑";
  if (direction === "down") return "↓";
  return "→";
}

export function FreshnessIndicator({ label }) {
  return <Chip tone="info" aria-label={`Freshness ${label}`}>{label}</Chip>;
}

export function ConfidenceIndicator({ label, tone = "neutral" }) {
  return <Chip tone={tone} aria-label={`Confidence ${label}`}>{label}</Chip>;
}

export function CompactSummary({ children }) {
  return <p style={compactSummaryStyle}>{children}</p>;
}

export function WhyThisMatters({ children }) {
  return (
    <p style={whyStyle}>
      <strong>Why this matters:</strong> {children}
    </p>
  );
}

const cardStyle = {
  backgroundColor: theme.color.bgRaised,
  borderWidth: "1px",
  borderStyle: "solid",
  borderColor: theme.color.border,
  borderRadius: theme.radius.lg,
  overflow: "hidden",
  color: theme.color.text,
};

const panelStyle = {
  ...cardStyle,
  padding: theme.spacing.lg,
};

const sectionHeaderStyle = {
  display: "flex",
  alignItems: "flex-end",
  justifyContent: "space-between",
  gap: theme.spacing.lg,
  padding: `${theme.spacing.xl}px ${theme.spacing.xl}px ${theme.spacing.lg}px`,
  borderBottom: `1px solid ${theme.color.border}`,
  flexWrap: "wrap",
};

const eyebrowStyle = {
  margin: "0 0 6px",
  color: theme.color.textMuted,
  ...theme.typography.label,
};

const sectionTitleStyle = {
  margin: 0,
  color: theme.color.text,
  fontSize: "20px",
  lineHeight: 1.2,
};

const sectionSubtitleStyle = {
  margin: "6px 0 0",
  color: theme.color.textMuted,
  fontSize: "13px",
};

const sectionActionsStyle = {
  display: "flex",
  gap: theme.spacing.sm,
  flexWrap: "wrap",
};

const buttonBaseStyle = {
  borderRadius: theme.radius.sm,
  borderWidth: "1px",
  borderStyle: "solid",
  borderColor: theme.color.border,
  padding: "8px 11px",
  fontSize: "12px",
  fontWeight: 800,
  cursor: "pointer",
};

const primaryButtonStyle = {
  backgroundColor: theme.color.ai,
  borderColor: "rgba(125, 211, 252, 0.45)",
  color: "#ecfeff",
};

const secondaryButtonStyle = {
  backgroundColor: theme.color.bgRaised,
  color: theme.color.text,
};

const disabledButtonStyle = {
  color: "#6e7681",
  cursor: "not-allowed",
  opacity: 0.6,
};

const iconButtonStyle = {
  ...buttonBaseStyle,
  width: 38,
  height: 38,
  padding: 0,
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  backgroundColor: theme.color.bgRaised,
  color: theme.color.text,
};

const chipStyle = {
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  gap: 4,
  padding: "4px 8px",
  border: "1px solid",
  borderRadius: theme.radius.pill,
  fontSize: "11px",
  fontWeight: 800,
  lineHeight: 1,
  textTransform: "uppercase",
};

const metricCardStyle = {
  padding: theme.spacing.lg,
  minHeight: 124,
};

const metricHeaderStyle = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: theme.spacing.sm,
};

const metricLabelStyle = {
  margin: 0,
  color: theme.color.textMuted,
  fontSize: "14px",
};

const metricValueStyle = {
  margin: "10px 0 0",
  color: theme.color.text,
  fontSize: "30px",
  lineHeight: 1.05,
};

const metricAccentStyle = (tone) => ({
  width: 8,
  height: 28,
  borderRadius: theme.radius.pill,
  backgroundColor: (toneStyles[tone] || toneStyles.neutral).borderColor,
});

const compactSummaryStyle = {
  margin: "8px 0 0",
  color: theme.color.textMuted,
  fontSize: "12px",
  lineHeight: 1.35,
};

const indicatorRowStyle = {
  display: "flex",
  flexWrap: "wrap",
  gap: theme.spacing.xs,
  marginTop: theme.spacing.sm,
};

const whyStyle = {
  margin: "10px 0 0",
  color: theme.color.textSoft,
  fontSize: "12px",
  lineHeight: 1.35,
};
