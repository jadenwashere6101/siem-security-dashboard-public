// Canned sample events for the Temporary Playground Rule builder's "Load
// sample events" action. Every payload below was verified directly against
// the real production parser/normalizer functions in
// engines/detection_simulator.py's PARSE_DISPATCH (see this change's
// implementation notes), so it is known to parse successfully. This module
// only supplies literal text for the builder's textarea -- it does not parse,
// normalize, or evaluate anything itself.

const PFSENSE_RAW_TEXT = [
  "Jan  1 00:00:00 filterlog: 1,,,1000000103,igb1,match,block,in,4,0x0,,64,0,0,DF,6,tcp,60,203.0.113.5,198.51.100.10,54321,22,0,S",
  "Jan  1 00:05:00 filterlog: 1,,,1000000103,igb1,match,block,in,4,0x0,,64,0,0,DF,6,tcp,60,203.0.113.6,198.51.100.10,54322,22,0,S",
  "Jan  1 00:06:00 filterlog: 1,,,1000000103,igb1,match,block,in,4,0x0,,64,0,0,DF,6,tcp,60,203.0.113.5,198.51.100.10,54325,22,0,S",
].join("\n");

const NGINX_RAW_TEXT = [
  '203.0.113.9 - - [10/Oct/2026:13:55:36 -0700] "GET /admin HTTP/1.1" 500 123',
  '203.0.113.10 - - [10/Oct/2026:13:56:10 -0700] "GET /wp-login.php HTTP/1.1" 401 512',
  '203.0.113.9 - - [10/Oct/2026:13:57:02 -0700] "GET /admin HTTP/1.1" 500 123',
].join("\n");

const HONEYPOT_JSON_LINES = [
  { event_type: "env_probe", source_ip: "203.0.113.11", path: "/.env", method: "GET" },
  { event_type: "env_probe", source_ip: "203.0.113.41", path: "/.git/config", method: "GET" },
  { event_type: "credential_stuffing", source_ip: "203.0.113.12", username: "admin" },
  { event_type: "credential_stuffing", source_ip: "203.0.113.42", username: "root" },
];

const BANK_APP_JSON_LINES = [
  {
    event_type: "failed_login",
    severity: "medium",
    source_ip: "198.51.100.201",
    message: "Failed login attempt for username: alice",
    app_name: "bank_app",
    environment: "test",
    username: "alice",
  },
  {
    event_type: "failed_login",
    severity: "medium",
    source_ip: "198.51.100.202",
    message: "Failed login attempt for username: bob",
    app_name: "bank_app",
    environment: "test",
    username: "bob",
  },
  {
    event_type: "failed_login",
    severity: "medium",
    source_ip: "198.51.100.201",
    message: "Failed login attempt for username: alice",
    app_name: "bank_app",
    environment: "test",
    username: "alice",
  },
];

const PFSENSE_JSON_LINES = [
  {
    event_type: "firewall_block",
    severity: "medium",
    source_ip: "203.0.113.50",
    source: "pfsense",
    source_type: "firewall",
    message: "blocked",
    app_name: "pfSense",
    environment: "test",
    raw_payload: {
      action: "block",
      interface: "igb1",
      direction: "in",
      ip_version: "4",
      protocol: "tcp",
      source_ip: "203.0.113.50",
      destination_ip: "198.51.100.50",
      source_port: 54321,
      destination_port: 443,
    },
  },
  {
    event_type: "firewall_block",
    severity: "medium",
    source_ip: "203.0.113.51",
    source: "pfsense",
    source_type: "firewall",
    message: "blocked",
    app_name: "pfSense",
    environment: "test",
    raw_payload: {
      action: "block",
      interface: "igb1",
      direction: "in",
      ip_version: "4",
      protocol: "tcp",
      source_ip: "203.0.113.51",
      destination_ip: "198.51.100.50",
      source_port: 54322,
      destination_port: 443,
    },
  },
];

const AZURE_INSIGHTS_JSON_LINES = [
  {
    baseType: "SignInLog",
    userPrincipalName: "alice@contoso.com",
    sourceIp: "203.0.113.21",
    resultType: "50126",
    timestamp: "2026-07-13T10:15:00Z",
  },
  {
    baseType: "SignInLog",
    userPrincipalName: "bob@contoso.com",
    sourceIp: "203.0.113.22",
    resultType: "50126",
    timestamp: "2026-07-13T10:16:00Z",
  },
  {
    baseType: "SignInLog",
    userPrincipalName: "alice@contoso.com",
    sourceIp: "203.0.113.21",
    resultType: "50126",
    timestamp: "2026-07-13T10:17:00Z",
  },
];

const OPENTELEMETRY_JSON_LINES = [
  { source_ip: "203.0.113.31", status_code: 500, name: "GET /checkout", app_name: "checkout-svc" },
  { source_ip: "203.0.113.32", status_code: 401, name: "GET /admin", app_name: "admin-portal" },
  { source_ip: "203.0.113.31", status_code: 500, name: "GET /checkout", app_name: "checkout-svc" },
];

const asJsonLines = (items) => items.map((item) => JSON.stringify(item)).join("\n");
const asJsonArray = (items) => JSON.stringify(items, null, 2);

// Keyed by `${source}:${input_format}` so the builder can look up sample text
// for the analyst's exact source + input-format selection.
export const PLAYGROUND_SAMPLE_TEXT_BY_SOURCE_AND_FORMAT = Object.freeze({
  "honeypot:json_lines": asJsonLines(HONEYPOT_JSON_LINES),
  "honeypot:json_array": asJsonArray(HONEYPOT_JSON_LINES),
  "bank_app:json_lines": asJsonLines(BANK_APP_JSON_LINES),
  "bank_app:json_array": asJsonArray(BANK_APP_JSON_LINES),
  "pfsense:raw_text": PFSENSE_RAW_TEXT,
  "pfsense:json_lines": asJsonLines(PFSENSE_JSON_LINES),
  "pfsense:json_array": asJsonArray(PFSENSE_JSON_LINES),
  "nginx:raw_text": NGINX_RAW_TEXT,
  "azure_insights:json_lines": asJsonLines(AZURE_INSIGHTS_JSON_LINES),
  "azure_insights:json_array": asJsonArray(AZURE_INSIGHTS_JSON_LINES),
  "opentelemetry:json_lines": asJsonLines(OPENTELEMETRY_JSON_LINES),
  "opentelemetry:json_array": asJsonArray(OPENTELEMETRY_JSON_LINES),
});

export const getPlaygroundSampleText = (source, inputFormat) =>
  PLAYGROUND_SAMPLE_TEXT_BY_SOURCE_AND_FORMAT[`${source}:${inputFormat}`] || "";
