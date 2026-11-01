import { AlertTriangle, ShieldCheck } from 'lucide-react';
import { useEffect, useState } from 'react';
import { fetchCustodyEntries, verifyChain } from '../api/client';
import type { CustodyEntry } from '../api/types';
import { ChainTimeline } from '../components/ChainTimeline';

export function CustodyPage() {
  const [entries, setEntries] = useState<CustodyEntry[]>([]);
  const [tamperedIndex, setTamperedIndex] = useState<number | null>(null);
  const [verified, setVerified] = useState(false);
  const [message, setMessage] = useState('The seal chain is intact and ready for review.');

  useEffect(() => {
    void fetchCustodyEntries().then(setEntries);
  }, []);

  const handleCheck = async () => {
    const result = await verifyChain(entries);
    setVerified(result.valid);
    if (result.valid) {
      setMessage('All seals are still in sequence. Nothing in the chain has moved.');
    } else {
      setMessage(`Entry ${result.brokenIndex ?? 'n/a'} was changed. Everything after it can no longer be trusted.`);
    }
  };

  const handleTamper = () => {
    const target = 3;
    setTamperedIndex(target);
    setVerified(false);
    setMessage('Entry 3 was changed. Everything after it can no longer be trusted.');
  };

  const handleRestore = () => {
    setTamperedIndex(null);
    setVerified(false);
    setMessage('The chain was restored. All entries are back in sequence.');
  };

  return (
    <div className="py-8">
      <div className="mb-6 flex items-center justify-between gap-4">
        <div>
          <p className="text-[11px] uppercase tracking-[0.15em] text-forest-card">Custody log</p>
          <h1 className="mt-2 text-4xl text-forest">Seal and proof trail</h1>
        </div>
      </div>

      <div className={`mb-6 rounded-[22px] border border-line bg-cream-deep p-4 ${tamperedIndex ? 'integrity-failed' : verified ? 'integrity-verified' : ''}`}>
        <div className="flex items-start gap-3">
          {tamperedIndex ? (
            <AlertTriangle className="mt-1 text-forest" size={22} aria-hidden="true" />
          ) : (
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-leaf text-on-dark">
              <ShieldCheck size={18} aria-hidden="true" />
            </div>
          )}
          <div>
            <div className="text-[11px] uppercase tracking-[0.14em] text-forest-card">Chain status</div>
            <p className="mt-2 text-lg text-forest" role="alert">
              {message}
            </p>
          </div>
        </div>
      </div>

      <ChainTimeline
        entries={entries}
        tamperedIndex={tamperedIndex}
        verified={verified}
        onCheck={handleCheck}
        onTamper={handleTamper}
        onRestore={handleRestore}
      />
    </div>
  );
}
