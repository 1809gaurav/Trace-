import { useEffect, useMemo, useState } from 'react';

export interface A11ySettings {
  fontScale: 100 | 125 | 150;
  highContrast: boolean;
  playfulMotion: boolean;
  dyslexiaMode: boolean;
}

const STORAGE_KEY = 'forensicrecover-a11y';

const defaults: A11ySettings = {
  fontScale: 100,
  highContrast: false,
  playfulMotion: true,
  dyslexiaMode: false,
};

function readStoredSettings(): A11ySettings {
  if (typeof window === 'undefined') {
    return defaults;
  }

  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (!raw) {
    return defaults;
  }

  try {
    const parsed = JSON.parse(raw) as Partial<A11ySettings>;
    return {
      ...defaults,
      ...parsed,
    };
  } catch {
    return defaults;
  }
}

export function useA11ySettings() {
  const [settings, setSettings] = useState<A11ySettings>(readStoredSettings);

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
    document.documentElement.style.fontSize = `${settings.fontScale}%`;
    document.body.dataset.highContrast = String(settings.highContrast);
    document.body.dataset.playfulMotion = String(settings.playfulMotion);
    document.body.dataset.dyslexiaMode = String(settings.dyslexiaMode);
  }, [settings]);

  const value = useMemo(
    () => ({
      settings,
      setFontScale: (fontScale: A11ySettings['fontScale']) =>
        setSettings((current) => ({ ...current, fontScale })),
      setHighContrast: (highContrast: boolean) =>
        setSettings((current) => ({ ...current, highContrast })),
      setPlayfulMotion: (playfulMotion: boolean) =>
        setSettings((current) => ({ ...current, playfulMotion })),
      setDyslexiaMode: (dyslexiaMode: boolean) =>
        setSettings((current) => ({ ...current, dyslexiaMode })),
    }),
    [settings],
  );

  return value;
}
