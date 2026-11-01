import { FileImage, FileText, Film, HardDrive, Search } from 'lucide-react';
import { motion } from 'framer-motion';
import type { RecoveredFile } from '../api/types';
import { ConfidenceMeter } from './ConfidenceMeter';
import { RecoveredPreview } from './RecoveredPreview';
import { StatusBadge } from './StatusBadge';

const fileIconMap = {
  jpeg: FileImage,
  png: FileImage,
  pdf: FileText,
  mp4: Film,
  dvr: HardDrive,
} as const;

export function FileCard({
  file,
  onSelect,
  synthetic = false,
}: {
  file: RecoveredFile;
  onSelect: (file: RecoveredFile) => void;
  synthetic?: boolean;
}) {
  const Icon = fileIconMap[file.type];
  return (
    <motion.button
      type="button"
      whileHover={{ y: -2 }}
      onClick={() => onSelect(file)}
      className="file-card interactive relative w-full overflow-hidden rounded-[20px] border border-line bg-cream-deep p-4 text-left shadow-paper transition-colors hover-leaf-wash focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-forest focus-visible:ring-offset-2 focus-visible:ring-offset-cream"
      onMouseMove={(event) => {
        const rect = event.currentTarget.getBoundingClientRect();
        const x = (event.clientX - (rect.left + rect.width / 2)) / rect.width;
        const y = (event.clientY - (rect.top + rect.height / 2)) / rect.height;
        event.currentTarget.style.transform = `perspective(1000px) rotateX(${y * 2}deg) rotateY(${x * 2}deg)`;
      }}
      onMouseLeave={(event) => {
        event.currentTarget.style.transform = 'none';
      }}
    >
      <div className="mb-4 flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-[12px] border border-line bg-cream text-forest">
            <Icon size={22} aria-hidden="true" />
          </div>
          <div>
            <div className="text-sm font-semibold text-forest">{file.name}</div>
            <div className="text-[11px] uppercase tracking-[0.14em] text-muted">{file.type}</div>
          </div>
        </div>
        <StatusBadge classification={file.classification} />
      </div>

      <div className="mt-3 rounded-[12px] border border-line bg-cream p-3 text-[13px] text-muted">
        <div className="mb-3 flex items-center justify-between">
          <span className="uppercase tracking-[0.12em] text-muted">Preview</span>
          <Search size={16} aria-hidden="true" />
        </div>
        {synthetic ? (
          <div className="flex h-20 items-center justify-center rounded-[8px] border border-line bg-cream-deep text-sm font-medium text-muted">
            Synthetic sample — no image content
          </div>
        ) : file.type === 'jpeg' || file.type === 'png' ? (
          <RecoveredPreview key={file.id} fileId={file.id} fileName={file.name} compact />
        ) : (
          <div className="flex h-20 items-center justify-center rounded-[8px] border border-line bg-cream text-sm text-muted">
            No inline image preview for this file type
          </div>
        )}
      </div>

      {synthetic ? (
        <p className="mt-4 text-sm font-medium text-muted">Synthetic sample — confidence unavailable</p>
      ) : (
        <div className="mt-4">
          <ConfidenceMeter value={file.confidence} />
        </div>
      )}

      <p className="mt-3 text-sm leading-relaxed text-muted">{file.reason}</p>
    </motion.button>
  );
}
