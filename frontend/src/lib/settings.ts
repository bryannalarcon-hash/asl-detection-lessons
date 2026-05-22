// App Settings persistence (localStorage). Mirrors the App Settings page's toggles
// and seeds the Lesson Intro toggles' defaults.
import { useEffect, useState } from 'react';
import { APP_SETTINGS_LS_KEY } from './constants';

export interface AppSettings {
  cameraDefault: boolean;
  referenceDefault: boolean;
  playbackSpeed: 1 | 0.75;
  autoAdvanceMs: 0 | 800 | 1500;
  reducedMotion: boolean;
  mirror: boolean;
}

export const DEFAULT_SETTINGS: AppSettings = {
  cameraDefault: true,
  referenceDefault: true,
  playbackSpeed: 1,
  autoAdvanceMs: 0,
  reducedMotion: false,
  mirror: true,
};

function read(): AppSettings {
  if (typeof window === 'undefined') return DEFAULT_SETTINGS;
  try {
    const raw = window.localStorage.getItem(APP_SETTINGS_LS_KEY);
    if (!raw) return DEFAULT_SETTINGS;
    const parsed = JSON.parse(raw) as Partial<AppSettings>;
    return { ...DEFAULT_SETTINGS, ...parsed };
  } catch {
    return DEFAULT_SETTINGS;
  }
}

function write(settings: AppSettings) {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(APP_SETTINGS_LS_KEY, JSON.stringify(settings));
  } catch {
    // ignore storage failures (private-browsing mode etc.)
  }
}

export function useAppSettings() {
  const [settings, setSettings] = useState<AppSettings>(() => read());

  useEffect(() => {
    write(settings);
  }, [settings]);

  const update = (patch: Partial<AppSettings>) => {
    setSettings((prev) => ({ ...prev, ...patch }));
  };

  return { settings, update };
}

export function loadSettings(): AppSettings {
  return read();
}
