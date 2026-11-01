import { useState } from 'react';

export function BeforeAfterSlider() {
  const [position, setPosition] = useState(55);

  return (
    <div className="rounded-[20px] border border-line bg-cream-deep p-4">
      <div className="mb-3 flex items-center justify-between text-[11px] uppercase tracking-[0.14em] text-forest-card">
        <span>Before / after</span>
        <span>{position}%</span>
      </div>
      <div className="relative h-52 overflow-hidden rounded-[12px] border border-line evidence-preview-surface">
        <div className="absolute inset-0 evidence-preview-duotone" />
        <div
          className="absolute inset-y-0 left-0 w-full overflow-hidden border-r-2 border-line evidence-preview-visual"
          style={{ width: `${position}%` }}
        >
          <div className="flex h-full items-center justify-center text-2xl font-semibold text-forest">After</div>
        </div>
        <div className="flex h-full items-center justify-center text-2xl font-semibold text-forest">Before</div>
        <div
          className="absolute inset-y-0 z-10 w-1 bg-forest"
          style={{ left: `${position}%` }}
          aria-hidden="true"
        />
      </div>
      <input
        aria-label="Adjust before and after reconstruction view"
        type="range"
        min={0}
        max={100}
        value={position}
        onChange={(event) => setPosition(Number(event.target.value))}
        className="mt-4 w-full accent-leaf"
      />
    </div>
  );
}
