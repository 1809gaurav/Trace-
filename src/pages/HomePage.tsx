import { AlertTriangle, ArrowRight, Check, Copy, FileUp, ShieldCheck, Sparkles } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import type { SyntheticEvent } from 'react';
import { uploadEvidence } from '../api/client';
import { HomeRadar } from '../components/HomeRadar';
import { MagneticButton } from '../components/MagneticButton';

interface EvidenceState {
  name: string;
  sizeBytes: number;
  fingerprint: string;
}

export function HomePage({
  playfulMotionEnabled,
  highContrastEnabled,
}: {
  playfulMotionEnabled: boolean;
  highContrastEnabled: boolean;
}) {
  const navigate = useNavigate();
  const location = useLocation();
  const [isDragging, setIsDragging] = useState(false);
  const [evidence, setEvidence] = useState<EvidenceState | null>(null);
  const [showFullFingerprint, setShowFullFingerprint] = useState(false);
  const [uploadError, setUploadError] = useState('');
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (location.hash !== '#upload-zone') return;
    window.requestAnimationFrame(() => {
      const uploadZone = document.getElementById('upload-zone');
      uploadZone?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      uploadZone?.focus();
    });
  }, [location.hash]);

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

  const scrollToUpload = () => {
    const uploadZone = document.getElementById('upload-zone');
    uploadZone?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    uploadZone?.focus();
  };

  const stopGesture = (event: SyntheticEvent) => event.stopPropagation();

  return (
    <div className="home-page">
      <section className="home-hero" aria-labelledby="home-title">
        <HomeRadar
          playfulMotionEnabled={playfulMotionEnabled}
          highContrastEnabled={highContrastEnabled}
        />
        <div className="hero-copy-scrim" aria-hidden="true" />
        <div className="hero-content">
          <div className="hero-intro">
            <p className="hero-eyebrow">Evidence recovery that shows its proof</p>
            <h1 id="home-title" className="hero-title">
              Get the evidence back.
              <span>Keep the proof.</span>
            </h1>
            <p className="hero-description">
              Trace brings files back from damaged CCTV and disk images, and shows exactly how much to trust each one. Nothing on your drive is ever changed.
            </p>
            <div className="hero-actions">
              <button type="button" className="button-primary" onClick={scrollToUpload}>
                Start a case
                <ArrowRight size={17} className="ml-2" aria-hidden="true" />
              </button>
              <a className="button-secondary" href="#how-it-works">See how it works</a>
            </div>
          </div>

          <article className="hero-evidence-card sample-card" aria-label="Sample case summary">
            <span className="sample-chip">Sample</span>
            <p className="sample-kicker mt-4 text-[11px] font-bold uppercase tracking-[0.16em]">
              Your case at a glance
            </p>
            <div className="mt-4 flex items-start gap-4">
              <div className="sample-icon-tile" aria-hidden="true">
                <ShieldCheck size={25} />
              </div>
              <div>
                <h2 className="text-2xl font-bold leading-tight">Proof, file by file</h2>
                <p className="sample-subtitle mt-1 text-sm leading-relaxed">
                  Every recovered file carries its own record.
                </p>
              </div>
            </div>
            <div className="mt-5">
              <div className="sample-row">
                <span>Evidence locked</span>
                <strong className="inline-flex items-center gap-2"><Check size={15} aria-hidden="true" /> ON</strong>
              </div>
              <div className="sample-row">
                <span>Review focus</span>
                <strong>File by file</strong>
              </div>
              <div className="sample-row">
                <span>Results</span>
                <strong>Evidence-led</strong>
              </div>
            </div>
            <p className="sample-footer mt-4 text-xs">Nothing was changed on your drive</p>
            <span className="floating-chip floating-chip--top">Built to be questioned</span>
            <span className="floating-chip floating-chip--bottom">Review each hash</span>
          </article>
        </div>
      </section>

      <section className="upload-section" aria-label="Add evidence and see what happens next">
        <section
          id="upload-zone"
          className={`upload-zone home-glass-panel interactive ${isDragging ? 'is-dragging' : ''}`}
          role="region"
          tabIndex={0}
          aria-label="Add a disk image"
          aria-keyshortcuts="Enter Space"
          onPointerDown={stopGesture}
          onClick={stopGesture}
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
            void handleFile(event.dataTransfer.files[0] ?? null);
          }}
        >
          <div className="flex flex-col gap-6 md:flex-row md:items-center md:justify-between">
            <div className="flex items-center gap-4">
              <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full border border-line bg-cream text-forest">
                <FileUp size={25} aria-hidden="true" />
              </div>
              <div>
                <h2 className="text-2xl font-semibold text-forest">Add a disk image</h2>
                <p className="text-base text-muted">Choose an image. Trace will keep it read-only.</p>
              </div>
            </div>
            <button
              type="button"
              className="button-primary"
              onPointerDown={stopGesture}
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
                void handleFile(event.target.files?.[0] ?? null);
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
            <div className="mt-5 rounded-[20px] border border-line bg-cream p-4">
              <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                <div>
                  <p className="text-[11px] font-bold uppercase tracking-[0.12em] text-muted">Evidence locked</p>
                  <h3 className="mt-1 text-xl font-semibold text-forest">{evidence.name}</h3>
                </div>
                <div className="flex items-center gap-3 rounded-full border border-line bg-cream-deep px-3 py-2 text-sm text-forest">
                  <Check size={16} aria-hidden="true" />
                  <span>{(evidence.sizeBytes / 1024 / 1024).toFixed(1)} MB image</span>
                </div>
              </div>
              <div className="mt-4 flex flex-col gap-3 rounded-[16px] border border-line bg-cream-deep p-3 md:flex-row md:items-center md:justify-between">
                <div className="min-w-0">
                  <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-muted">Fingerprint</div>
                  <div className="mt-1 break-all font-mono text-xs text-forest">
                    {showFullFingerprint ? evidence.fingerprint : evidence.fingerprint.slice(0, 12)}
                  </div>
                  <button
                    type="button"
                    className="mt-2 min-h-11 text-sm text-forest underline-offset-4 hover:underline"
                    onPointerDown={stopGesture}
                    onClick={() => setShowFullFingerprint((current) => !current)}
                  >
                    {showFullFingerprint ? 'Hide full fingerprint' : 'Show full fingerprint'}
                  </button>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <button
                    type="button"
                    className="inline-flex min-h-11 items-center gap-2 border border-line bg-cream px-3 py-2 text-sm text-forest"
                    onPointerDown={stopGesture}
                    onClick={() => void navigator.clipboard.writeText(evidence.fingerprint)}
                  >
                    <Copy size={14} aria-hidden="true" />
                    Copy
                  </button>
                  <button
                    type="button"
                    className="min-h-11 border border-line bg-cream px-3 py-2 text-sm text-forest"
                    onPointerDown={stopGesture}
                    onClick={() => setEvidence(null)}
                  >
                    Clear
                  </button>
                </div>
              </div>
              <div className="mt-4 flex items-center gap-2 text-sm font-semibold text-forest">
                <ShieldCheck size={17} aria-hidden="true" />
                Evidence locked — Trace will not change your source image.
              </div>
            </div>
          ) : null}
        </section>

        <div className="mt-6">
          <p className="mb-3 text-[11px] font-bold uppercase tracking-[0.18em] text-forest">What happens next</p>
          <div id="how-it-works" className="next-steps-grid">
            {[
              'Seal the image before it is opened.',
              'Scan for deleted, damaged, and fragmented files.',
              'Review each result and its proof before reporting.',
            ].map((step, index) => (
              <article key={step} className="next-step">
                <div className="mb-2 flex items-center gap-3 text-forest">
                  <span className="flex h-9 w-9 items-center justify-center rounded-full border border-line bg-cream text-sm font-bold">
                    {index + 1}
                  </span>
                  <span className="text-sm font-bold">Step {index + 1}</span>
                </div>
                <p className="text-sm leading-relaxed text-muted">{step}</p>
              </article>
            ))}
          </div>
        </div>

        <div className="mt-6 grid gap-4 md:grid-cols-3">
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
            <article key={item.title} className="home-glass-panel p-5">
              <div className="text-forest">{item.icon}</div>
              <h2 className="mt-3 text-lg font-semibold text-forest">{item.title}</h2>
              <p className="mt-2 text-sm leading-relaxed text-muted">{item.text}</p>
            </article>
          ))}
        </div>
      </section>

      <div className="upload-section flex justify-end pb-8">
        <MagneticButton
          variant="primary"
          disabled={!evidence}
          onPointerDown={stopGesture}
          onClick={(event) => {
            stopGesture(event);
            navigate('/run');
          }}
        >
          Start recovery
          <ArrowRight size={16} className="ml-2" aria-hidden="true" />
        </MagneticButton>
      </div>
    </div>
  );
}
