import { Download, Printer, ShieldCheck } from 'lucide-react';
import { useEffect, useState } from 'react';
import { fetchReport, mockPdfDownload } from '../api/client';
import type { ReportData } from '../api/types';
import traceLogo from '../assets/logo.svg';

export function ReportPage() {
  const [report, setReport] = useState<ReportData | null>(null);
  const [toast, setToast] = useState('');

  useEffect(() => {
    void fetchReport().then(setReport);
  }, []);

  const triggerDownload = async () => {
    const result = await mockPdfDownload();
    setToast(result.placeholder);
    window.setTimeout(() => setToast(''), 2200);
  };

  const printReport = () => {
    window.print();
    setToast('The print view is ready.');
    window.setTimeout(() => setToast(''), 2200);
  };

  if (!report) {
    return (
      <section aria-busy="true" aria-live="polite" className="my-8 rounded-[22px] border border-line bg-cream-deep p-6 text-center">
        <img src={traceLogo} alt="" aria-hidden="true" className="mx-auto mb-4 h-auto w-[112px] opacity-60" />
        <h1 className="text-3xl text-forest">Preparing your report</h1>
        <p className="mt-2 text-muted">Gathering the case summary and evidence list.</p>
        <div className="skeleton-line mx-auto mt-5 h-3 max-w-sm rounded-full bg-cream-deep" />
      </section>
    );
  }

  return (
    <div className="py-8">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-[11px] uppercase tracking-[0.15em] text-forest-card">Report</p>
          <h1 className="mt-2 text-4xl text-forest">Court-ready summary</h1>
        </div>
        <div className="flex gap-3">
          <button
            type="button"
            onClick={triggerDownload}
            className="inline-flex min-h-11 items-center gap-2 rounded-full border-2 border-leaf bg-leaf px-4 py-2 text-sm font-medium text-on-dark focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-mint focus-visible:ring-offset-2 focus-visible:ring-offset-cream"
          >
            <Download size={16} />
            Download PDF
          </button>
          <button
            type="button"
            onClick={printReport}
            className="inline-flex items-center gap-2 rounded-full border-2 border-forest bg-transparent px-4 py-2 text-sm font-medium text-forest focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-forest focus-visible:ring-offset-2 focus-visible:ring-offset-cream"
          >
            <Printer size={16} />
            Print
          </button>
        </div>
      </div>

      <div className="rounded-[28px] border border-line bg-cream-deep p-6 shadow-paper">
        <div className="rounded-[22px] border border-line bg-cream p-6 text-forest">
          <div className="flex flex-col gap-4 border-b border-line pb-4 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <img src={traceLogo} alt="" aria-hidden="true" className="mb-4 h-auto w-[112px]" />
              <p className="text-[11px] uppercase tracking-[0.16em] text-forest-card">Trace evidence report</p>
              <p className="text-[11px] uppercase tracking-[0.16em] text-forest-card">Case ID</p>
              <h2 className="mt-2 text-2xl font-semibold text-forest">{report.caseId}</h2>
            </div>
            <div className="text-right">
              <p className="text-[11px] uppercase tracking-[0.16em] text-forest-card">Collection</p>
              <p className="mt-2 text-sm text-muted">{report.collection}</p>
            </div>
          </div>

          <div className="mt-5">
            <p className="text-[11px] uppercase tracking-[0.16em] text-forest-card">Case name</p>
            <h3 className="mt-2 text-3xl font-semibold text-forest">{report.caseName}</h3>
          </div>

          <div className="mt-6 grid gap-4 md:grid-cols-2">
            <div className="rounded-[16px] border border-line bg-cream p-4">
              <div className="mb-2 flex items-center gap-2 text-forest">
                <ShieldCheck size={18} />
                <span className="text-[11px] uppercase tracking-[0.16em]">Summary</span>
              </div>
              <p className="text-base leading-relaxed text-muted">{report.summary}</p>
            </div>
            <div className="rounded-[16px] border border-line bg-cream p-4">
              <div className="mb-2 text-[11px] uppercase tracking-[0.16em] text-forest-card">Limitations</div>
              <ul className="space-y-2 text-sm text-muted">
                {report.limitations.map((item) => (
                  <li key={item}>• {item}</li>
                ))}
              </ul>
            </div>
          </div>

          <div className="mt-6">
            <p className="text-[11px] uppercase tracking-[0.16em] text-forest-card">Recovered files</p>
            <ul className="mt-3 list-inside list-disc space-y-2 text-sm text-muted">
              {report.fileNames.map((fileName) => (
                <li key={fileName}>{fileName}</li>
              ))}
            </ul>
          </div>

          <div className="mt-6 border-t border-line pt-4">
            <p className="text-[11px] uppercase tracking-[0.16em] text-forest-card">Notes</p>
            <ul className="mt-3 space-y-2 text-sm text-muted">
              {report.notes.map((note) => (
                <li key={note}>• {note}</li>
              ))}
            </ul>
          </div>
        </div>
      </div>

      {toast ? (
        <div aria-live="polite" className="fixed bottom-24 right-4 rounded-full border border-line bg-cream-deep px-4 py-2 text-sm text-forest">
          {toast}
        </div>
      ) : null}
    </div>
  );
}
