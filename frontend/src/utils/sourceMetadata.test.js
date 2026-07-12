import { LIVE_LOG_SECTIONS, SOURCE_METADATA } from "./sourceMetadata";

test("frontend canonical source metadata matches the backend contract", () => {
  expect(SOURCE_METADATA.map(({ source, sourceType, displayLabel, liveLogsDestination }) => ({
    source,
    sourceType,
    displayLabel,
    liveLogsDestination,
  }))).toEqual([
    { source: "honeypot", sourceType: "honeypot", displayLabel: "Honeypot", liveLogsDestination: "live-logs-honeypot" },
    { source: "bank_app", sourceType: "custom", displayLabel: "Bank App", liveLogsDestination: "live-logs-bank-app" },
    { source: "pfsense", sourceType: "firewall", displayLabel: "pfSense", liveLogsDestination: "live-logs-pfsense" },
    { source: "nginx", sourceType: "web_log", displayLabel: "NGINX", liveLogsDestination: "live-logs-nginx" },
    { source: "azure_insights", sourceType: "cloud_api", displayLabel: "Azure Application Insights", liveLogsDestination: "live-logs-azure" },
    { source: "opentelemetry", sourceType: "telemetry", displayLabel: "OpenTelemetry", liveLogsDestination: "live-logs-otel" },
  ]);
  expect(LIVE_LOG_SECTIONS.map((item) => item.source)).toEqual(
    SOURCE_METADATA.map((item) => item.source)
  );
});

