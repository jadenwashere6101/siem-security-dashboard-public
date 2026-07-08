import React from "react";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import SettingsPanel from "./SettingsPanel";
import { DEFAULT_UI_SETTINGS } from "../utils/uiSettings";

const baseProps = {
  settings: DEFAULT_UI_SETTINGS,
  landingPageOptions: [{ id: "dashboard", label: "Dashboard" }],
  onDefaultLandingPageChange: jest.fn(),
  onAutoRefreshIntervalChange: jest.fn(),
  onDisplaySettingsChange: jest.fn(),
  onNotificationSettingsChange: jest.fn(),
  sections: [],
  roleFlags: {},
  cardStyle: {},
  cardHeaderStyle: {},
  cardTitleStyle: {},
  cardSubtitleStyle: {},
  filterLabelStyle: {},
  selectStyle: {},
};

const renderPanel = (overrides = {}) =>
  render(
    <SettingsPanel
      {...baseProps}
      {...overrides}
      settings={{
        ...DEFAULT_UI_SETTINGS,
        ...overrides.settings,
        display: {
          ...DEFAULT_UI_SETTINGS.display,
          ...overrides.settings?.display,
        },
        notifications: {
          ...DEFAULT_UI_SETTINGS.notifications,
          ...overrides.settings?.notifications,
        },
      }}
    />
  );

const defineNotificationMock = ({ permission = "granted", requestPermission } = {}) => {
  const NotificationMock = jest.fn();
  NotificationMock.permission = permission;
  NotificationMock.requestPermission =
    requestPermission || jest.fn().mockResolvedValue(permission);
  Object.defineProperty(window, "Notification", {
    configurable: true,
    writable: true,
    value: NotificationMock,
  });
  return NotificationMock;
};

beforeEach(() => {
  jest.clearAllMocks();
  delete window.Notification;
  delete window.Audio;
});

test("shows notification and alert sound preferences without requiring real alerts", () => {
  renderPanel();

  expect(screen.getByText(/^alert sound$/i)).toBeInTheDocument();
  expect(screen.getByText(/^browser notifications$/i)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /test browser notification/i })).toBeInTheDocument();
  expect(
    screen.getByText(/test notifications are synthetic and do not create or modify siem alerts/i)
  ).toBeInTheDocument();
});

test("enabling browser notifications requests permission from the default state", async () => {
  const requestPermission = jest.fn().mockResolvedValue("granted");
  defineNotificationMock({ permission: "default", requestPermission });
  const onNotificationSettingsChange = jest.fn();

  renderPanel({ onNotificationSettingsChange });

  await userEvent.click(screen.getByLabelText(/browser notifications/i));

  await waitFor(() => {
    expect(requestPermission).toHaveBeenCalledTimes(1);
    expect(onNotificationSettingsChange).toHaveBeenCalledWith({
      browserNotificationsEnabled: true,
    });
  });
});

test("granted permission sends a synthetic test browser notification", async () => {
  const NotificationMock = defineNotificationMock({ permission: "granted" });

  renderPanel();

  await act(async () => {
    await userEvent.click(screen.getByRole("button", { name: /test browser notification/i }));
  });

  await waitFor(() => {
    expect(NotificationMock).toHaveBeenCalledWith("Test SIEM alert notification", {
      body: "Synthetic notification from Settings. No real alert was created.",
    });
    expect(screen.getByText(/test browser notification sent/i)).toBeInTheDocument();
  });
});

test("denied permission guards browser notification actions", () => {
  defineNotificationMock({ permission: "denied" });

  renderPanel();

  expect(screen.getByText(/browser permission blocked/i)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /test browser notification/i })).toBeDisabled();
});

test("unavailable Notification API is handled gracefully", () => {
  renderPanel();

  expect(screen.getByText(/browser notifications unavailable/i)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /test browser notification/i })).toBeDisabled();
});

test("Notification constructor errors are handled gracefully", async () => {
  const NotificationMock = jest.fn(() => {
    throw new Error("blocked");
  });
  NotificationMock.permission = "granted";
  NotificationMock.requestPermission = jest.fn().mockResolvedValue("granted");
  Object.defineProperty(window, "Notification", {
    configurable: true,
    writable: true,
    value: NotificationMock,
  });

  renderPanel();

  await act(async () => {
    await userEvent.click(screen.getByRole("button", { name: /test browser notification/i }));
  });

  expect(await screen.findByText(/unable to show test browser notification/i)).toBeInTheDocument();
});

test("alert sound test uses configured volume and reports success", async () => {
  const play = jest.fn().mockResolvedValue(undefined);
  const AudioMock = jest.fn().mockImplementation(() => ({
    play,
    volume: 0,
  }));
  window.Audio = AudioMock;

  renderPanel({
    settings: {
      notifications: {
        alertSoundsEnabled: true,
        alertSoundVolume: 0.75,
      },
    },
  });

  await userEvent.click(screen.getByRole("button", { name: /test alert sound/i }));

  await waitFor(() => {
    expect(AudioMock).toHaveBeenCalledTimes(1);
    expect(AudioMock.mock.results[0].value.volume).toBe(0.75);
    expect(play).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/test alert sound played/i)).toBeInTheDocument();
  });
});

test("alert sound test handles playback failure", async () => {
  window.Audio = jest.fn().mockImplementation(() => ({
    play: jest.fn().mockRejectedValue(new Error("blocked")),
    volume: 0,
  }));

  renderPanel({
    settings: {
      notifications: {
        alertSoundsEnabled: true,
      },
    },
  });

  await userEvent.click(screen.getByRole("button", { name: /test alert sound/i }));

  expect(await screen.findByText(/unable to play the test alert sound/i)).toBeInTheDocument();
});
