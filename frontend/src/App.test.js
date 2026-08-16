import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from './App';
import { loadCurrentSession } from './services/authService';
import { loadAlertDashboardSummary, loadAlertRuleOptions, loadAlerts } from './services/alertsService';
import { createAiThread, getAiThread, getAiThreadTurns, getAiWorkflowRequest, queueAiWorkflowRequest, requestAiExplanation, requestAiWorkflow, resetAiThread } from './services/aiService';
import {
  createEvidenceReference,
  createInvestigation,
  createWorkspaceHypothesis,
  createWorkspaceNote,
  createWorkspaceTask,
  deleteEvidenceReference,
  deleteHypothesisEvidenceLink,
  deleteInvestigation,
  deleteWorkspaceHypothesis,
  deleteWorkspaceNote,
  deleteWorkspaceTask,
  linkHypothesisEvidence,
  loadAnalystWorkspace,
  loadInvestigationWorkspace,
  pinWorkspaceItem,
  removeWorkspacePin,
  updateEvidenceReference,
  updateInvestigation,
  updateWorkspaceTask,
} from './services/investigationWorkspaceService';
import { UI_SETTINGS_STORAGE_KEY } from './utils/uiSettings';

jest.mock('./services/authService', () => ({
  loadCurrentSession: jest.fn(),
  loginToDashboard: jest.fn(),
  logoutFromDashboard: jest.fn(),
}));

jest.mock('./services/alertsService', () => ({
  loadAlerts: jest.fn(),
  loadAlertDashboardSummary: jest.fn(),
  loadAlertRuleOptions: jest.fn(),
}));

jest.mock('./services/aiService', () => ({
  createAiThread: jest.fn(() => Promise.resolve({ thread: { thread_id: 'ath_test', version: 1 } })),
  getAiThread: jest.fn(() => Promise.resolve({
    thread: {
      thread_id: 'ath_test',
      version: 1,
      primary_entity: { type: 'dashboard', id: 'dashboard' },
      focus_state: {},
      state: { unresolved_questions: [], corrections: [] },
    },
    active_request: null,
  })),
  getAiThreadTurns: jest.fn(() => Promise.resolve({ turns: [], next_cursor: null, has_more: false })),
  getAiWorkflowRequest: jest.fn(() => Promise.resolve({ status: 'completed', workflow: 'deep_investigate', result: { status: 'success', answer: 'done', metadata: {}, context: {} }, metadata: {}, context: {} })),
  queueAiWorkflowRequest: jest.fn(() => Promise.resolve({ status: 'queued', workflow: 'deep_investigate', request_id: 'aiwf_test', metadata: {}, lifecycle: { stages: [{ stage: 'queued', status: 'running' }] } })),
  requestAiChat: jest.fn(() => Promise.resolve({ status: 'success', answer: 'ok', metadata: {}, context: {} })),
  requestAiDraft: jest.fn(() => Promise.resolve({ status: 'success', draft: {}, metadata: {}, context: {} })),
  requestAiExplanation: jest.fn(() => Promise.resolve({ status: 'success', answer: 'ok', metadata: {}, context: {} })),
  requestAiInvestigation: jest.fn(() => Promise.resolve({ status: 'success', investigation: {}, metadata: {}, context: {} })),
  requestAiWorkflow: jest.fn(() => Promise.resolve({ status: 'success', workflow: 'quick_explain', result: { status: 'success', answer: 'ok', metadata: {}, context: {} }, metadata: {}, context: {} })),
  resetAiThread: jest.fn(),
}));

jest.mock('./services/investigationWorkspaceService', () => ({
  createEvidenceReference: jest.fn(),
  createInvestigation: jest.fn(),
  createWorkspaceHypothesis: jest.fn(),
  createWorkspaceNote: jest.fn(),
  createWorkspaceTask: jest.fn(),
  deleteEvidenceReference: jest.fn(),
  deleteHypothesisEvidenceLink: jest.fn(),
  deleteInvestigation: jest.fn(),
  deleteWorkspaceHypothesis: jest.fn(),
  deleteWorkspaceNote: jest.fn(),
  deleteWorkspaceTask: jest.fn(),
  linkHypothesisEvidence: jest.fn(),
  loadAnalystWorkspace: jest.fn(),
  loadInvestigationWorkspace: jest.fn(),
  pinWorkspaceItem: jest.fn(),
  removeWorkspacePin: jest.fn(),
  updateEvidenceReference: jest.fn(),
  updateInvestigation: jest.fn(),
  updateWorkspaceTask: jest.fn(),
}));

jest.mock('./components/NistEvidenceWorkspace', () => (props) => (
  <div data-testid="nist-evidence-workspace" data-role={props.userRole}>
    NIST Evidence Workspace Mock
  </div>
));

jest.mock('./components/DashboardSection', () => (props) => (
  <div data-testid="dashboard-section" data-anakin-open={props.anakinOpen ? 'true' : 'false'}>
    <h2>Dashboard workspace</h2>
    Dashboard Section Mock search:{props.searchTerm || ''}
    <div>severity:{props.severityFilter || ''}</div>
    <div>status:{props.statusFilter || ''}</div>
    <div>source:{props.sourceFilter || ''}</div>
    <div>rule:{props.ruleFilter || ''}</div>
    <div>scope:{props.operationalScope}</div>
    <div>loading:{String(Boolean(props.loading))}</div>
    <div>refreshing:{String(Boolean(props.refreshing))}</div>
    <div>error:{props.error || ''}</div>
    <button type="button" onClick={() => props.setOperationalScope('all_history')}>
      Dashboard show all history
    </button>
    <button type="button" onClick={() => props.setSeverityFilter('high')}>
      Dashboard set severity
    </button>
    <button type="button" onClick={() => props.setStatusFilter('resolved')}>
      Dashboard set status
    </button>
    <button type="button" onClick={() => props.setSourceFilter('pfsense')}>
      Dashboard set source
    </button>
    <button type="button" onClick={() => props.setRuleFilter('failed_login_threshold')}>
      Dashboard set rule
    </button>
    <button type="button" onClick={() => props.setSearchTerm('manual search')}>
      Dashboard set search
    </button>
    <button type="button" onClick={() => props.onOpenResponseRegistry({ sourceIp: '8.8.8.8', relatedAlertId: 12 })}>
      Dashboard open registry
    </button>
    <button
      type="button"
      onClick={() =>
        props.onOpenInvestigation({
          id: 101,
          alert_type: 'failed_login_threshold',
          severity: 'high',
          source_ip: '8.8.8.8',
          status: 'open',
        })
      }
    >
      Dashboard open investigation
    </button>
    <button type="button" onClick={() => props.onReviewIncident()}>
      Dashboard open incidents
    </button>
    <button type="button" onClick={() => props.onAlertDetailsOpenChange?.(true)}>
      Dashboard open alert details mock
    </button>
    <button
      type="button"
      onClick={() => props.onAskAi?.({
        workflow: 'quick_explain',
        contextType: 'alert',
        context: { alert_id: 7, source_ip: '203.0.113.7' },
        question: 'Explain alert 7.',
        title: 'Explain alert 7',
      })}
    >
      Explain alert 7 mock
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
    <button
      type="button"
      onClick={() =>
        props.onAskAi({
          contextType: 'recon_activity',
          action: 'explain_recon_activity',
          title: 'Recon activity #90',
          question: 'Explain this recon activity.',
          context: { activity_id: 90 },
        })
      }
    >
      SOC explain recon
    </button>
  </div>
));

jest.mock('./components/ResponseRegistryPanel', () => (props) => (
  <div data-testid="response-registry-panel">
    Response Registry Mock view:{props.initialView || 'all'} {props.navigationRequest?.q}{' '}
    {props.navigationRequest?.exactIndicator}{' '}
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

jest.mock('./components/AiGatewayConfigPanel', () => () => (
  <div data-testid="ai-gateway-config-panel">AI Gateway Config Panel Mock</div>
));

jest.mock('./components/AdminUsersPanel', () => () => (
  <div data-testid="admin-users-panel">Admin Users Panel Mock</div>
));

jest.mock('./components/AuditLogPanel', () => () => (
  <div data-testid="audit-log-panel">Audit Log Panel Mock</div>
));

jest.mock('./components/RepoArchitectureAssistantPanel', () => () => (
  <div data-testid="repo-architecture-assistant-panel">Repo Architecture Assistant Mock</div>
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

jest.mock('./components/DetectionSimulatorPanel', () => () => (
  <div data-testid="detection-simulator-panel">Detection Simulator Panel Mock</div>
));

beforeEach(() => {
  jest.clearAllMocks();
  window.localStorage.clear();
  window.sessionStorage.clear();
  Object.defineProperty(window, 'innerWidth', {
    configurable: true,
    writable: true,
    value: 1280,
  });
  loadCurrentSession.mockResolvedValue({ authenticated: false });
  createAiThread.mockResolvedValue({ thread: { thread_id: 'ath_test', version: 1 } });
  getAiThread.mockResolvedValue({
    thread: {
      thread_id: 'ath_test',
      version: 1,
      primary_entity: { type: 'dashboard', id: 'dashboard' },
      focus_state: {},
      state: { unresolved_questions: [], corrections: [] },
    },
    active_request: null,
  });
  getAiThreadTurns.mockResolvedValue({ turns: [], next_cursor: null, has_more: false });
  resetAiThread.mockResolvedValue({
    thread: {
      thread_id: 'ath_replacement',
      version: 1,
      primary_entity: { type: 'dashboard', id: 'dashboard' },
      focus_state: {},
    },
  });
  loadAlerts.mockResolvedValue({ items: [], total: 0, limit: 50, offset: 0, sort: 'newest' });
  loadAlertDashboardSummary.mockResolvedValue({
    metrics: {
      total_alerts: 0,
      high_count: 0,
      medium_count: 0,
      low_count: 0,
      unique_source_ips: 0,
    },
    top_source_ips: [],
    timeline: [],
    map_markers: [],
  });
  loadAlertRuleOptions.mockResolvedValue([
    { rule_id: 'failed_login_threshold', label: 'Failed Login Threshold' },
  ]);
  loadAnalystWorkspace.mockResolvedValue({
    workspace: { id: 1, visibility: 'private' },
    items: [],
    investigations: [],
    notes: [],
    hypotheses: [],
    tasks: [],
    evidence: [],
  });
  pinWorkspaceItem.mockResolvedValue({ id: 1 });
  createEvidenceReference.mockResolvedValue({ id: 2 });
  createInvestigation.mockResolvedValue({ id: 3, linked_alert_id: 101, status: 'open' });
  createWorkspaceNote.mockResolvedValue({ id: 4 });
  createWorkspaceHypothesis.mockResolvedValue({ id: 5 });
  createWorkspaceTask.mockResolvedValue({ id: 6 });
  deleteEvidenceReference.mockResolvedValue({ deleted: true });
  deleteHypothesisEvidenceLink.mockResolvedValue({ deleted: true });
  deleteInvestigation.mockResolvedValue({ deleted: true });
  deleteWorkspaceNote.mockResolvedValue({ deleted: true });
  deleteWorkspaceHypothesis.mockResolvedValue({ deleted: true });
  deleteWorkspaceTask.mockResolvedValue({ deleted: true });
  linkHypothesisEvidence.mockResolvedValue({ id: 7 });
  loadInvestigationWorkspace.mockResolvedValue({
    workspace: { id: 1, visibility: 'private' },
    investigation: { id: 3, title: 'Investigation for alert #101', status: 'open', linked_alert_id: 101, confidence: 'medium', disposition: 'undetermined' },
    source_context: { alert: { id: 101, alert_type: 'failed_login_threshold', severity: 'high', source_ip: '8.8.8.8', message: 'failed login burst', created_at: '2026-07-29T20:00:00Z' }, incident: null, source_ip: '8.8.8.8', partial: [] },
    notes: [],
    hypotheses: [],
    tasks: [],
    evidence: [],
    hypothesis_evidence: [],
    timeline: [],
    unassigned: { items: [], notes: [], hypotheses: [], tasks: [], evidence: [] },
  });
  removeWorkspacePin.mockResolvedValue({ deleted: true });
  updateEvidenceReference.mockResolvedValue({ id: 8 });
  updateInvestigation.mockResolvedValue({ id: 3 });
  updateWorkspaceTask.mockResolvedValue({ id: 9 });
});

test('renders without crashing', async () => {
  render(<App />);
  expect(screen.getByText(/checking authentication/i)).toBeInTheDocument();
  expect(await screen.findByRole('heading', { name: /siem dashboard login/i })).toBeInTheDocument();
});

test('renders the login form for unauthenticated users', async () => {
  const { container } = render(<App />);

  expect(await screen.findByRole('heading', { name: /siem dashboard login/i })).toBeInTheDocument();
  expect(screen.getByText(/anakin analyst console/i)).toBeInTheDocument();
  expect(screen.getByText(/operational console/i)).toBeInTheDocument();
  expect(screen.queryByText(/^v0\.1\.0$/i)).not.toBeInTheDocument();
  expect(screen.getByText(/username/i)).toBeInTheDocument();
  expect(container.querySelector('input[type="text"]')).toBeInTheDocument();
  expect(screen.getByText(/password/i)).toBeInTheDocument();
  expect(container.querySelector('input[type="password"]')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /log in/i })).toBeInTheDocument();
});

test('renders Threat Brief only on Dashboard for analyst roles', async () => {
  loadCurrentSession.mockResolvedValue({
    authenticated: true,
    user: 'analyst1',
    role: 'analyst',
  });
  loadAlerts.mockResolvedValue({
    items: [{ id: 101, alert_type: 'critical_login', severity: 'critical', source_ip: '8.8.8.8', status: 'open' }],
    total: 1,
    limit: 50,
    offset: 0,
  });

  render(<App />);

  expect(await screen.findByRole('region', { name: 'Threat Brief' })).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: /soc command center/i }));
  expect(await screen.findByTestId('soc-command-center')).toBeInTheDocument();
  expect(screen.queryByRole('region', { name: 'Threat Brief' })).not.toBeInTheDocument();
});

test('authenticated sidebar omits visible package version label', async () => {
  loadCurrentSession.mockResolvedValue({
    authenticated: true,
    user: 'analyst1',
    role: 'analyst',
  });

  render(<App />);

  expect(await screen.findByRole('button', { name: /^dashboard$/i })).toBeInTheDocument();
  expect(screen.getByText('Operational')).toBeInTheDocument();
  expect(screen.queryByText(/^v0\.1\.0$/i)).not.toBeInTheDocument();
});

test('workspace investigation actions show feedback, saved state, and avoid duplicate saves', async () => {
  loadCurrentSession.mockResolvedValue({
    authenticated: true,
    user: 'analyst1',
    role: 'analyst',
  });
  const emptyWorkspace = {
    workspace: { id: 1, visibility: 'private' },
    items: [],
    investigations: [],
    notes: [],
    hypotheses: [],
    tasks: [],
    evidence: [],
  };
  const savedWorkspace = {
    ...emptyWorkspace,
    investigations: [{ id: 3, title: 'Investigation for alert #101', status: 'open', linked_alert_id: 101 }],
  };
  loadAnalystWorkspace
    .mockResolvedValueOnce(emptyWorkspace)
    .mockResolvedValueOnce(savedWorkspace)
    .mockResolvedValue(savedWorkspace);

  render(<App />);

  await userEvent.click(await screen.findByRole('button', { name: 'Dashboard open investigation' }));
  expect(await screen.findByRole('dialog', { name: 'Investigation Drawer' })).toHaveTextContent('Alert #101');

  await userEvent.click(screen.getByRole('button', { name: 'Save investigation state' }));
  expect(await screen.findAllByText(/Investigation saved to Analyst Workspace/i)).toHaveLength(2);
  expect(createInvestigation).toHaveBeenCalledTimes(1);

  await userEvent.click(screen.getByRole('button', { name: 'Save investigation state' }));
  expect(await screen.findAllByText(/already saved/i)).toHaveLength(2);
  expect(createInvestigation).toHaveBeenCalledTimes(1);

  await userEvent.click(screen.getByRole('button', { name: /^Analyst Workspace$/i }));
  expect((await screen.findAllByText('Investigation for alert #101')).length).toBeGreaterThan(1);
  expect(screen.getAllByText(/alert:101/i).length).toBeGreaterThan(1);
});

test('keeps the login card inside a narrow mobile viewport', async () => {
  Object.defineProperty(window, 'innerWidth', {
    configurable: true,
    writable: true,
    value: 360,
  });

  const { container } = render(<App />);

  const heading = await screen.findByRole('heading', { name: /siem dashboard login/i });
  const form = heading.closest('form');
  const shell = container.firstChild;

  expect(shell).toHaveStyle({ overflowX: 'hidden', boxSizing: 'border-box' });
  expect(form).toHaveStyle({
    width: '100%',
    maxWidth: '420px',
    minWidth: 0,
    flexShrink: 1,
    boxSizing: 'border-box',
  });
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

test('renders the NIST Evidence workspace for Analyst+ and hides it from viewers', async () => {
  loadCurrentSession.mockResolvedValue({ authenticated: true, user: 'analyst1', role: 'analyst' });
  const { unmount } = render(<App />);
  const nist = await screen.findByRole('button', { name: /^nist evidence$/i });
  await userEvent.click(nist);
  expect(await screen.findByTestId('nist-evidence-workspace')).toHaveAttribute('data-role', 'analyst');
  unmount();

  loadCurrentSession.mockResolvedValue({ authenticated: true, user: 'viewer1', role: 'viewer' });
  render(<App />);
  await screen.findByRole('button', { name: /^dashboard$/i });
  expect(screen.queryByRole('button', { name: /^nist evidence$/i })).not.toBeInTheDocument();
});

test('renders Detection Simulator for analyst and hides it from viewers', async () => {
  loadCurrentSession.mockResolvedValue({ authenticated: true, user: 'analyst1', role: 'analyst' });
  render(<App />);

  const detectionSimulator = await screen.findByRole('button', { name: /detection simulator/i });
  await userEvent.click(detectionSimulator);
  expect(await screen.findByTestId('detection-simulator-panel')).toBeInTheDocument();
});

test('does not render Detection Simulator nav for viewer role', async () => {
  loadCurrentSession.mockResolvedValue({ authenticated: true, user: 'viewer1', role: 'viewer' });
  render(<App />);

  await screen.findByRole('button', { name: /^dashboard$/i });
  expect(screen.queryByRole('button', { name: /detection simulator/i })).not.toBeInTheDocument();
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

test('workspace Back and Forward buttons restore prior workspaces and disabled state', async () => {
  loadCurrentSession.mockResolvedValue({
    authenticated: true,
    user: 'analyst1',
    role: 'analyst',
  });
  const historyBack = jest.spyOn(window.history, 'back').mockImplementation(() => {});
  const historyForward = jest.spyOn(window.history, 'forward').mockImplementation(() => {});

  render(<App />);

  const backButton = await screen.findByRole('button', { name: /^back$/i });
  const forwardButton = screen.getByRole('button', { name: /^forward$/i });
  expect(backButton).toBeDisabled();
  expect(forwardButton).toBeDisabled();

  await userEvent.click(screen.getByRole('button', { name: /soar operations/i }));
  expect(await screen.findByTestId('dead-letters-panel')).toBeInTheDocument();
  expect(backButton).not.toBeDisabled();
  expect(forwardButton).toBeDisabled();

  await userEvent.click(backButton);
  expect(await screen.findByTestId('dashboard-section')).toBeInTheDocument();
  expect(historyBack).toHaveBeenCalled();
  expect(backButton).toBeDisabled();
  expect(forwardButton).not.toBeDisabled();

  await userEvent.click(forwardButton);
  expect(await screen.findByTestId('dead-letters-panel')).toBeInTheDocument();
  expect(historyForward).toHaveBeenCalled();

  historyBack.mockRestore();
  historyForward.mockRestore();
});

test('browser popstate restores SIEM-owned workspace history entries', async () => {
  loadCurrentSession.mockResolvedValue({
    authenticated: true,
    user: 'analyst1',
    role: 'analyst',
  });

  render(<App />);

  expect(await screen.findByTestId('dashboard-section')).toBeInTheDocument();
  const dashboardState = window.history.state;

  await userEvent.click(screen.getByRole('button', { name: /soar operations/i }));
  expect(await screen.findByTestId('dead-letters-panel')).toBeInTheDocument();
  const operationsState = window.history.state;

  act(() => {
    window.dispatchEvent(new PopStateEvent('popstate', { state: dashboardState }));
  });
  expect(await screen.findByTestId('dashboard-section')).toBeInTheDocument();

  act(() => {
    window.dispatchEvent(new PopStateEvent('popstate', { state: operationsState }));
  });
  expect(await screen.findByTestId('dead-letters-panel')).toBeInTheDocument();
});

test('passes dashboard loading state before the first alerts requests resolve', async () => {
  loadCurrentSession.mockResolvedValue({
    authenticated: true,
    user: 'analyst1',
    role: 'analyst',
  });
  loadAlerts.mockImplementation(() => new Promise(() => {}));
  loadAlertDashboardSummary.mockImplementation(() => new Promise(() => {}));

  render(<App />);

  expect(await screen.findByTestId('dashboard-section')).toHaveTextContent('loading:true');
});

test('dashboard defaults alert requests to since tuning and can switch to all history', async () => {
  loadCurrentSession.mockResolvedValue({
    authenticated: true,
    user: 'analyst1',
    role: 'analyst',
  });

  render(<App />);

  await screen.findByTestId('dashboard-section');
  expect(loadAlerts).toHaveBeenCalledWith(expect.objectContaining({ operationalScope: 'since_tuning' }));
  expect(loadAlertDashboardSummary).toHaveBeenCalledWith(expect.objectContaining({ operationalScope: 'since_tuning' }));

  await userEvent.click(screen.getByRole('button', { name: 'Dashboard show all history' }));

  await waitFor(() => {
    expect(loadAlerts).toHaveBeenLastCalledWith(expect.objectContaining({ operationalScope: 'all_history' }));
  });
  expect(loadAlertDashboardSummary).toHaveBeenLastCalledWith(expect.objectContaining({ operationalScope: 'all_history' }));
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
  await waitFor(() => {
    expect(loadAlerts).toHaveBeenLastCalledWith(
      expect.objectContaining({ exactSourceIp: '203.0.113.10', searchTerm: '' })
    );
  });
  expect(screen.getByText('Recent Alerts target')).toHaveFocus();
  expect(main.scrollTo).toHaveBeenCalledWith({ top: 320, left: 0, behavior: 'smooth' });

  HTMLElement.prototype.getBoundingClientRect = originalGetBoundingClientRect;
});

test('contextual alert pivots clear incompatible local filters while manual filters remain preserved', async () => {
  loadCurrentSession.mockResolvedValue({ authenticated: true, user: 'analyst1', role: 'analyst' });
  render(<App />);
  const dashboard = await screen.findByTestId('dashboard-section');

  await userEvent.click(screen.getByRole('button', { name: 'Dashboard set severity' }));
  await userEvent.click(screen.getByRole('button', { name: 'Dashboard set status' }));
  await userEvent.click(screen.getByRole('button', { name: 'Dashboard set source' }));
  await userEvent.click(screen.getByRole('button', { name: 'Dashboard set rule' }));
  await userEvent.click(screen.getByRole('button', { name: 'Dashboard set search' }));

  expect(dashboard).toHaveTextContent('search:manual search');
  expect(dashboard).toHaveTextContent('severity:high');
  expect(dashboard).toHaveTextContent('status:resolved');
  expect(dashboard).toHaveTextContent('source:pfsense');
  expect(dashboard).toHaveTextContent('rule:failed_login_threshold');

  await userEvent.click(screen.getByRole('button', { name: /soar incidents/i }));
  await userEvent.click(await screen.findByRole('button', { name: 'Incident open related alerts' }));

  await waitFor(() => {
    expect(loadAlerts).toHaveBeenLastCalledWith(
      expect.objectContaining({
        exactSourceIp: '203.0.113.10',
        searchTerm: '',
        severityFilter: '',
        statusFilter: '',
        sourceFilter: 'all',
        ruleFilter: 'all',
        offset: 0,
      })
    );
  });

  await userEvent.click(screen.getByRole('button', { name: /^dashboard$/i }));
  expect(await screen.findByTestId('dashboard-section')).toHaveTextContent('search:');
  expect(screen.getByTestId('dashboard-section')).toHaveTextContent('severity:');
  expect(screen.getByTestId('dashboard-section')).toHaveTextContent('status:');
  expect(screen.getByTestId('dashboard-section')).toHaveTextContent('rule:all');
  expect(screen.getByTestId('dashboard-section')).toHaveTextContent('source:all');
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

test('SOC entity AI requests do not include full visible dashboard context', async () => {
  loadCurrentSession.mockResolvedValue({
    authenticated: true,
    user: 'analyst1',
    role: 'analyst',
  });
  loadAlertDashboardSummary.mockResolvedValue({
    metrics: { total_alerts: 99, high_count: 9, medium_count: 8, low_count: 7, unique_source_ips: 6 },
    top_source_ips: [{ source_ip: '198.51.100.10' }],
    timeline: [{ bucket: '2026-01-01T00:00:00Z', count: 5 }],
    map_markers: [{ source_ip: '198.51.100.10', lat: 1, lon: 2 }],
  });
  loadAlerts.mockResolvedValue({
    items: [{ id: 101, alert_type: 'scan', severity: 'high', source_ip: '198.51.100.10', status: 'open' }],
    total: 1,
    limit: 50,
    offset: 0,
    sort: 'newest',
  });
  queueAiWorkflowRequest.mockImplementationOnce(() => new Promise(() => {}));

  render(<App />);

  await userEvent.click(await screen.findByRole('button', { name: /soc command center/i }));
  await userEvent.click(await screen.findByRole('button', { name: /soc explain recon/i }));

  await waitFor(() => expect(queueAiWorkflowRequest).toHaveBeenCalled());
  const [payload] = queueAiWorkflowRequest.mock.calls[0];
  expect(payload.context_type).toBe('recon_activity');
  expect(payload.context.activity_id).toBe(90);
  expect(payload.context.command).toMatchObject({ id: 'contextual.recon_activity.explain_recon_activity', read_only: true });
  expect(payload.context.dashboard_summary).toBeUndefined();
  expect(payload.context.timeline).toBeUndefined();
  expect(payload.context.map_markers).toBeUndefined();
  expect(payload.context.recent_alerts).toBeUndefined();
});

test('freeform Ask Anakin auto route queues and polls backend-classified long workflows', async () => {
  loadCurrentSession.mockResolvedValue({
    authenticated: true,
    user: 'analyst1',
    role: 'analyst',
  });
  queueAiWorkflowRequest.mockResolvedValueOnce({
    status: 'queued',
    workflow: 'deep_investigate',
    request_id: 'aiwf_auto_deep',
    classification: {
      requested_workflow: 'auto',
      classified_workflow: 'deep_investigate',
      confidence: 'high',
    },
    lifecycle: { stages: [{ stage: 'queued', status: 'running' }] },
    metadata: { async: true },
  });
  getAiWorkflowRequest.mockResolvedValueOnce({
    status: 'completed',
    workflow: 'deep_investigate',
    request_id: 'aiwf_auto_deep',
    result: { status: 'success', answer: 'Correlated evidence is ready.', metadata: {}, context: {} },
    metadata: { async: true },
    lifecycle: { stages: [{ stage: 'complete', status: 'completed' }] },
  });
  getAiThreadTurns
    .mockResolvedValueOnce({ turns: [], next_cursor: null, has_more: false })
    .mockResolvedValueOnce({
      turns: [{ turn_id: 'turn_auto_user', sequence: 1, role: 'user', content: 'Deep investigate this alert and evidence gaps' }],
      next_cursor: null,
      has_more: false,
    })
    .mockResolvedValueOnce({
      turns: [
        { turn_id: 'turn_auto_user', sequence: 1, role: 'user', content: 'Deep investigate this alert and evidence gaps' },
        { turn_id: 'turn_auto_answer', sequence: 2, role: 'assistant', content: 'Correlated evidence is ready.' },
      ],
      next_cursor: null,
      has_more: false,
    });

  render(<App />);

  await userEvent.click(await screen.findByRole('button', { name: /open general anakin siem chat/i }));
  await userEvent.type(screen.getByLabelText(/^ask anakin$/i), 'Deep investigate this alert and evidence gaps');
  await userEvent.click(screen.getByRole('button', { name: /submit ask anakin question/i }));

  await waitFor(() => expect(queueAiWorkflowRequest).toHaveBeenCalled());
  expect(createAiThread).toHaveBeenCalledWith({
    domain: 'siem',
    primary_entity: { type: 'dashboard', id: 'dashboard' },
    is_default: true,
  });
  expect(queueAiWorkflowRequest.mock.calls[0][0]).toMatchObject({
    workflow: 'auto',
    prompt: 'Deep investigate this alert and evidence gaps',
    conversation: {
      thread_id: 'ath_test',
      expected_version: 1,
      client_request_id: expect.any(String),
    },
  });
  expect(requestAiWorkflow).not.toHaveBeenCalled();
  await waitFor(() => expect(getAiWorkflowRequest).toHaveBeenCalledWith('aiwf_auto_deep', expect.any(Object)));
  expect(await screen.findByText(/correlated evidence is ready/i)).toBeInTheDocument();
});

test('freeform Ask Anakin auto route renders immediate quick result from queue endpoint', async () => {
  loadCurrentSession.mockResolvedValue({
    authenticated: true,
    user: 'analyst1',
    role: 'analyst',
  });
  queueAiWorkflowRequest.mockResolvedValueOnce({
    status: 'success',
    workflow: 'quick_explain',
    classification: {
      requested_workflow: 'auto',
      classified_workflow: 'quick_explain',
      confidence: 'medium',
    },
    result: { status: 'success', answer: 'Short answer.', metadata: {}, context: {} },
    metadata: { async: false, immediate: true },
  });
  getAiThreadTurns
    .mockResolvedValueOnce({ turns: [], next_cursor: null, has_more: false })
    .mockResolvedValueOnce({
      turns: [
        { turn_id: 'turn_quick_user', sequence: 1, role: 'user', content: 'Explain this alert briefly' },
        { turn_id: 'turn_quick_answer', sequence: 2, role: 'assistant', content: 'Short answer.' },
      ],
      next_cursor: null,
      has_more: false,
    });

  render(<App />);

  await userEvent.click(await screen.findByRole('button', { name: /open general anakin siem chat/i }));
  await userEvent.type(screen.getByLabelText(/^ask anakin$/i), 'Explain this alert briefly');
  await userEvent.click(screen.getByRole('button', { name: /submit ask anakin question/i }));

  await waitFor(() => expect(queueAiWorkflowRequest).toHaveBeenCalled());
  expect(getAiWorkflowRequest).not.toHaveBeenCalled();
  expect(requestAiWorkflow).not.toHaveBeenCalled();
  expect(await screen.findByText(/short answer/i)).toBeInTheDocument();
});

test('contextual controls hand foreground to the one canonical conversation surface', async () => {
  loadCurrentSession.mockResolvedValue({ authenticated: true, user: 'analyst1', role: 'analyst' });
  requestAiWorkflow.mockResolvedValueOnce({
    status: 'success',
    workflow: 'quick_explain',
    result: { status: 'success', answer: 'Alert 7 needs review.', metadata: {}, context: {} },
    metadata: { async: false, immediate: true },
  });

  render(<App />);

  const dashboard = await screen.findByTestId('dashboard-section');
  await userEvent.click(screen.getByRole('button', { name: 'Dashboard open alert details mock' }));
  expect(dashboard).toHaveAttribute('data-anakin-open', 'false');
  await userEvent.click(screen.getByRole('button', { name: 'Explain alert 7 mock' }));

  await waitFor(() => expect(requestAiWorkflow).toHaveBeenCalledTimes(1));
  expect(screen.getAllByRole('dialog', { name: 'Anakin conversation' })).toHaveLength(1);
  expect(document.querySelectorAll('[data-anakin-surface="canonical"]')).toHaveLength(1);
  expect(dashboard).toHaveAttribute('data-anakin-open', 'true');
  expect(screen.queryByRole('dialog', { name: 'Anakin assistant response' })).not.toBeInTheDocument();
});

test('a delayed completion cannot attach after another foreground context takes ownership', async () => {
  loadCurrentSession.mockResolvedValue({ authenticated: true, user: 'analyst1', role: 'analyst' });
  let resolveQueue;
  queueAiWorkflowRequest.mockReturnValueOnce(new Promise((resolve) => { resolveQueue = resolve; }));

  render(<App />);
  await userEvent.click(await screen.findByRole('button', { name: /open general anakin siem chat/i }));
  await userEvent.type(screen.getByLabelText(/^ask anakin$/i), 'Investigate the current activity');
  await userEvent.click(screen.getByRole('button', { name: /submit ask anakin question/i }));
  await waitFor(() => expect(queueAiWorkflowRequest).toHaveBeenCalledTimes(1));

  await userEvent.click(screen.getByRole('button', { name: 'Dashboard open alert details mock' }));
  expect(screen.queryByRole('dialog', { name: 'Anakin conversation' })).not.toBeInTheDocument();

  await act(async () => {
    resolveQueue({
      status: 'completed',
      workflow: 'auto',
      request_id: 'aiwf_stale',
      result: { status: 'success', answer: 'Stale answer from the previous selection.' },
    });
  });

  await userEvent.click(screen.getByRole('button', { name: /open general anakin siem chat/i }));
  await waitFor(() => expect(screen.queryByText(/reviewing the available context/i)).not.toBeInTheDocument());
  expect(screen.queryByText(/stale answer from the previous selection/i)).not.toBeInTheDocument();
});

test('reset replaces the active thread and New Thread intentionally creates a non-default thread', async () => {
  loadCurrentSession.mockResolvedValue({ authenticated: true, user: 'analyst1', role: 'analyst' });
  window.sessionStorage.setItem(
    'anakin.activeThreadPointer.v1',
    JSON.stringify({ owner: 'analyst1', threadId: 'ath_test', entity: { type: 'dashboard', id: 'dashboard' } })
  );
  createAiThread.mockResolvedValueOnce({
    thread: { thread_id: 'ath_explicit', version: 1, primary_entity: { type: 'dashboard', id: 'dashboard' }, focus_state: {} },
  });

  render(<App />);
  await waitFor(() => expect(getAiThread).toHaveBeenCalledWith('ath_test'));
  await userEvent.click(screen.getByRole('button', { name: /open general anakin siem chat/i }));
  await userEvent.click(screen.getByRole('button', { name: 'Reset' }));
  await waitFor(() => expect(resetAiThread).toHaveBeenCalledWith('ath_test', { expected_version: 1 }));
  await userEvent.click(screen.getByRole('button', { name: 'New thread' }));
  await waitFor(() => expect(createAiThread).toHaveBeenCalledWith(expect.objectContaining({ is_default: false })));
});

test('logout clears thread and async request pointers before another identity can render them', async () => {
  loadCurrentSession.mockResolvedValue({ authenticated: true, user: 'analyst1', role: 'analyst' });
  window.sessionStorage.setItem('anakin.activeThreadPointer.v1', JSON.stringify({ owner: 'analyst1', threadId: 'ath_test' }));
  window.sessionStorage.setItem('anakin.activeWorkflowRequests.v1', JSON.stringify({ saved: { requestId: 'aiwf_1' } }));

  render(<App />);
  await screen.findByText(/signed in as analyst1/i);
  await userEvent.click(screen.getByRole('button', { name: /switch account \/ logout/i }));

  await waitFor(() => expect(window.sessionStorage.getItem('anakin.activeThreadPointer.v1')).toBeNull());
  expect(window.sessionStorage.getItem('anakin.activeWorkflowRequests.v1')).toBeNull();
  expect(screen.queryByRole('dialog', { name: 'Anakin conversation' })).not.toBeInTheDocument();
});

test('restores every ordered turn page so newer responses are not omitted', async () => {
  loadCurrentSession.mockResolvedValue({ authenticated: true, user: 'analyst1', role: 'analyst' });
  window.sessionStorage.setItem(
    'anakin.activeThreadPointer.v1',
    JSON.stringify({ owner: 'analyst1', threadId: 'ath_test' })
  );
  getAiThreadTurns
    .mockResolvedValueOnce({
      turns: [{ turn_id: 'turn_1', sequence: 1, role: 'user', content: 'First question' }],
      next_cursor: 1,
      has_more: true,
    })
    .mockResolvedValueOnce({
      turns: [{ turn_id: 'turn_2', sequence: 2, role: 'assistant', content: 'Newest answer' }],
      next_cursor: null,
      has_more: false,
    });

  render(<App />);
  await waitFor(() => expect(getAiThreadTurns).toHaveBeenNthCalledWith(2, 'ath_test', { limit: 100, cursor: 1 }));
  await userEvent.click(screen.getByRole('button', { name: /open general anakin siem chat/i }));

  expect(await screen.findByText('First question')).toBeInTheDocument();
  expect(screen.getByText('Newest answer')).toBeInTheDocument();
});

test('restores the authorized thread and resumes its active request after remount', async () => {
  loadCurrentSession.mockResolvedValue({
    authenticated: true,
    user: 'analyst1',
    role: 'analyst',
  });
  window.sessionStorage.setItem(
    'anakin.activeThreadPointer.v1',
    JSON.stringify({ owner: 'analyst1', threadId: 'ath_test', entity: { type: 'dashboard', id: 'dashboard' } })
  );
  getAiThread.mockResolvedValueOnce({
    thread: {
      thread_id: 'ath_test',
      version: 2,
      primary_entity: { type: 'dashboard', id: 'dashboard' },
      focus_state: {},
      state: { unresolved_questions: [], corrections: [] },
    },
    active_request: {
      request_id: 'aiwf_auto_saved',
      thread_id: 'ath_test',
      status: 'running',
      workflow: 'decision_support',
      terminal: false,
    },
  });
  getAiWorkflowRequest.mockResolvedValueOnce({
    status: 'completed',
    workflow: 'decision_support',
    request_id: 'aiwf_auto_saved',
    result: { status: 'success', answer: 'Escalate based on confirmed follow-up.', metadata: {}, context: {} },
    metadata: { async: true },
    lifecycle: { stages: [{ stage: 'complete', status: 'completed' }] },
  });
  getAiThreadTurns
    .mockResolvedValueOnce({
      turns: [{ turn_id: 'turn_saved_user', sequence: 1, role: 'user', content: 'What should I do next?' }],
      next_cursor: null,
      has_more: false,
    })
    .mockResolvedValueOnce({
      turns: [
        { turn_id: 'turn_saved_user', sequence: 1, role: 'user', content: 'What should I do next?' },
        { turn_id: 'turn_saved_answer', sequence: 2, role: 'assistant', content: 'Escalate based on confirmed follow-up.' },
      ],
      next_cursor: null,
      has_more: false,
    });

  render(<App />);

  await waitFor(() => expect(getAiWorkflowRequest).toHaveBeenCalledWith('aiwf_auto_saved', expect.any(Object)));
  expect(queueAiWorkflowRequest).not.toHaveBeenCalled();
  expect(await screen.findByText(/escalate based on confirmed follow-up/i)).toBeInTheDocument();
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
  expect(screen.getByRole('button', { name: /ai gateway policy/i })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /user management/i })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /audit logs/i })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /repo architecture ai/i })).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /^administration$/i })).not.toBeInTheDocument();

  await userEvent.click(screen.getByRole('button', { name: /detection rules/i }));
  expect(await screen.findByTestId('detection-rules-panel')).toBeInTheDocument();
  expect(screen.queryByTestId('admin-users-panel')).not.toBeInTheDocument();
  expect(screen.queryByTestId('audit-log-panel')).not.toBeInTheDocument();

  await userEvent.click(screen.getByRole('button', { name: /user management/i }));
  expect(await screen.findByTestId('admin-users-panel')).toBeInTheDocument();
  expect(screen.queryByTestId('detection-rules-panel')).not.toBeInTheDocument();
  expect(screen.queryByTestId('audit-log-panel')).not.toBeInTheDocument();

  await userEvent.click(screen.getByRole('button', { name: /ai gateway policy/i }));
  expect(await screen.findByTestId('ai-gateway-config-panel')).toBeInTheDocument();
  expect(screen.queryByTestId('detection-rules-panel')).not.toBeInTheDocument();
  expect(screen.queryByTestId('admin-users-panel')).not.toBeInTheDocument();

  await userEvent.click(screen.getByRole('button', { name: /audit logs/i }));
  expect(await screen.findByTestId('audit-log-panel')).toBeInTheDocument();
  expect(screen.queryByTestId('detection-rules-panel')).not.toBeInTheDocument();
  expect(screen.queryByTestId('admin-users-panel')).not.toBeInTheDocument();

  await userEvent.click(screen.getByRole('button', { name: /repo architecture ai/i }));
  expect(await screen.findByTestId('repo-architecture-assistant-panel')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /open general anakin siem chat/i })).toBeInTheDocument();
  expect(screen.queryByTestId('detection-rules-panel')).not.toBeInTheDocument();
  expect(screen.queryByTestId('admin-users-panel')).not.toBeInTheDocument();
  expect(screen.queryByTestId('audit-log-panel')).not.toBeInTheDocument();
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
  expect(screen.queryByRole('button', { name: /ai gateway policy/i })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /user management/i })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /audit logs/i })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /repo architecture ai/i })).not.toBeInTheDocument();
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
  expect(screen.queryByRole('button', { name: /repo architecture ai/i })).not.toBeInTheDocument();
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
