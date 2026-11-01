import { Search, SlidersHorizontal } from 'lucide-react';
import { useEffect, useMemo, useState, useSyncExternalStore } from 'react';
import { fetchResults, fetchScore, getDemoDataMode, subscribeDemoDataMode } from '../api/client';
import type { RecoveredFile, Score } from '../api/types';
import { FileCard } from '../components/FileCard';
import { FileDrawer } from '../components/FileDrawer';

const statuses = ['all', 'intact', 'carved', 'reconstructed', 'partial'] as const;

export function ResultsPage() {
  const [files, setFiles] = useState<RecoveredFile[]>([]);
  const [score, setScore] = useState<Score | null>(null);
  const [selectedFile, setSelectedFile] = useState<RecoveredFile | null>(null);
  const [query, setQuery] = useState('');
  const [activeStatus, setActiveStatus] = useState<(typeof statuses)[number]>('all');
  const demoData = useSyncExternalStore(subscribeDemoDataMode, getDemoDataMode, getDemoDataMode);
  const [loadError, setLoadError] = useState('');
  const unavailableLabel = demoData ? 'Not scored for synthetic runs' : 'Benchmark unavailable';

  useEffect(() => {
    let active = true;
    void fetchResults()
      .then((items) => {
        if (active) setFiles(items);
      })
      .catch(() => {
        if (active) setLoadError('Results could not be loaded. Please try again.');
      });
    void fetchScore()
      .then((value) => {
        if (active) setScore(value);
      })
      .catch(() => {
        if (active) setLoadError('The score could not be loaded. Please try again.');
      });
    return () => {
      active = false;
    };
  }, []);

  const filteredFiles = useMemo(() => {
    const lowerQuery = query.trim().toLowerCase();
    return files
      .filter((file) => (activeStatus === 'all' ? true : file.classification === activeStatus))
      .filter((file) => (lowerQuery ? file.name.toLowerCase().includes(lowerQuery) : true))
      .sort((left, right) => (demoData ? left.name.localeCompare(right.name) : right.confidence - left.confidence));
  }, [activeStatus, demoData, files, query]);

  const summaryItems = [
    {
      label: 'Found',
      value: score?.benchmarkUnavailable ? unavailableLabel : `${score?.recovered ?? 0} of ${score?.expected ?? 0} files`,
      detail: 'Recovered count compared with the benchmark expected count.',
    },
    {
      label: 'How accurate',
      value: score?.benchmarkUnavailable ? unavailableLabel : `${Math.round((score?.precision ?? 0) * 100)}%`,
      detail: 'Scorer precision for recovered files matched to benchmark ground truth.',
    },
    {
      label: 'How complete',
      value: score?.benchmarkUnavailable ? unavailableLabel : `${Math.round((score?.completeness ?? 0) * 100)}%`,
      detail: 'Scorer completeness compared with benchmark ground truth.',
    },
    {
      label: 'Recall',
      value: score?.benchmarkUnavailable ? unavailableLabel : `${Math.round((score?.recall ?? 0) * 100)}%`,
      detail: 'Expected files recovered, divided by all expected files.',
    },
    {
      label: 'Mistakes',
      value: score?.benchmarkUnavailable ? unavailableLabel : `${score?.falsePositives ?? 0} false positives`,
      detail: 'Recovered files that did not match benchmark ground truth.',
    },
    {
      label: 'False-positive rate',
      value: score?.benchmarkUnavailable ? unavailableLabel : `${Math.round((score?.falsePositiveRate ?? 0) * 100)}%`,
      detail: 'False positives divided by all recovered items.',
    },
    {
      label: 'Metadata accuracy',
      value: score?.benchmarkUnavailable ? unavailableLabel : `${Math.round((score?.metadataAccuracy ?? 0) * 100)}%`,
      detail: 'Ground-truth metadata fields that matched the recovery output.',
    },
    {
      label: 'Classification accuracy',
      value: score?.benchmarkUnavailable ? unavailableLabel : `${Math.round((score?.classificationAccuracy ?? 0) * 100)}%`,
      detail: 'Matched files assigned an accepted classification.',
    },
    {
      label: 'Image integrity',
      value: score?.benchmarkUnavailable ? unavailableLabel : score?.imageIntegrityOk ? 'Passed' : 'Failed',
      detail: 'Whether the scorer confirmed the source image hash.',
    },
    {
      label: 'Overconfident errors',
      value: score?.benchmarkUnavailable ? unavailableLabel : `${score?.overconfidentErrors ?? 0}`,
      detail: 'Incorrect matches above the scorer confidence threshold.',
    },
  ];

  return (
    <div className="py-8">
      <div className="mb-6">
        <p className="text-[11px] uppercase tracking-[0.15em] text-muted">
          Results
          {demoData ? <span className="demo-pill results-demo-pill">SYNTHETIC</span> : null}
        </p>
        <h1 className="mt-2 text-4xl text-forest">Recovered evidence review</h1>
      </div>

      <div className="mb-6 grid gap-4 md:grid-cols-4">
        {summaryItems.map((item) => (
          <div key={item.label} className="rounded-[18px] border border-line bg-cream-deep p-4" title={item.detail}>
            <div className="text-[11px] uppercase tracking-[0.15em] text-muted">{item.label}</div>
            <div className={`mt-2 font-semibold text-forest ${score?.benchmarkUnavailable ? 'score-unavailable' : 'text-2xl'}`} aria-live="polite">
              {item.value}
            </div>
          </div>
        ))}
      </div>

      {loadError ? <p role="alert" className="notice-error mb-5 rounded-2xl border bg-cream-deep p-4 text-forest">{loadError}</p> : null}
      {score && !score.benchmarkUnavailable ? (
        <section className="mb-6 rounded-[22px] border border-line bg-cream-deep p-4" aria-labelledby="calibration-heading">
          <h2 id="calibration-heading" className="text-lg font-semibold text-forest">Confidence calibration</h2>
          <p className="mt-1 text-sm text-muted">Observed correct-item rate by scorer confidence range.</p>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            {score.calibration.map((bucket) => (
              <div key={`${bucket.lower}-${bucket.upper}`} className="rounded-xl border border-line bg-cream p-3">
                <div className="text-xs font-medium text-muted">{Math.round(bucket.lower * 100)}–{Math.round(bucket.upper * 100)}%</div>
                <div className="mt-1 text-lg font-semibold text-forest">
                  {bucket.correctRate === null ? '—' : `${Math.round(bucket.correctRate * 100)}%`}
                </div>
                <div className="text-xs text-muted">{bucket.count} results</div>
              </div>
            ))}
          </div>
        </section>
      ) : null}
      {score && !score.benchmarkUnavailable ? (
        <section className="mb-6 rounded-[22px] border border-line bg-cream-deep p-4" aria-labelledby="per-file-score-heading">
          <h2 id="per-file-score-heading" className="text-lg font-semibold text-forest">Ground-truth file results</h2>
          <div className="mt-4 divide-y divide-line">
            {score.perFile.map((item) => (
              <div key={item.groundTruthId} className="grid gap-2 py-3 text-sm sm:grid-cols-5 sm:items-center">
                <span className="font-medium text-forest">{item.name}</span>
                <span className="text-muted">Status: {item.status}</span>
                <span className="text-muted">Completeness: {Math.round(item.completeness * 100)}%</span>
                <span className="text-muted">
                  Classification: {item.classificationGot ?? 'Not recovered'} (expected {item.classificationExpected})
                </span>
                <span className="text-muted">
                  Confidence: {item.confidence === null ? '—' : `${Math.round(item.confidence * 100)}%`}
                </span>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      <div className="mb-6 flex flex-col gap-4 rounded-[22px] border border-line bg-cream-deep p-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-wrap gap-2">
          {statuses.map((status) => (
            <button
              key={status}
              type="button"
              onClick={() => setActiveStatus(status)}
              className={`rounded-full border px-4 py-2 text-sm font-medium focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-forest focus-visible:ring-offset-2 focus-visible:ring-offset-cream ${
                activeStatus === status
                  ? 'border-line bg-cream-deep text-forest'
                  : 'border-line bg-cream-deep text-forest'
              }`}
            >
              {status === 'all' ? 'All' : status}
            </button>
          ))}
        </div>

        <label className="flex min-w-[220px] items-center gap-3 rounded-full border border-line bg-cream px-3 py-2 text-forest">
          <Search size={18} />
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            className="w-full bg-transparent text-sm placeholder:text-muted focus:outline-none"
            placeholder="Search recovered files"
            aria-label="Search recovered files"
          />
        </label>
      </div>

      <div className="mb-4 flex items-center gap-2 text-sm text-muted">
        <SlidersHorizontal size={16} />
        {demoData ? 'Synthetic samples sorted by name' : 'Sorted by confidence'}
      </div>

      <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
        {filteredFiles.map((file) => (
          <FileCard key={file.id} file={file} onSelect={setSelectedFile} synthetic={demoData} />
        ))}
      </div>

      {filteredFiles.length === 0 ? (
        <div className="mt-6 rounded-[20px] border border-line bg-cream-deep p-6 text-center text-muted">
          No files match that search yet. Try a broader term or different filter.
        </div>
      ) : null}

      <FileDrawer
        key={selectedFile?.id ?? 'empty'}
        file={selectedFile}
        isOpen={Boolean(selectedFile)}
        onClose={() => setSelectedFile(null)}
        synthetic={demoData}
      />
    </div>
  );
}
