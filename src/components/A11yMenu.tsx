import { Accessibility, Contrast, ScanText, Sparkles } from 'lucide-react';
import { useState } from 'react';
import type { A11ySettings } from '../hooks/useA11ySettings';

export function A11yMenu({
  settings,
  onFontScale,
  onHighContrast,
  onPlayfulMotion,
  onDyslexiaMode,
}: {
  settings: A11ySettings;
  onFontScale: (value: 100 | 125 | 150) => void;
  onHighContrast: (value: boolean) => void;
  onPlayfulMotion: (value: boolean) => void;
  onDyslexiaMode: (value: boolean) => void;
}) {
  const [open, setOpen] = useState(false);

  return (
    <div className="fixed bottom-4 left-4 z-40">
      <div className={`overflow-hidden rounded-[18px] border border-line bg-cream-deep shadow-paper transition-all ${open ? 'max-h-[360px] w-[260px] p-3' : 'max-h-[52px] w-[52px] p-0'}`}>
        <button
          type="button"
          className="flex h-11 w-11 items-center justify-center rounded-full border border-line bg-cream-deep text-forest transition hover:bg-cream-deep focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-forest focus-visible:ring-offset-2 focus-visible:ring-offset-cream"
          onClick={() => setOpen((current) => !current)}
          aria-expanded={open}
          aria-label="Accessibility settings"
        >
          <Accessibility size={18} />
        </button>

        {open ? (
          <div className="mt-3 space-y-3">
            <div>
              <p className="text-[11px] uppercase tracking-[0.12em] text-forest-card">Text size</p>
              <div className="mt-2 flex gap-2">
                {[100, 125, 150].map((size) => (
                  <button
                    key={size}
                    type="button"
                    onClick={() => onFontScale(size as 100 | 125 | 150)}
                    className={`flex-1 rounded-full border px-2 py-2 text-sm font-medium focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-forest focus-visible:ring-offset-2 focus-visible:ring-offset-cream ${
                      settings.fontScale === size ? 'border-line bg-cream text-forest' : 'border-line bg-cream-deep text-forest'
                    }`}
                  >
                    {size}%
                  </button>
                ))}
              </div>
            </div>

            <label className="flex items-center justify-between gap-3 rounded-[12px] border border-line bg-cream p-2 text-sm text-forest">
              <span className="flex items-center gap-2"><Contrast size={16} /> High contrast</span>
              <input type="checkbox" checked={settings.highContrast} onChange={(event) => onHighContrast(event.target.checked)} />
            </label>

            <label className="flex items-center justify-between gap-3 rounded-[12px] border border-line bg-cream p-2 text-sm text-forest">
              <span className="flex items-center gap-2"><Sparkles size={16} /> Playful motion</span>
              <input type="checkbox" checked={settings.playfulMotion} onChange={(event) => onPlayfulMotion(event.target.checked)} />
            </label>

            <label className="flex items-center justify-between gap-3 rounded-[12px] border border-line bg-cream p-2 text-sm text-forest">
              <span className="flex items-center gap-2"><ScanText size={16} /> Dyslexia-friendly</span>
              <input type="checkbox" checked={settings.dyslexiaMode} onChange={(event) => onDyslexiaMode(event.target.checked)} />
            </label>
          </div>
        ) : null}
      </div>
    </div>
  );
}
