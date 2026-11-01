import { AnimatePresence, motion } from 'framer-motion';
import { X, Copy, Eye, EyeOff } from 'lucide-react';
import { useEffect, useState } from 'react';
import type { RecoveredFile } from '../api/types';
import { BeforeAfterSlider } from './BeforeAfterSlider';
import { StatusBadge } from './StatusBadge';
import { ConfidenceMeter } from './ConfidenceMeter';

export function FileDrawer({
  file,
  isOpen,
  onClose,
}: {
  file: RecoveredFile | null;
  isOpen: boolean;
  onClose: () => void;
}) {
  const [showOriginal, setShowOriginal] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!isOpen) return undefined;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  const handleCopy = async () => {
    if (!file) return;
    try {
      await navigator.clipboard.writeText(file.sha256);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1200);
    } catch {
      setCopied(false);
    }
  };

  return (
    <AnimatePresence>
      {isOpen && file ? (
        <motion.div
          className="fixed inset-0 z-40 drawer-backdrop backdrop-blur-[1px]"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
        >
          <motion.aside
            role="dialog"
            aria-modal="true"
            aria-label={`${file.name} details`}
            className="absolute right-0 top-0 h-full w-full max-w-[560px] overflow-y-auto border-l border-line bg-cream p-6 drawer-shadow"
            initial={{ x: 48, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: 48, opacity: 0 }}
            transition={{ duration: 0.2 }}
          >
            <div className="mb-4 flex items-center justify-between">
              <div>
                <p className="text-[11px] uppercase tracking-[0.16em] text-forest-card">Evidence preview</p>
                <h2 className="mt-1 text-2xl font-semibold leading-none text-forest">{file.name}</h2>
              </div>
              <button
                type="button"
                className="flex h-11 w-11 items-center justify-center rounded-full border border-line bg-cream-deep text-forest transition hover-leaf-wash focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-forest focus-visible:ring-offset-2 focus-visible:ring-offset-cream"
                onClick={onClose}
                aria-label="Close details panel"
              >
                <X size={18} />
              </button>
            </div>

            <div className="rounded-[20px] border border-line bg-cream-deep p-3">
              <div className="relative overflow-hidden rounded-[14px] border border-line evidence-preview-surface p-3">
                <div
                  className="flex h-56 items-center justify-center rounded-[10px] border border-line evidence-preview-visual text-2xl font-semibold text-forest"
                  style={{ filter: showOriginal ? 'none' : 'grayscale(1) sepia(0.35) brightness(0.72) contrast(1.15)' }}
                >
                  {file.name}
                </div>
                <button
                  type="button"
                  className="mt-3 inline-flex items-center gap-2 rounded-full border border-line bg-cream px-3 py-2 text-sm font-medium text-forest focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-forest focus-visible:ring-offset-2 focus-visible:ring-offset-cream"
                  onClick={() => setShowOriginal((current) => !current)}
                >
                  {showOriginal ? <EyeOff size={16} /> : <Eye size={16} />}
                  {showOriginal ? 'Hide original' : 'Show original'}
                </button>
              </div>
            </div>

            <div className="mt-5 flex items-center justify-between gap-3">
              <StatusBadge classification={file.classification} />
              <button
                type="button"
                onClick={handleCopy}
                className="inline-flex items-center gap-2 rounded-full border border-line bg-cream px-3 py-2 text-sm font-medium text-forest focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-forest focus-visible:ring-offset-2 focus-visible:ring-offset-cream"
              >
                <Copy size={14} />
                {copied ? 'Copied' : 'Copy hash'}
              </button>
            </div>

            <div className="mt-5 rounded-[18px] border border-line bg-cream-deep p-4">
              <h3 className="text-sm font-semibold uppercase tracking-[0.14em] text-forest-card">Why this result</h3>
              <p className="mt-3 text-base leading-relaxed text-forest">{file.reason}</p>
            </div>

            {file.type === 'jpeg' || file.type === 'png' ? (
              <div className="mt-5">
                <BeforeAfterSlider />
              </div>
            ) : null}

            <div className="mt-5">
              <ConfidenceMeter value={file.confidence} />
            </div>

            <div className="mt-6 rounded-[18px] border border-line bg-cream p-4">
              <h3 className="text-sm font-semibold uppercase tracking-[0.14em] text-forest-card">Technical details</h3>
              <dl className="mt-4 space-y-3 text-sm text-forest">
                <div className="flex justify-between gap-4">
                  <dt className="text-muted">Stage</dt>
                  <dd>{file.stage}</dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt className="text-muted">Size</dt>
                  <dd>{file.sizeBytes.toLocaleString()} bytes</dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt className="text-muted">SHA-256</dt>
                  <dd className="break-all text-right font-mono text-[11px]">{file.sha256}</dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt className="text-muted">Offsets</dt>
                  <dd>{file.offsets.map((offset) => `${offset.start}-${offset.end}`).join(', ')}</dd>
                </div>
              </dl>
              <div className="mt-4 rounded-[10px] border border-line bg-cream-deep p-3 font-mono text-[11px] leading-6 text-forest">
                52 48 43 52 20 2d 7... 0a 20 20 20 20 20
              </div>
            </div>
          </motion.aside>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
