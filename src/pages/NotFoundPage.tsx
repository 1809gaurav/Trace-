import { AlertTriangle } from 'lucide-react';
import { Link } from 'react-router-dom';

export function NotFoundPage() {
  return (
    <div className="flex min-h-[50vh] items-center justify-center py-12">
      <div className="max-w-xl rounded-[24px] border border-line bg-cream-deep p-8 text-center shadow-paper">
        <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full border border-line bg-cream text-forest">
          <AlertTriangle size={26} />
        </div>
        <h1 className="mt-5 text-4xl text-forest">Trace couldn’t find that page</h1>
        <p className="mt-3 text-lg leading-relaxed text-muted">
          This page was not part of the evidence set. Head back to the start and reopen the case.
        </p>
        <Link
          to="/"
          className="mt-5 inline-flex min-h-11 rounded-full border border-line bg-cream-deep px-5 py-3 text-sm font-semibold text-forest focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-forest focus-visible:ring-offset-2 focus-visible:ring-offset-cream"
        >
          Back to start
        </Link>
      </div>
    </div>
  );
}
