import React, { createContext, useCallback, useContext, useMemo, useState } from "react";

import { DEFAULT_UI_SETTINGS, readUiSettings, writeUiSettings } from "../utils/uiSettings";

const UiSettingsContext = createContext({
  settings: DEFAULT_UI_SETTINGS,
  updateSettings: () => {},
});

export function UiSettingsProvider({ children }) {
  const [settings, setSettings] = useState(() => readUiSettings());

  const updateSettings = useCallback((updater) => {
    setSettings((previous) => {
      const nextCandidate =
        typeof updater === "function" ? updater(previous) : { ...previous, ...updater };
      return writeUiSettings(nextCandidate);
    });
  }, []);

  const value = useMemo(
    () => ({
      settings,
      updateSettings,
    }),
    [settings, updateSettings]
  );

  return <UiSettingsContext.Provider value={value}>{children}</UiSettingsContext.Provider>;
}

export const useUiSettings = () => useContext(UiSettingsContext);
