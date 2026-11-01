import { AlertTriangle, CheckCircle2, ShieldAlert, RotateCcw } from 'lucide-react';
import { motion } from 'framer-motion';
import type { CustodyEntry } from '../api/types';

export function ChainTimeline({
  entries,
  tamperedIndex,
  verified,
  onCheck,
  onTamper,
  onRestore,
}: {
  entries: CustodyEntry[];
  tamperedIndex: number | null;
  verified: boolean;
  onCheck: () => void;
  onTamper: () => void;
  onRestore: () => void;
}) {
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-3">
        <button
          type="button"
          onClick={onCheck}
          className="inline-flex min-h-11 items-center gap-2 rounded-full border-2 border-forest bg-transparent px-4 py-2 text-sm font-medium text-forest focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-forest focus-visible:ring-offset-2 focus-visible:ring-offset-cream"
        >
          <CheckCircle2 size={16} />
          Check the chain
        </button>
        <button
          type="button"
          onClick={onTamper}
          className="inline-flex items-center gap-2 rounded-full border-2 border-forest bg-transparent px-4 py-2 text-sm font-medium text-forest focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-forest focus-visible:ring-offset-2 focus-visible:ring-offset-cream"
        >
          <ShieldAlert size={16} />
          Try a tamper test
        </button>
        <button
          type="button"
          onClick={onRestore}
          className="inline-flex items-center gap-2 rounded-full border-2 border-forest bg-transparent px-4 py-2 text-sm font-medium text-forest focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-forest focus-visible:ring-offset-2 focus-visible:ring-offset-cream"
        >
          <RotateCcw size={16} />
          Restore
        </button>
      </div>

      <div className="relative pl-6">
        <div className="timeline-line absolute left-[18px] top-0 h-full w-[2px]" aria-hidden="true" />
        {entries.map((entry, index) => {
          const isBroken = tamperedIndex !== null && index + 1 >= tamperedIndex;
          const isVerified = verified && index <= entries.length - 1;
          const detailText = typeof entry.details.step === 'string' ? entry.details.step : 'Chain check on evidence integrity.';

          return (
            <motion.div
              key={entry.index}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.06 }}
              className={`relative mb-5 rounded-[20px] border border-line bg-cream-deep p-4 ${isBroken ? 'integrity-failed' : isVerified ? 'integrity-verified' : ''}`}
            >
              <div className={`absolute -left-[19px] top-7 flex h-8 w-8 items-center justify-center rounded-full border bg-cream text-forest shadow-marker ${isBroken ? 'border-forest' : isVerified ? 'border-leaf bg-leaf text-on-dark' : 'border-line'}`}>
                {isBroken ? <AlertTriangle size={14} className="text-forest" aria-hidden="true" /> : isVerified ? <CheckCircle2 size={14} className="text-on-dark" aria-hidden="true" /> : <div className="h-2 w-2 rounded-full bg-leaf" />}
              </div>
              <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
                <div>
                  <p className="text-[11px] uppercase tracking-[0.14em] text-forest-card">Seal {entry.index}</p>
                  <h2 className="mt-1 text-lg font-semibold text-forest">{entry.step}</h2>
                </div>
                <time className="text-sm text-muted">{entry.time}</time>
              </div>
              <p className="mt-3 text-sm leading-relaxed text-muted">{detailText}</p>
              <details className="mt-3 rounded-[12px] border border-line bg-cream p-3 text-sm text-forest">
                <summary className="cursor-pointer list-none font-medium">Show technical hash</summary>
                <div className="mt-3 space-y-2 font-mono text-[11px] leading-6 text-forest">
                  <div>PrevHash: {entry.prevHash}</div>
                  <div>Hash: {entry.hash}</div>
                </div>
              </details>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}
