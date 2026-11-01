import { motion } from 'framer-motion';
import { ArrowLeft, Clock3 } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { createRecoveryStream, fetchResults } from '../api/client';
import type { RecoveredFile, RecoveryMessage } from '../api/types';

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
    found: 2,
    message: 'Looking at the drive and checking the write history.',
  });
  const [files, setFiles] = useState<RecoveredFile[]>([]);

  useEffect(() => {
    const socket = createRecoveryStream();
    socket.addEventListener('message', async (event: Event) => {
      const message = (event as CustomEvent<RecoveryMessage>).detail as RecoveryMessage;
      setStatus(message);
      const recovered = await fetchResults();
      setFiles(recovered.slice(0, message.found ?? 0));

      if (message.status === 'done') {
        window.setTimeout(() => navigate('/results'), 1100);
      }
    });

    return () => {
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
          <p className="text-[11px] uppercase tracking-[0.15em] text-forest-card">Recovery in progress</p>
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
            Found {status.found} deleted files. {status.message}
          </p>
          <div className="mt-5 space-y-3">
            {files.length === 0 ? (
              <div className="rounded-[16px] border border-line bg-cream p-4 text-sm text-muted">Scanning the image for recoverable files…</div>
            ) : (
              files.map((file) => (
                <div key={file.id} className="flex items-center justify-between rounded-[14px] border border-line bg-cream p-3">
                  <div>
                    <div className="text-sm font-semibold text-forest">{file.name}</div>
                    <div className="text-xs uppercase tracking-[0.12em] text-forest-card">{file.stage}</div>
                  </div>
                  <div className="rounded-full border border-line leaf-wash px-2.5 py-1 text-xs font-semibold uppercase tracking-[0.12em] text-forest">
                    {Math.round(file.confidence * 100)}%
                  </div>
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
            <div className="text-[11px] uppercase tracking-[0.12em] text-forest-card">Status</div>
            <div className="mt-2 text-lg font-semibold text-forest">{status.status}</div>
          </div>
        </div>
      </section>
    </div>
  );
}
