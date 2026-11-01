export function ConfidenceMeter({ value }: { value: number }) {
  const percent = Math.max(0, Math.min(100, Math.round(value * 100)));

  return (
    <div aria-label={`Confidence ${percent}%`} className="space-y-2">
      <div className="flex items-center justify-between text-[11px] font-semibold uppercase tracking-[0.12em] text-forest-card">
        <span>How sure we are</span>
        <span>{percent}%</span>
      </div>
      <div className="h-2.5 overflow-hidden rounded-full border border-line bg-cream-deep">
        <div
          className="h-full rounded-full bg-leaf"
          style={{ width: `${percent}%` }}
          aria-hidden="true"
        />
      </div>
    </div>
  );
}
