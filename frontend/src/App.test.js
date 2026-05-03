import { render, screen } from '@testing-library/react';
import App from './App';
import { loadCurrentSession } from './services/authService';

jest.mock('./services/authService', () => ({
  loadCurrentSession: jest.fn(),
  loginToDashboard: jest.fn(),
  logoutFromDashboard: jest.fn(),
}));

beforeEach(() => {
  loadCurrentSession.mockResolvedValue({ authenticated: false });
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
