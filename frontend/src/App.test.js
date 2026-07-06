import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from './App';
import { loadCurrentSession } from './services/authService';
import { loadAlerts } from './services/alertsService';

jest.mock('./services/authService', () => ({
  loadCurrentSession: jest.fn(),
  loginToDashboard: jest.fn(),
  logoutFromDashboard: jest.fn(),
}));

jest.mock('./services/alertsService', () => ({
  loadAlerts: jest.fn(),
}));

jest.mock('./components/DashboardSection', () => () => (
  <div data-testid="dashboard-section">Dashboard Section Mock</div>
));

jest.mock('./components/DeadLettersPanel', () => (props) => (
  <div data-testid="dead-letters-panel">
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
    SOC Command Center Mock {props.userRole} {props.currentUsername}
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

beforeEach(() => {
  jest.clearAllMocks();
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
