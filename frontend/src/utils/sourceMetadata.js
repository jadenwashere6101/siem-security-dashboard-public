export const SOURCE_METADATA = Object.freeze([
  Object.freeze({ source: "honeypot", sourceType: "honeypot", displayLabel: "Honeypot", liveLogsLabel: "Honeypot", liveLogsDestination: "live-logs-honeypot" }),
  Object.freeze({ source: "bank_app", sourceType: "custom", displayLabel: "Bank App", liveLogsLabel: "Bank App", liveLogsDestination: "live-logs-bank-app" }),
  Object.freeze({ source: "pfsense", sourceType: "firewall", displayLabel: "pfSense", liveLogsLabel: "pfSense", liveLogsDestination: "live-logs-pfsense" }),
  Object.freeze({ source: "nginx", sourceType: "web_log", displayLabel: "NGINX", liveLogsLabel: "NGINX", liveLogsDestination: "live-logs-nginx" }),
  Object.freeze({ source: "azure_insights", sourceType: "cloud_api", displayLabel: "Azure Application Insights", liveLogsLabel: "Azure", liveLogsDestination: "live-logs-azure" }),
  Object.freeze({ source: "opentelemetry", sourceType: "telemetry", displayLabel: "OpenTelemetry", liveLogsLabel: "OTEL", liveLogsDestination: "live-logs-otel" }),
]);

export const SOURCE_METADATA_BY_ID = Object.freeze(
  Object.fromEntries(SOURCE_METADATA.map((item) => [item.source, item]))
);

export const SOURCE_DISPLAY_LABELS = Object.freeze(
  Object.fromEntries(SOURCE_METADATA.map((item) => [item.source, item.displayLabel]))
);

export const LIVE_LOG_SOURCE_LABELS = Object.freeze(
  Object.fromEntries(SOURCE_METADATA.map((item) => [item.source, item.liveLogsLabel]))
);

export const LIVE_LOG_SECTIONS = Object.freeze(
  SOURCE_METADATA.map((item) => Object.freeze({
    id: item.liveLogsDestination,
    label: item.liveLogsLabel,
    group: "live logs",
    source: item.source,
    visibleWhen: ({ canTakeAlertActions }) => canTakeAlertActions,
  }))
);

