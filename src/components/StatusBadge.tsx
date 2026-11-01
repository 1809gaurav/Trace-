import { Scissors, Puzzle, CircleDashed, ShieldCheck } from 'lucide-react';
import type { Classification } from '../api/types';

const config: Record<Classification, { label: string; Icon: typeof ShieldCheck; className: string }> = {
  intact: { label: 'Intact', Icon: ShieldCheck, className: 'border-leaf bg-leaf text-on-dark' },
  carved: { label: 'Carved', Icon: Scissors, className: 'border-2 border-forest bg-transparent text-forest' },
  reconstructed: { label: 'Reconstructed', Icon: Puzzle, className: 'border-2 border-mint bg-mint text-forest' },
  partial: { label: 'Partial', Icon: CircleDashed, className: 'border-2 border-dashed border-line bg-cream-deep text-forest' },
};

export function StatusBadge({ classification }: { classification: Classification }) {
  const { label, Icon, className } = config[classification];

  return (
    <span className={`inline-flex items-center gap-2 rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.12em] ${className}`}>
      <Icon size={14} aria-hidden="true" className={classification === 'partial' ? 'partial-status-icon' : undefined} />
      {label}
    </span>
  );
}
