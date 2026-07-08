import React from "react";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import LiveLogsPanel from "./LiveLogsPanel";
import { loadLiveLogs } from "../services/liveLogsService";

jest.mock("../services/liveLogsService", () => ({
  loadLiveLogs: jest.fn(),
}));

const styleProps = {
  cardStyle: {},
  cardHeaderStyle: {},
  cardTitleStyle: {},
  cardSubtitleStyle: {},
};

const eventOne = {
  id: 1,
  event_type: "firewall_block",
  severity: "medium",
  source: "pfsense",
  source_ip: "198.51.100.10",
  app_name: "pfsense_filterlog",
  message: "first event",
  raw_payload: {
    filter_action: "block",
    interface: "wan",
    protocol: "tcp",
  },
  created_at: "2026-07-07T10:00:00Z",
};

const eventTwo = {
  ...eventOne,
  id: 2,
  message: "second event",
  created_at: "2026-07-07T10:00:05Z",
};

beforeEach(() => {
  jest.clearAllMocks();
  jest.useFakeTimers();
});

afterEach(() => {
  jest.clearAllTimers();
  jest.useRealTimers();
});

test("renders loading then populated newest-first rows", async () => {
  loadLiveLogs.mockResolvedValue([eventOne, eventTwo]);

  render(<LiveLogsPanel source="pfsense" {...styleProps} />);

  expect(screen.getByText(/loading live logs/i)).toBeInTheDocument();
  expect(await screen.findByRole("button", { name: "Event Feed" })).toHaveAttribute(
    "aria-pressed",
    "true"
  );
  expect(screen.getByRole("button", { name: "Raw Log" })).toHaveAttribute("aria-pressed", "false");
  expect(screen.getByRole("button", { name: "JSON" })).toHaveAttribute("aria-pressed", "false");
  expect(await screen.findByText("second event")).toBeInTheDocument();
  expect(screen.getByText("first event")).toBeInTheDocument();

  const messages = screen.getAllByText(/event$/i).map((node) => node.textContent);
  expect(messages).toEqual(["second event", "first event"]);
  expect(loadLiveLogs).toHaveBeenCalledWith({ source: "pfsense" });
});

test("presents the view toggle in Event Feed, Raw Log, JSON order", async () => {
  loadLiveLogs.mockResolvedValue([eventOne]);

  render(<LiveLogsPanel source="pfsense" {...styleProps} />);
  await screen.findByText("first event");

  const group = screen.getByRole("group", { name: "Live log view mode" });
  const buttonNames = within(group)
    .getAllByRole("button")
    .map((button) => button.textContent);
  expect(buttonNames).toEqual(["Event Feed", "Raw Log", "JSON"]);
});

test("switches to JSON and renders raw payloads newest-first", async () => {
  loadLiveLogs.mockResolvedValue([eventOne, eventTwo]);

  render(<LiveLogsPanel source="pfsense" {...styleProps} />);

  expect(await screen.findByText("second event")).toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: "JSON" }));

  expect(screen.getByRole("button", { name: "JSON" })).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByLabelText("pfSense json view")).toBeInTheDocument();
  expect(screen.getByText(/id=2 source=pfsense/i)).toBeInTheDocument();
  expect(screen.getAllByText(/"filter_action": "block"/i)).toHaveLength(2);
  expect(screen.getAllByText(/"interface": "wan"/i)).toHaveLength(2);
});

test("JSON falls back to normalized event details when raw_payload is unavailable", async () => {
  loadLiveLogs.mockResolvedValue([{ ...eventOne, raw_payload: {}, message: "normalized only" }]);

  render(<LiveLogsPanel source="pfsense" {...styleProps} />);

  expect(await screen.findByText("normalized only")).toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: "JSON" }));

  expect(screen.getByText(/"message": "normalized only"/i)).toBeInTheDocument();
  expect(screen.getByText(/"source": "pfsense"/i)).toBeInTheDocument();
});

test("JSON uses the same source-filtered events request", async () => {
  loadLiveLogs.mockResolvedValue([
    {
      ...eventOne,
      id: 42,
      source: "azure_insights",
      source_type: "cloud",
      raw_payload: { operationName: "SignInLogs", category: "AuditLogs" },
    },
  ]);
  render(<LiveLogsPanel source="azure_insights" label="Azure" {...styleProps} />);

  expect(await screen.findByText("first event")).toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: "JSON" }));

  const jsonView = screen.getByLabelText("Azure json view");
  expect(jsonView).toBeInTheDocument();
  expect(within(jsonView).getByText(/source=azure_insights/i)).toBeInTheDocument();
  expect(within(jsonView).getByText(/"operationName": "SignInLogs"/i)).toBeInTheDocument();
  expect(loadLiveLogs).toHaveBeenCalledTimes(1);
  expect(loadLiveLogs).toHaveBeenCalledWith({ source: "azure_insights" });
});

test("JSON prefers the original pfSense filterlog line over the parsed JSON payload", async () => {
  loadLiveLogs.mockResolvedValue([
    {
      ...eventOne,
      raw_payload: {
        action: "block",
        interface: "wan",
        protocol: "tcp",
        raw_log: "rule 100 wan block tcp 203.0.113.5:443 198.51.100.10:52344",
        sanitized_summary: "rule 100 wan block tcp 203.0.113.5:443 198.51.100.1",
      },
    },
  ]);

  render(<LiveLogsPanel source="pfsense" {...styleProps} />);
  await screen.findByText("first event");

  await userEvent.click(screen.getByRole("button", { name: "JSON" }));

  const jsonView = screen.getByLabelText("pfSense json view");
  expect(
    within(jsonView).getByText(/rule 100 wan block tcp 203\.0\.113\.5:443 198\.51\.100\.10:52344/)
  ).toBeInTheDocument();
  expect(within(jsonView).queryByText(/"action": "block"/i)).not.toBeInTheDocument();
});

test("JSON prefers the original NGINX access log line over the parsed JSON payload", async () => {
  loadLiveLogs.mockResolvedValue([
    {
      ...eventOne,
      source: "nginx",
      raw_payload: {
        line: '203.0.113.9 - - [07/Jul/2026:10:00:00 +0000] "GET /admin HTTP/1.1" 403 512',
        log_format: "nginx_access",
        method: "GET",
        path: "/admin",
        status: 403,
      },
    },
  ]);

  render(<LiveLogsPanel source="nginx" label="NGINX" {...styleProps} />);
  await screen.findByText("first event");

  await userEvent.click(screen.getByRole("button", { name: "JSON" }));

  const jsonView = screen.getByLabelText("NGINX json view");
  expect(within(jsonView).getByText(/GET \/admin HTTP\/1\.1.*403/)).toBeInTheDocument();
  expect(within(jsonView).queryByText(/"log_format": "nginx_access"/i)).not.toBeInTheDocument();
});

test("Raw Log displays the literal pfSense filterlog line directly, not JSON", async () => {
  loadLiveLogs.mockResolvedValue([
    {
      ...eventOne,
      raw_payload: {
        action: "block",
        interface: "wan",
        raw_log: "rule 100 wan block tcp 203.0.113.5:443 198.51.100.10:52344",
        sanitized_summary: "rule 100 wan block tcp 203.0.113.5:443 198.51.100.1",
      },
    },
  ]);

  render(<LiveLogsPanel source="pfsense" {...styleProps} />);
  await screen.findByText("first event");

  await userEvent.click(screen.getByRole("button", { name: "Raw Log" }));

  const rawLog = screen.getByLabelText("pfSense raw log");
  expect(
    within(rawLog).getByText("rule 100 wan block tcp 203.0.113.5:443 198.51.100.10:52344")
  ).toBeInTheDocument();
  expect(within(rawLog).queryByText(/"action"/i)).not.toBeInTheDocument();
  expect(within(rawLog).queryByText(/^id=/i)).not.toBeInTheDocument();
});

test("Raw Log displays the literal NGINX access log line directly, not JSON", async () => {
  loadLiveLogs.mockResolvedValue([
    {
      ...eventOne,
      source: "nginx",
      raw_payload: {
        line: '198.51.100.8 - - [08/Jul/2026:00:01:55 +0000] "GET / HTTP/1.1" 404 512',
        log_format: "nginx_access",
        method: "GET",
        path: "/",
        status: 404,
      },
    },
  ]);

  render(<LiveLogsPanel source="nginx" label="NGINX" {...styleProps} />);
  await screen.findByText("first event");

  await userEvent.click(screen.getByRole("button", { name: "Raw Log" }));

  const rawLog = screen.getByLabelText("NGINX raw log");
  expect(
    within(rawLog).getByText('198.51.100.8 - - [08/Jul/2026:00:01:55 +0000] "GET / HTTP/1.1" 404 512')
  ).toBeInTheDocument();
  expect(within(rawLog).queryByText(/"log_format"/i)).not.toBeInTheDocument();
});

test("Raw Log renders a compact reconstructed line for Honeypot events", async () => {
  loadLiveLogs.mockResolvedValue([
    {
      ...eventOne,
      source: "honeypot",
      source_type: "honeypot",
      event_type: "env_probe",
      raw_payload: {
        event_type: "env_probe",
        source_ip: "198.235.24.129",
        timestamp: "2026-07-08T00:18:07Z",
        path: "/",
        method: "GET",
        user_agent: "Hello from Palo Alto Networks, find out more about this scanner at...",
        environment: "honeypot",
      },
    },
  ]);

  render(<LiveLogsPanel source="honeypot" label="Honeypot" {...styleProps} />);
  await screen.findByText("first event");

  await userEvent.click(screen.getByRole("button", { name: "Raw Log" }));

  const rawLog = screen.getByLabelText("Honeypot raw log");
  expect(
    within(rawLog).getByText(
      '2026-07-08T00:18:07Z 198.235.24.129 GET / User-Agent="Hello from Palo Alto Networks, find out more about this scanner at..."'
    )
  ).toBeInTheDocument();
  expect(within(rawLog).queryByText(/"event_type"/i)).not.toBeInTheDocument();
});

test("Raw Log renders a concise one-line log for Azure events", async () => {
  loadLiveLogs.mockResolvedValue([
    {
      ...eventOne,
      source: "azure_insights",
      source_type: "cloud_api",
      event_type: "successful_login",
      message: "Azure login success for alice@example.com from 203.0.113.5",
      raw_payload: {
        operationName: "SignInLogs",
        resultCode: "0",
        userPrincipalName: "alice@example.com",
        clientIp: "203.0.113.5",
        timestamp: "2026-07-08T01:00:00Z",
      },
    },
  ]);

  render(<LiveLogsPanel source="azure_insights" label="Azure" {...styleProps} />);
  await screen.findByText("Azure login success for alice@example.com from 203.0.113.5");

  await userEvent.click(screen.getByRole("button", { name: "Raw Log" }));

  const rawLog = screen.getByLabelText("Azure raw log");
  const line = within(rawLog).getByText(/SignInLogs/);
  expect(line.textContent).toContain("2026-07-08T01:00:00Z");
  expect(line.textContent).toContain("[SignInLogs]");
  expect(line.textContent).toContain("result=0");
  expect(line.textContent).toContain("user=alice@example.com");
  expect(line.textContent).toContain("source_ip=203.0.113.5");
  expect(within(rawLog).queryByText(/"operationName"/i)).not.toBeInTheDocument();
});

test("Raw Log renders a concise one-line telemetry log for OpenTelemetry events", async () => {
  loadLiveLogs.mockResolvedValue([
    {
      ...eventOne,
      source: "opentelemetry",
      source_type: "telemetry",
      event_type: "normal_activity",
      message: "Successful HTTP telemetry observed: GET /api/orders",
      raw_payload: {
        name: "GET /api/orders",
        timestamp: "2026-07-08T02:00:00Z",
        attributes: [
          { key: "service.name", value: { stringValue: "orders-api" } },
          { key: "http.status_code", value: { stringValue: "200" } },
        ],
      },
    },
  ]);

  render(<LiveLogsPanel source="opentelemetry" label="OTEL" {...styleProps} />);
  await screen.findByText("Successful HTTP telemetry observed: GET /api/orders");

  await userEvent.click(screen.getByRole("button", { name: "Raw Log" }));

  const rawLog = screen.getByLabelText("OTEL raw log");
  const line = within(rawLog).getByText(/GET \/api\/orders/);
  expect(line.textContent).toContain("2026-07-08T02:00:00Z");
  expect(line.textContent).toContain("[orders-api]");
  expect(line.textContent).toContain("status=200");
  expect(within(rawLog).queryByText(/"attributes"/i)).not.toBeInTheDocument();
});

test("Raw Log renders a concise application log line for Bank App events", async () => {
  loadLiveLogs.mockResolvedValue([
    {
      ...eventOne,
      source: "bank_app",
      source_type: "custom",
      app_name: "bank-web",
      severity: "high",
      message: "Multiple failed login attempts detected",
      source_ip: "10.0.0.42",
      created_at: "2026-07-08T03:00:00Z",
      raw_payload: {
        app_name: "bank-web",
        severity: "high",
        message: "Multiple failed login attempts detected",
        source_ip: "10.0.0.42",
      },
    },
  ]);

  render(<LiveLogsPanel source="bank_app" label="Bank App" {...styleProps} />);
  await screen.findByText("Multiple failed login attempts detected");

  await userEvent.click(screen.getByRole("button", { name: "Raw Log" }));

  const rawLog = screen.getByLabelText("Bank App raw log");
  const line = within(rawLog).getByText(/Multiple failed login attempts detected/);
  expect(line.textContent).toContain("2026-07-08T03:00:00Z");
  expect(line.textContent).toContain("[bank-web]");
  expect(line.textContent).toContain("HIGH:");
  expect(line.textContent).toContain("source_ip=10.0.0.42");
  expect(within(rawLog).queryByText(/"app_name"/i)).not.toBeInTheDocument();
});

test("renders empty state", async () => {
  loadLiveLogs.mockResolvedValue([]);

  render(<LiveLogsPanel source="honeypot" label="Honeypot" {...styleProps} />);

  expect(await screen.findByText(/no live logs found for honeypot/i)).toBeInTheDocument();
});

test("renders error state and keeps polling retry path", async () => {
  loadLiveLogs.mockRejectedValueOnce(new Error("Network failed")).mockResolvedValueOnce([eventOne]);

  render(<LiveLogsPanel source="pfsense" {...styleProps} />);

  expect(await screen.findByText("Network failed")).toBeInTheDocument();

  await act(async () => {
    jest.advanceTimersByTime(5000);
  });

  await waitFor(() => {
    expect(screen.getByText("first event")).toBeInTheDocument();
  });
});

test("polling merges new rows without duplicating existing ids", async () => {
  loadLiveLogs
    .mockResolvedValueOnce([eventOne])
    .mockResolvedValueOnce([eventOne, eventTwo]);

  render(<LiveLogsPanel source="pfsense" {...styleProps} />);

  expect(await screen.findByText("first event")).toBeInTheDocument();

  await act(async () => {
    jest.advanceTimersByTime(5000);
  });

  await waitFor(() => {
    expect(screen.getByText("second event")).toBeInTheDocument();
  });

  expect(screen.getAllByText("first event")).toHaveLength(1);
  expect(loadLiveLogs).toHaveBeenLastCalledWith({ source: "pfsense", afterId: 1 });
});

test("clears polling interval on unmount", async () => {
  loadLiveLogs.mockResolvedValue([eventOne]);
  const clearSpy = jest.spyOn(global, "clearInterval");

  const { unmount } = render(<LiveLogsPanel source="pfsense" {...styleProps} />);
  await screen.findByText("first event");

  unmount();

  expect(clearSpy).toHaveBeenCalled();
});
