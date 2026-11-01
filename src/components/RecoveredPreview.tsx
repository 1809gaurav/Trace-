import { useEffect, useState } from 'react';
import { fetchFilePreview } from '../api/client';

type PreviewState =
  | { status: 'loading' }
  | { status: 'ready'; url: string }
  | { status: 'unavailable' }
  | { status: 'error'; message: string };

export function RecoveredPreview({
  fileId,
  fileName,
  compact = false,
}: {
  fileId: string;
  fileName: string;
  compact?: boolean;
}) {
  const [preview, setPreview] = useState<PreviewState>({ status: 'loading' });

  useEffect(() => {
    let active = true;
    let objectUrl: string | null = null;
    void fetchFilePreview(fileId)
      .then((blob) => {
        if (!active) return;
        if (!blob) {
          setPreview({ status: 'unavailable' });
          return;
        }
        objectUrl = URL.createObjectURL(blob);
        setPreview({ status: 'ready', url: objectUrl });
      })
      .catch((error: unknown) => {
        if (active) {
          setPreview({
            status: 'error',
            message: error instanceof Error ? error.message : 'The recovered preview could not be loaded.',
          });
        }
      });
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [fileId]);

  const containerClass = compact
    ? 'flex h-20 items-center justify-center rounded-[8px] border border-line bg-cream'
    : 'flex min-h-20 items-center justify-center rounded-[14px] border border-line bg-cream';
  if (preview.status === 'ready') {
    return (
      <img
        src={preview.url}
        alt={`Recovered output ${fileName}`}
        className={`${compact ? 'h-20' : 'max-h-80'} w-full rounded-[14px] border border-line object-contain`}
      />
    );
  }
  if (preview.status === 'error') {
    return <p className="notice-error rounded-xl p-3 text-sm" role="alert">{preview.message}</p>;
  }
  if (preview.status === 'unavailable') {
    return <div className={`${containerClass} px-3 text-center text-sm text-muted`}>No inline preview is available.</div>;
  }
  return <div className={`${containerClass} px-3 text-center text-sm text-muted`} role="status">Loading recovered image preview…</div>;
}
