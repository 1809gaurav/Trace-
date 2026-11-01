import { motion } from 'framer-motion';
import { ArrowLeft, Clock3 } from 'lucide-react';
import { useEffect, useMemo, useState, useSyncExternalStore } from 'react';
import { useNavigate } from 'react-router-dom';
import { createRecoveryStream, fetchResults, getDemoDataMode, subscribeDemoDataMode } from '../api/client';
import type { RecoveryMessage } from '../api/types';

const stops = [
  'Look at the drive',
  'Find deleted files',
  'Dig through raw data',
  'Piece fragments together',
  'Check and label',
];

export function RunPage() {
  const navigate = useNavigate();
  const [status, setStatus] = useState<RecoveryMessage>({
    status: 'reading',
    found: 0,
    message: 'Looking at the drive and checking the write history.',
  });
  const [files, setFiles] = useState<NonNullable<RecoveryMessage['file']>[]>([]);
  const [loadError, setLoadError] = useState('');
  const synthetic = useSyncExternalStore(subscribeDemoDataMode, getDemoDataMode, getDemoDataMode);

  useEffect(() => {
    const socket = createRecoveryStream();
    const refreshLiveFiles = () => {
      void fetchResults()
        .then((recovered) => {
          setFiles(recovered.map(({ id, name, type, classification, confidence }) => ({
            id,
            name,
            type,
            classification,
            confidence,
          })));
        })
        .catch(() => setLoadError('Recovered file cards could not be loaded.'));
    };
    const refreshTimer = window.setInterval(refreshLiveFiles, 1000);
    const handleMessage = (event: Event) => {
      const message = (event as CustomEvent<RecoveryMessage>).detail as RecoveryMessage;
      setStatus(message);
      const file = message.file;
      if (file) {
        setFiles((current) => [
          ...current.filter((item) => item.id !== file.id),
          file,
        ]);
      } else if (message.status === 'done' || message.fileIds?.length) {
        void fetchResults()
          .then((recovered) => {
            setFiles(recovered
              .filter((file) => message.status === 'done' || message.fileIds?.includes(file.id))
              .map(({ id, name, type, classification, confidence }) => ({
                id,
                name,
                type,
                classification,
                confidence,
              })));
          })
          .catch(() => setLoadError('Recovered file cards could not be loaded.'));
      }

      if (message.status === 'done') {
        window.setTimeout(() => navigate('/results'), 1100);
      }
    };
    const handleError = () => setLoadError('The recovery run could not be started or continued.');
    socket.addEventListener('message', handleMessage);
    socket.addEventListener('error', handleError);

    return () => {
      window.clearInterval(refreshTimer);
      socket.removeEventListener('message', handleMessage);
      socket.removeEventListener('error', handleError);
      socket.close();
    };
  }, [navigate]);

  const currentStop = useMemo(() => {
    const map = {
      reading: 0,
      scanning: 1,
      isolating: 2,
      reconstructing: 3,
      verifying: 4,
      done: 4,
    };
    return map[status.status] ?? 0;
  }, [status.status]);

  return (
    <div className="py-8">
      <div className="mb-6 flex items-center justify-between gap-4">
        <div>
          <p className="text-[11px] uppercase tracking-[0.15em] text-muted">Recovery in progress</p>
          <h1 className="mt-2 text-4xl text-forest">Checking the drive and piecing it back together</h1>
        </div>
        <button
          type="button"
          className="inline-flex items-center gap-2 rounded-full border border-line bg-cream px-4 py-2 text-sm font-medium text-forest focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-forest focus-visible:ring-offset-2 focus-visible:ring-offset-cream"
          onClick={() => navigate('/')}
        >
          <ArrowLeft size={16} />
          Cancel
        </button>
      </div>

      <section className="rounded-[24px] border border-line bg-cream-deep p-5 shadow-paper">
        <div className="grid gap-4 md:grid-cols-5">
          {stops.map((stop, index) => (
            <div key={stop} className="relative flex flex-col items-center text-center">
              <div className="relative mb-3 flex h-12 w-12 items-center justify-center rounded-full border-2 border-line bg-cream text-sm font-semibold text-forest">
                {index + 1}
                {index <= currentStop ? <motion.div layout className="absolute inset-0 rounded-full leaf-wash-20" /> : null}
              </div>
              <div className={`${index <= currentStop ? 'text-forest' : 'text-muted'} text-sm`}>{stop}</div>
            </div>
          ))}
        </div>
      </section>

      <section className="mt-6 grid gap-5 lg:grid-cols-[1.1fr_0.9fr]">
        <div className="rounded-[24px] border border-line bg-cream-deep p-5">
          <div className="mb-4 flex items-center justify-between gap-4">
            <div className="text-sm font-medium text-muted">Live feed</div>
            <div className="inline-flex items-center gap-2 rounded-full border border-line bg-cream px-3 py-1.5 text-xs font-medium uppercase tracking-[0.12em] text-forest">
              <Clock3 size={14} />
              Est. 12 seconds
            </div>
          </div>
          <p className="text-xl text-forest" aria-live="polite">
            {synthetic
              ? `Synthetic sample run — no evidence recovery was performed. ${status.message}`
              : `Found ${status.found} deleted files. ${status.message}`}
          </p>
          {status.percent !== undefined ? (
            <progress className="mt-4 h-2 w-full accent-forest" max={100} value={status.percent}>
              {status.percent}%
            </progress>
          ) : null}
          {loadError ? <p className="notice-error mt-3 rounded-xl p-3 text-sm" role="alert">{loadError}</p> : null}
          <div className="mt-5 space-y-3">
            {files.length === 0 ? (
              <div className="rounded-[16px] border border-line bg-cream p-4 text-sm text-muted">Scanning the image for recoverable files…</div>
            ) : (
              files.map((file) => (
                <div key={file.id} className="flex items-center justify-between rounded-[14px] border border-line bg-cream p-3">
                  <div>
                    <div className="text-sm font-semibold text-forest">{file.name}</div>
                    <div className="text-xs uppercase tracking-[0.12em] text-muted">{file.classification} · {file.type}</div>
                  </div>
                  {synthetic ? (
                    <span className="text-xs font-medium text-muted">Synthetic</span>
                  ) : (
                    <div className="rounded-full border border-line leaf-wash px-2.5 py-1 text-xs font-semibold uppercase tracking-[0.12em] text-forest">
                      {Math.round(file.confidence * 100)}%
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        </div>

        <div className="rounded-[24px] border border-line bg-cream p-5">
          <h2 className="text-xl font-semibold text-forest">What we are checking</h2>
          <ul className="mt-4 space-y-3 text-base text-muted">
            <li>• File headers and signatures</li>
            <li>• Deleted clusters and file fragments</li>
            <li>• Metadata and checksum gaps</li>
            <li>• Reconstructed image integrity</li>
          </ul>
          <div className="mt-6 rounded-[18px] border border-line bg-cream-deep p-4">
            <div className="text-[11px] uppercase tracking-[0.12em] text-muted">Status</div>
            <div className="mt-2 text-lg font-semibold text-forest">{status.status}</div>
          </div>
        </div>
      </section>
    </div>
  );
}
