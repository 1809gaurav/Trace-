import { AlertTriangle, ArrowRight, Check, Copy, FileUp, ShieldCheck, Sparkles } from 'lucide-react';
import { useRef, useState } from 'react';
import type { SyntheticEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { uploadEvidence } from '../api/client';
import { ShardBackground } from '../components/ShardBackground';
import { MagneticButton } from '../components/MagneticButton';

interface EvidenceState {
  name: string;
  sizeBytes: number;
  fingerprint: string;
}

export function HomePage({ playfulMotionEnabled }: { playfulMotionEnabled: boolean }) {
  const navigate = useNavigate();
  const [isDragging, setIsDragging] = useState(false);
  const [evidence, setEvidence] = useState<EvidenceState | null>(null);
  const [showFullFingerprint, setShowFullFingerprint] = useState(false);
  const [uploadError, setUploadError] = useState('');
  const inputRef = useRef<HTMLInputElement | null>(null);

  const handleFile = async (file: File | null) => {
    if (!file) return;
    setUploadError('');
    try {
      const result = await uploadEvidence(file);
      setEvidence({
        name: result.fileName,
        sizeBytes: result.sizeBytes,
        fingerprint: result.fingerprint,
      });
    } catch {
      setUploadError('We could not prepare this image. Please try selecting it again.');
    }
  };

  const stopShardGesture = (event: SyntheticEvent) => event.stopPropagation();

  return (
    <div className="home-page">
      <section className="home-hero">
        <ShardBackground playfulMotionEnabled={playfulMotionEnabled} />
        <div className="hero-copy-scrim" aria-hidden="true" />
        <div className="hero-content">
          <div className="hero-intro">
            <p className="text-[11px] uppercase tracking-[0.18em] text-forest-card">A calmer way to recover evidence</p>
            <h1 className="mt-3 max-w-2xl text-5xl leading-[1.05] text-forest md:text-6xl">
              Get the evidence back. Keep the proof.
            </h1>
            <p className="mt-5 max-w-xl text-lg leading-relaxed text-muted">
              Recover the files that matter most from damaged CCTV and DVR drives without losing the chain of custody.
            </p>
          </div>

          <div className="hero-evidence-card home-glass-panel">
            <div className="mb-3 flex items-center gap-3 text-forest">
              <div className="flex h-10 w-10 items-center justify-center rounded-full border border-line bg-cream-deep">
                <ShieldCheck size={18} aria-hidden="true" />
              </div>
              <div>
                <div className="text-[11px] uppercase tracking-[0.15em] text-forest-card">Evidence lock</div>
                <div className="font-semibold">Managed in a sealed chain</div>
              </div>
            </div>
            <div className="space-y-2 text-sm text-muted">
              <p>Evidence locked, nothing can change it.</p>
              <p>Found 13 of 15 files on the previous review.</p>
            </div>
          </div>

          <section
            className={`upload-zone home-glass-panel interactive ${isDragging ? 'is-dragging' : ''}`}
            role="region"
            tabIndex={0}
            aria-label="Add a disk image"
            aria-keyshortcuts="Enter Space"
            onPointerDown={stopShardGesture}
            onClick={stopShardGesture}
            onKeyDown={(event) => {
              if (event.target === event.currentTarget && (event.key === 'Enter' || event.key === ' ')) {
                event.preventDefault();
                inputRef.current?.click();
              }
            }}
            onDragOver={(event) => {
              event.preventDefault();
              setIsDragging(true);
            }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={(event) => {
              event.preventDefault();
              setIsDragging(false);
              const file = event.dataTransfer.files[0];
              void handleFile(file);
            }}
          >
            <div className="flex flex-col gap-6 md:flex-row md:items-center md:justify-between">
              <div className="flex items-center gap-4">
                <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full border border-line bg-cream-deep text-forest">
                  <FileUp size={25} aria-hidden="true" />
                </div>
                <div>
                  <h2 className="text-2xl font-semibold text-forest">Add a disk image</h2>
                  <p className="text-base text-muted">Drag and drop a CCTV or DVR image. Or choose from storage.</p>
                </div>
              </div>

              <button
                type="button"
                className="min-h-11 rounded-full border-2 border-leaf bg-leaf px-5 py-3 text-sm font-semibold text-on-dark transition hover:bg-leaf focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-mint focus-visible:ring-offset-2 focus-visible:ring-offset-cream"
                onPointerDown={stopShardGesture}
                onClick={() => inputRef.current?.click()}
              >
                Select disk image
              </button>
              <input
                ref={inputRef}
                type="file"
                accept=".img,.dd,.raw,.dmg,.e01,.iso,.001,image/*"
                className="sr-only"
                aria-label="Select a disk image"
                onChange={(event) => {
                  const file = event.target.files?.[0] ?? null;
                  void handleFile(file);
                }}
              />
            </div>

            {uploadError ? (
              <p role="alert" className="integrity-failed mt-4 flex items-center gap-2 text-sm text-forest">
                <AlertTriangle size={16} aria-hidden="true" />
                <span>{uploadError}</span>
              </p>
            ) : null}
            {evidence ? (
              <div className="mt-5 rounded-[18px] border border-line bg-cream-deep p-4">
                <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                  <div>
                    <p className="text-[11px] uppercase tracking-[0.12em] text-forest-card">Evidence locked</p>
                    <h3 className="mt-1 text-xl font-semibold text-forest">{evidence.name}</h3>
                  </div>
                  <div className="flex items-center gap-3 rounded-full border border-line bg-cream-deep px-3 py-2 text-sm text-forest">
                    <Check size={16} aria-hidden="true" />
                    <span>{(evidence.sizeBytes / 1024 / 1024).toFixed(1)} MB image</span>
                  </div>
                </div>
                <div className="mt-4 flex flex-col gap-3 rounded-[14px] border border-line bg-cream-deep p-3 md:flex-row md:items-center md:justify-between">
                  <div>
                    <div className="text-[11px] uppercase tracking-[0.12em] text-forest-card">Fingerprint</div>
                    <div className="mt-1 font-mono text-xs text-forest">
                      {showFullFingerprint ? evidence.fingerprint : evidence.fingerprint.slice(0, 12)}
                    </div>
                    <button
                      type="button"
                      className="mt-2 min-h-11 text-sm text-forest underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-forest focus-visible:ring-offset-2 focus-visible:ring-offset-cream"
                      onPointerDown={stopShardGesture}
                      onClick={() => setShowFullFingerprint((current) => !current)}
                    >
                      {showFullFingerprint ? 'Hide full fingerprint' : 'Show full fingerprint'}
                    </button>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      className="inline-flex min-h-11 items-center gap-2 rounded-full border border-line bg-cream px-3 py-2 text-sm text-forest focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-forest focus-visible:ring-offset-2 focus-visible:ring-offset-cream"
                      onPointerDown={stopShardGesture}
                      onClick={() => void navigator.clipboard.writeText(evidence.fingerprint)}
                    >
                      <Copy size={14} aria-hidden="true" />
                      Copy
                    </button>
                    <button
                      type="button"
                      className="min-h-11 rounded-full border border-line bg-cream px-3 py-2 text-sm text-forest focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-forest focus-visible:ring-offset-2 focus-visible:ring-offset-cream"
                      onPointerDown={stopShardGesture}
                      onClick={() => setEvidence(null)}
                    >
                      Clear
                    </button>
                  </div>
                </div>
              </div>
            ) : null}
          </section>

          <div className="hero-start-button">
            <MagneticButton
              variant="secondary"
              className="min-h-11 px-6"
              type="button"
              disabled={!evidence}
              onPointerDown={stopShardGesture}
              onClick={(event) => {
                stopShardGesture(event);
                navigate('/run');
              }}
            >
              Start recovery
              <ArrowRight size={16} className="ml-2" aria-hidden="true" />
            </MagneticButton>
          </div>
        </div>
      </section>

      <section
        aria-label="How recovery works and what to expect"
        className="home-followup mx-auto max-w-6xl space-y-4 px-4 py-8 md:px-6"
      >
        <div className="grid gap-3 md:grid-cols-3">
          {[
            'Set a secure seal before the image is opened.',
            'Scan the drive for deleted and damaged files.',
            'Check the recovered set before it reaches the report.',
          ].map((step, index) => (
            <article key={step} className="home-glass-panel rounded-[18px] p-4">
              <div className="mb-2 flex items-center gap-2 text-forest">
                <span className="flex h-8 w-8 items-center justify-center rounded-full border border-line bg-cream-deep text-sm font-bold">{index + 1}</span>
                <span className="text-[11px] uppercase tracking-[0.14em]">What happens next</span>
              </div>
              <p className="text-sm leading-relaxed text-muted">{step}</p>
            </article>
          ))}
        </div>

        <div className="grid gap-3 md:grid-cols-3">
        {[
          {
            icon: <Sparkles size={18} aria-hidden="true" />,
            title: 'What we can find',
            text: 'Deleted images, fragments, and damaged records from CCTV and DVR evidence.',
          },
          {
            icon: <ShieldCheck size={18} aria-hidden="true" />,
            title: 'Why it is trusted',
            text: 'Every result is checked with a hash and a plain-language explanation for investigators.',
          },
          {
            icon: <FileUp size={18} aria-hidden="true" />,
            title: 'You can share it',
            text: 'Download a clean court-ready report when the review is complete.',
          },
        ].map((item) => (
          <article key={item.title} className="home-glass-panel rounded-[18px] p-4">
            <div className="text-forest">{item.icon}</div>
            <h2 className="mt-3 text-lg font-semibold text-forest">{item.title}</h2>
            <p className="mt-2 text-sm leading-relaxed text-muted">{item.text}</p>
          </article>
        ))}
        </div>
      </section>
    </div>
  );
}
