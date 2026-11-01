import { Search, SlidersHorizontal } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { fetchResults, fetchScore } from '../api/client';
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

  useEffect(() => {
    void fetchResults().then(setFiles);
    void fetchScore().then(setScore);
  }, []);

  const filteredFiles = useMemo(() => {
    const lowerQuery = query.trim().toLowerCase();
    return files
      .filter((file) => (activeStatus === 'all' ? true : file.classification === activeStatus))
      .filter((file) => (lowerQuery ? file.name.toLowerCase().includes(lowerQuery) : true))
      .sort((left, right) => right.confidence - left.confidence);
  }, [activeStatus, files, query]);

  const summaryItems = [
    {
      label: 'Found',
      value: `${score?.recovered ?? 0} of ${score?.expected ?? 0} files`,
      detail: 'The set includes the files that were still recoverable from the device.',
    },
    {
      label: 'How accurate',
      value: `${Math.round((score?.precision ?? 0) * 100)}%`,
      detail: 'Most of what was recovered is consistent with the original evidence.',
    },
    {
      label: 'How complete',
      value: `${Math.round((score?.completeness ?? 0) * 100)}%`,
      detail: 'Most of the expected evidence was found before the device was sealed.',
    },
    {
      label: 'Mistakes',
      value: `${score?.falsePositives ?? 0} false positives`,
      detail: 'Only one file was flagged for review after validation.',
    },
  ];

  return (
    <div className="py-8">
      <div className="mb-6">
        <p className="text-[11px] uppercase tracking-[0.15em] text-forest-card">Results</p>
        <h1 className="mt-2 text-4xl text-forest">Recovered evidence review</h1>
      </div>

      <div className="mb-6 grid gap-4 md:grid-cols-4">
        {summaryItems.map((item) => (
          <div key={item.label} className="rounded-[18px] border border-line bg-cream-deep p-4" title={item.detail}>
            <div className="text-[11px] uppercase tracking-[0.15em] text-forest-card">{item.label}</div>
            <div className="mt-2 text-2xl font-semibold text-forest">{item.value}</div>
          </div>
        ))}
      </div>

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
        Sorted by How sure we are
      </div>

      <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
        {filteredFiles.map((file) => (
          <FileCard key={file.id} file={file} onSelect={setSelectedFile} />
        ))}
      </div>

      {filteredFiles.length === 0 ? (
        <div className="mt-6 rounded-[20px] border border-line bg-cream-deep p-6 text-center text-muted">
          No files match that search yet. Try a broader term or different filter.
        </div>
      ) : null}

      <FileDrawer key={selectedFile?.id ?? 'empty'} file={selectedFile} isOpen={Boolean(selectedFile)} onClose={() => setSelectedFile(null)} />
    </div>
  );
}
