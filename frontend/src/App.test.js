import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from './App';
import { loadCurrentSession } from './services/authService';
import { loadAlerts } from './services/alertsService';
import { UI_SETTINGS_STORAGE_KEY } from './utils/uiSettings';

jest.mock('./services/authService', () => ({
  loadCurrentSession: jest.fn(),
  loginToDashboard: jest.fn(),
  logoutFromDashboard: jest.fn(),
}));

jest.mock('./services/alertsService', () => ({
  loadAlerts: jest.fn(),
}));

jest.mock('./components/DashboardSection', () => (props) => (
  <div data-testid="dashboard-section">
    <h2>Dashboard workspace</h2>
    Dashboard Section Mock search:{props.searchTerm || ''}
    <button type="button" onClick={() => props.onOpenResponseRegistry({ sourceIp: '8.8.8.8', relatedAlertId: 12 })}>
      Dashboard open registry
    </button>
    <button type="button" onClick={() => props.onReviewIncident()}>
      Dashboard open incidents
    </button>
    <div data-navigation-target="recent-alerts" tabIndex={-1}>Recent Alerts target</div>
  </div>
));

jest.mock('./components/DeadLettersPanel', () => (props) => (
  <div data-testid="dead-letters-panel">
    <h2>Dead Letter Queue</h2>
    Dead Letters Panel Mock {props.userRole}
  </div>
));

jest.mock('./components/SoarMetricsDashboard', () => (props) => (
  <div data-testid="soar-metrics-dashboard">
    SOAR Metrics Dashboard Mock {props.userRole}
  </div>
));

jest.mock('./components/SocCommandCenter', () => (props) => (
  <div data-testid="soc-command-center">
    <h2>SOC Command Center</h2>
    SOC Command Center Mock {props.userRole} {props.currentUsername}
    <button type="button" onClick={() => props.onNavigate('soar-operations')}>SOC open operations</button>
    <button type="button" onClick={() => props.onOpenAttentionItem('Pending approvals')}>SOC open approvals</button>
    <button type="button" onClick={() => props.onOpenResponseRegistry({ sourceIp: '9.9.9.9', relatedIncidentId: 7 })}>SOC open registry</button>
  </div>
));

jest.mock('./components/ResponseRegistryPanel', () => (props) => (
  <div data-testid="response-registry-panel">
    Response Registry Mock view:{props.initialView || 'all'} {props.navigationRequest?.q}{' '}
    {props.navigationRequest?.relatedIncidentId} {props.navigationRequest?.relatedAlertId}
  </div>
));

jest.mock('./components/ApprovalsPanel', () => (props) => (
  <div data-testid="approvals-panel">Approvals Mock {props.initialStatusFilter}</div>
));

jest.mock('./components/IncidentsPanel', () => (props) => (
  <div data-testid="incidents-panel">
    <h2>Incident Visibility</h2>
    Incidents Mock
    <button
      type="button"
      onClick={() => props.onViewRelatedAlerts?.('203.0.113.10')}
    >
      Incident open related alerts
    </button>
    <button
      type="button"
      onClick={() =>
        props.onOpenResponseRegistry?.({
          sourceIp: '203.0.113.10',
          relatedIncidentId: 42,
        })
      }
    >
      Incident open registry
    </button>
  </div>
));

jest.mock('./components/PlaybooksPanel', () => (props) => (
  <div data-testid="playbooks-panel">
    <h2>Playbooks</h2>
    Playbooks Mock
    <button
      type="button"
      onClick={() =>
        props.onOpenResponseRegistry?.({
          sourceIp: '198.51.100.20',
          relatedAlertId: 55,
          relatedIncidentId: 9,
        })
      }
    >
      Playbook open registry
    </button>
  </div>
));

jest.mock('./components/DetectionRulesPanel', () => () => (
  <div data-testid="detection-rules-panel">Detection Rules Panel Mock</div>
));

jest.mock('./components/AdminUsersPanel', () => () => (
  <div data-testid="admin-users-panel">Admin Users Panel Mock</div>
));

jest.mock('./components/AuditLogPanel', () => () => (
  <div data-testid="audit-log-panel">Audit Log Panel Mock</div>
));

jest.mock('./components/LiveLogsPanel', () => (props) => (
  <div data-testid="live-logs-panel">
    Live Logs Panel Mock {props.label} {props.source}
  </div>
));

jest.mock('./components/SourceHealthPanel', () => (props) => (
  <div data-testid="source-health-panel">
    <h2>Source Health</h2>
    <button type="button" onClick={() => props.onOpenLiveLogs('live-logs-pfsense')}>
      Source Health open pfSense logs
    </button>
  </div>
));

beforeEach(() => {
  jest.clearAllMocks();
  window.localStorage.clear();
  loadCurrentSession.mockResolvedValue({ authenticated: false });
  loadAlerts.mockResolvedValue([]);
});

test('renders without crashing', async () => {
  render(<App />);
  expect(screen.getByText(/checking authentication/i)).toBeInTheDocument();
  expect(await screen.findByRole('heading', { name: /siem dashboard login/i })).toBeInTheDocument();
});

test('renders the login form for unauthenticated users', async () => {
  const { container } = render(<App />);

  expect(await screen.findByRole('heading', { name: /siem dashboard login/i })).toBeInTheDocument();
  expect(screen.getByText(/username/i)).toBeInTheDocument();
  expect(container.querySelector('input[type="text"]')).toBeInTheDocument();
  expect(screen.getByText(/password/i)).toBeInTheDocument();
  expect(container.querySelector('input[type="password"]')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /log in/i })).toBeInTheDocument();
});

test('renders SOAR Operations nav for analyst and loads panel when selected', async () => {
  loadCurrentSession.mockResolvedValue({
    authenticated: true,
    user: 'analyst1',
    role: 'analyst',
  });

  render(<App />);

  expect(await screen.findByRole('button', { name: /soar operations/i })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /^dashboard$/i })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /soc command center/i })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /soar incidents/i })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /soar playbooks/i })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /soar approvals/i })).toBeInTheDocument();

  await userEvent.click(screen.getByRole('button', { name: /soar operations/i }));

  expect(await screen.findByTestId('dead-letters-panel')).toHaveTextContent(/analyst/i);
});

test('renders Source Health beneath Dashboard and routes its Live Logs action', async () => {
  loadCurrentSession.mockResolvedValue({ authenticated: true, user: 'analyst1', role: 'analyst' });
  render(<App />);
  const dashboard = await screen.findByRole('button', { name: /^dashboard$/i });
  const sourceHealth = screen.getByRole('button', { name: /^source health$/i });
  expect(dashboard.compareDocumentPosition(sourceHealth) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  await userEvent.click(sourceHealth);
  expect(await screen.findByTestId('source-health-panel')).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: /source health open pfsense logs/i }));
  expect(await screen.findByTestId('live-logs-panel')).toHaveTextContent('pfSense pfsense');
});

test('renders SOC Command Center nav for analyst and loads command center when selected', async () => {
  loadCurrentSession.mockResolvedValue({
    authenticated: true,
    user: 'analyst1',
    role: 'analyst',
  });

  render(<App />);

  expect(await screen.findByRole('button', { name: /soc command center/i })).toBeInTheDocument();

  await userEvent.click(screen.getByRole('button', { name: /soc command center/i }));

  expect(await screen.findByTestId('soc-command-center')).toHaveTextContent(/analyst analyst1/i);
});

test('ordinary sidebar and SOC navigation reset the shared main scroll container', async () => {
  loadCurrentSession.mockResolvedValue({ authenticated: true, user: 'analyst1', role: 'analyst' });
  render(<App />);
  const operationsButton = await screen.findByRole('button', { name: /soar operations/i });
  const main = screen.getByRole('main');
  main.scrollTo = jest.fn();

  await userEvent.click(operationsButton);
  expect(main.scrollTo).toHaveBeenLastCalledWith({ top: 0, left: 0, behavior: 'smooth' });
  expect(screen.getByRole('heading', { name: 'Dead Letter Queue' })).toHaveFocus();

  await userEvent.click(screen.getByRole('button', { name: /soc command center/i }));
  expect(screen.getByRole('heading', { name: 'SOC Command Center' })).toHaveFocus();
  main.scrollTo.mockClear();
  await userEvent.click(await screen.findByRole('button', { name: 'SOC open operations' }));
  expect(main.scrollTo).toHaveBeenLastCalledWith({ top: 0, left: 0, behavior: 'smooth' });
  expect(screen.getByRole('heading', { name: 'Dead Letter Queue' })).toHaveFocus();
});

test('SOC attention and Open in Response Registry preserve deep navigation context', async () => {
  loadCurrentSession.mockResolvedValue({ authenticated: true, user: 'analyst1', role: 'analyst' });
  render(<App />);
  await userEvent.click(await screen.findByRole('button', { name: /soc command center/i }));
  const main = screen.getByRole('main');
  main.scrollTo = jest.fn();

  await userEvent.click(screen.getByRole('button', { name: 'SOC open approvals' }));
  expect(await screen.findByTestId('approvals-panel')).toHaveTextContent('pending');
  expect(screen.getByLabelText('SOAR Approvals workspace')).toHaveFocus();

  await userEvent.click(screen.getByRole('button', { name: /soc command center/i }));
  await userEvent.click(await screen.findByRole('button', { name: 'SOC open registry' }));
  expect(await screen.findByTestId('response-registry-panel')).toHaveTextContent('9.9.9.9 7');
  expect(screen.getByLabelText('Response Registry workspace')).toHaveFocus();
});

test('incident and playbook Open in Response Registry preserve correlation identifiers', async () => {
  loadCurrentSession.mockResolvedValue({ authenticated: true, user: 'analyst1', role: 'analyst' });
  render(<App />);

  await userEvent.click(await screen.findByRole('button', { name: /soar incidents/i }));
  await userEvent.click(await screen.findByRole('button', { name: 'Incident open registry' }));
  expect(await screen.findByTestId('response-registry-panel')).toHaveTextContent('203.0.113.10 42');

  await userEvent.click(screen.getByRole('button', { name: /soar playbooks/i }));
  await userEvent.click(await screen.findByRole('button', { name: 'Playbook open registry' }));
  expect(await screen.findByTestId('response-registry-panel')).toHaveTextContent(
    '198.51.100.20 9 55'
  );
});

test('related-alert deep links preserve source-IP filter and Recent Alerts destination', async () => {
  loadCurrentSession.mockResolvedValue({ authenticated: true, user: 'analyst1', role: 'analyst' });
  const originalGetBoundingClientRect = HTMLElement.prototype.getBoundingClientRect;
  HTMLElement.prototype.getBoundingClientRect = function getBoundingClientRect() {
    if (this.getAttribute?.('data-navigation-target') === 'recent-alerts') return { top: 390 };
    if (this.tagName === 'MAIN') return { top: 70 };
    return originalGetBoundingClientRect.call(this);
  };
  render(<App />);
  await userEvent.click(await screen.findByRole('button', { name: /soar incidents/i }));
  const main = screen.getByRole('main');
  main.scrollTo = jest.fn();

  await userEvent.click(await screen.findByRole('button', { name: 'Incident open related alerts' }));
  expect(await screen.findByTestId('dashboard-section')).toHaveTextContent('search:203.0.113.10');
  expect(screen.getByText('Recent Alerts target')).toHaveFocus();
  expect(main.scrollTo).toHaveBeenCalledWith({ top: 320, left: 0, behavior: 'smooth' });

  HTMLElement.prototype.getBoundingClientRect = originalGetBoundingClientRect;
});

test('dashboard deep links preserve registry and incident destinations', async () => {
  loadCurrentSession.mockResolvedValue({ authenticated: true, user: 'analyst1', role: 'analyst' });
  render(<App />);
  await screen.findByTestId('dashboard-section');

  await userEvent.click(screen.getByRole('button', { name: 'Dashboard open registry' }));
  expect(await screen.findByTestId('response-registry-panel')).toHaveTextContent('8.8.8.8');

  await userEvent.click(screen.getByRole('button', { name: /^dashboard$/i }));
  await userEvent.click(await screen.findByRole('button', { name: 'Dashboard open incidents' }));
  expect(await screen.findByRole('button', { name: /soar incidents/i })).toHaveAttribute('aria-current', 'page');
  expect(screen.getByRole('heading', { name: 'Incident Visibility' })).toHaveFocus();
});

test('renders SOAR Metrics nav for analyst and loads dashboard when selected', async () => {
  loadCurrentSession.mockResolvedValue({
    authenticated: true,
    user: 'analyst1',
    role: 'analyst',
  });

  render(<App />);

  expect(await screen.findByRole('button', { name: /soar metrics/i })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /soar operations/i })).toBeInTheDocument();

  await userEvent.click(screen.getByRole('button', { name: /soar metrics/i }));

  expect(await screen.findByTestId('soar-metrics-dashboard')).toHaveTextContent(/analyst/i);
});

test('renders SOAR Metrics nav for super_admin and passes role', async () => {
  loadCurrentSession.mockResolvedValue({
    authenticated: true,
    user: 'admin1',
    role: 'super_admin',
  });

  render(<App />);

  expect(await screen.findByRole('button', { name: /soar metrics/i })).toBeInTheDocument();

  await userEvent.click(screen.getByRole('button', { name: /soar metrics/i }));

  expect(await screen.findByTestId('soar-metrics-dashboard')).toHaveTextContent(/super_admin/i);
});

test('renders split administration nav for super_admin and each item loads only its panel', async () => {
  loadCurrentSession.mockResolvedValue({
    authenticated: true,
    user: 'admin1',
    role: 'super_admin',
  });

  render(<App />);

  expect(await screen.findByRole('button', { name: /detection rules/i })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /user management/i })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /audit logs/i })).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /^administration$/i })).not.toBeInTheDocument();

  await userEvent.click(screen.getByRole('button', { name: /detection rules/i }));
  expect(await screen.findByTestId('detection-rules-panel')).toBeInTheDocument();
  expect(screen.queryByTestId('admin-users-panel')).not.toBeInTheDocument();
  expect(screen.queryByTestId('audit-log-panel')).not.toBeInTheDocument();

  await userEvent.click(screen.getByRole('button', { name: /user management/i }));
  expect(await screen.findByTestId('admin-users-panel')).toBeInTheDocument();
  expect(screen.queryByTestId('detection-rules-panel')).not.toBeInTheDocument();
  expect(screen.queryByTestId('audit-log-panel')).not.toBeInTheDocument();

  await userEvent.click(screen.getByRole('button', { name: /audit logs/i }));
  expect(await screen.findByTestId('audit-log-panel')).toBeInTheDocument();
  expect(screen.queryByTestId('detection-rules-panel')).not.toBeInTheDocument();
  expect(screen.queryByTestId('admin-users-panel')).not.toBeInTheDocument();
});

test('does not render split administration nav for analyst', async () => {
  loadCurrentSession.mockResolvedValue({
    authenticated: true,
    user: 'analyst1',
    role: 'analyst',
  });

  render(<App />);

  expect(await screen.findByRole('button', { name: /^dashboard$/i })).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /detection rules/i })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /user management/i })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /audit logs/i })).not.toBeInTheDocument();
});

test('does not render SOAR Operations nav for viewer', async () => {
  loadCurrentSession.mockResolvedValue({
    authenticated: true,
    user: 'viewer1',
    role: 'viewer',
  });

  render(<App />);

  expect(await screen.findByRole('button', { name: /^dashboard$/i })).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /soc command center/i })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /detection rules/i })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /user management/i })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /audit logs/i })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /soar operations/i })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /soar metrics/i })).not.toBeInTheDocument();
  expect(screen.queryByTestId('dead-letters-panel')).not.toBeInTheDocument();
  expect(screen.queryByTestId('soar-metrics-dashboard')).not.toBeInTheDocument();
  expect(screen.queryByTestId('soc-command-center')).not.toBeInTheDocument();
});

test.each([
  [/honeypot/i, "Honeypot", "honeypot"],
  [/bank app/i, "Bank App", "bank_app"],
  [/pfsense/i, "pfSense", "pfsense"],
  [/nginx/i, "NGINX", "nginx"],
  [/azure/i, "Azure", "azure_insights"],
  [/otel/i, "OTEL", "opentelemetry"],
])('renders Live Logs nav item %s and passes source to panel', async (buttonName, label, source) => {
  loadCurrentSession.mockResolvedValue({
    authenticated: true,
    user: 'analyst1',
    role: 'analyst',
  });

  render(<App />);

  await userEvent.click(await screen.findByRole('button', { name: buttonName }));

  expect(await screen.findByTestId('live-logs-panel')).toHaveTextContent(
    `Live Logs Panel Mock ${label} ${source}`
  );
});

test('does not render Live Logs nav for viewer', async () => {
  loadCurrentSession.mockResolvedValue({
    authenticated: true,
    user: 'viewer1',
    role: 'viewer',
  });

  render(<App />);

  expect(await screen.findByRole('button', { name: /^dashboard$/i })).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /pfsense/i })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /honeypot/i })).not.toBeInTheDocument();
});

test('renders Settings nav for viewer and opens preference controls', async () => {
  loadCurrentSession.mockResolvedValue({
    authenticated: true,
    user: 'viewer1',
    role: 'viewer',
  });

  render(<App />);

  const settingsButton = await screen.findByRole('button', { name: /settings/i });
  expect(settingsButton).toBeInTheDocument();

  await userEvent.click(settingsButton);

  expect(await screen.findByRole('heading', { name: /^settings$/i })).toBeInTheDocument();
  expect(screen.getByLabelText(/default landing page/i)).toBeInTheDocument();
  expect(screen.getByLabelText(/global auto-refresh interval/i)).toBeInTheDocument();
  expect(screen.getByText(/^alert sound$/i)).toBeInTheDocument();
  expect(screen.getByText(/^browser notifications$/i)).toBeInTheDocument();
});

test('uses stored landing page when visible for the current role', async () => {
  loadCurrentSession.mockResolvedValue({
    authenticated: true,
    user: 'analyst1',
    role: 'analyst',
  });
  window.localStorage.setItem(
    UI_SETTINGS_STORAGE_KEY,
    JSON.stringify({
      version: 1,
      settings: {
        defaultLandingPage: 'threat-hunt',
        autoRefreshIntervalMs: 5000,
      },
    })
  );

  render(<App />);

  const threatHuntButton = await screen.findByRole('button', { name: /threat hunt/i });
  await waitFor(() => {
    expect(threatHuntButton).toHaveAttribute('aria-current', 'page');
  });
});

test('falls back to dashboard when stored landing page is hidden for role', async () => {
  loadCurrentSession.mockResolvedValue({
    authenticated: true,
    user: 'viewer1',
    role: 'viewer',
  });
  window.localStorage.setItem(
    UI_SETTINGS_STORAGE_KEY,
    JSON.stringify({
      version: 1,
      settings: {
        defaultLandingPage: 'threat-hunt',
        autoRefreshIntervalMs: 5000,
      },
    })
  );

  render(<App />);

  expect(await screen.findByRole('button', { name: /^dashboard$/i })).toHaveAttribute(
    'aria-current',
    'page'
  );
});

test('does not show a standalone Blocklist sidebar destination', async () => {
  loadCurrentSession.mockResolvedValue({
    authenticated: true,
    user: 'analyst1',
    role: 'analyst',
  });

  render(<App />);

  expect(await screen.findByRole('button', { name: /response registry/i })).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /^blocklist$/i })).not.toBeInTheDocument();
});

test('legacy blocklist landing preference opens Response Registry Blocklist Tracking', async () => {
  loadCurrentSession.mockResolvedValue({
    authenticated: true,
    user: 'analyst1',
    role: 'analyst',
  });
  window.localStorage.setItem(
    UI_SETTINGS_STORAGE_KEY,
    JSON.stringify({
      version: 1,
      settings: {
        defaultLandingPage: 'blocklist',
        autoRefreshIntervalMs: 5000,
      },
    })
  );

  render(<App />);

  await waitFor(async () => {
    expect(screen.getByRole('button', { name: /response registry/i })).toHaveAttribute(
      'aria-current',
      'page'
    );
  });
  expect(await screen.findByTestId('response-registry-panel')).toHaveTextContent(
    'view:blocklist_tracking'
  );
});

test('auto-refresh off disables interval polling while keeping initial load', async () => {
  jest.useFakeTimers();
  loadCurrentSession.mockResolvedValue({
    authenticated: true,
    user: 'analyst1',
    role: 'analyst',
  });
  window.localStorage.setItem(
    UI_SETTINGS_STORAGE_KEY,
    JSON.stringify({
      version: 1,
      settings: {
        defaultLandingPage: 'dashboard',
        autoRefreshIntervalMs: 0,
      },
    })
  );

  render(<App />);
  await screen.findByRole('button', { name: /^dashboard$/i });

  const callsAfterInitialLoad = loadAlerts.mock.calls.length;
  jest.advanceTimersByTime(30000);

  expect(loadAlerts.mock.calls.length).toBe(callsAfterInitialLoad);
  jest.useRealTimers();
});
