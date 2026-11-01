import { NavLink, Route, Routes, useLocation } from 'react-router-dom';
import { BrowserRouter } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { A11yMenu } from './components/A11yMenu';
import { CursorLayer } from './components/CursorLayer';
import { SkipLink } from './components/SkipLink';
import { useA11ySettings } from './hooks/useA11ySettings';
import { CustodyPage } from './pages/CustodyPage';
import { HomePage } from './pages/HomePage';
import { NotFoundPage } from './pages/NotFoundPage';
import { ReportPage } from './pages/ReportPage';
import { ResultsPage } from './pages/ResultsPage';
import { RunPage } from './pages/RunPage';
import traceLogo from './assets/logo.svg';

const navItems = [
  { label: 'Start', to: '/' },
  { label: 'Results', to: '/results' },
  { label: 'Custody log', to: '/custody' },
  { label: 'Report', to: '/report' },
];

function AppContent() {
  const location = useLocation();
  const [scrolled, setScrolled] = useState(false);
  const { settings, setFontScale, setHighContrast, setPlayfulMotion, setDyslexiaMode } = useA11ySettings();
  const isHome = location.pathname === '/';

  useEffect(() => {
    const updateScroll = () => setScrolled(window.scrollY > 12);
    updateScroll();
    window.addEventListener('scroll', updateScroll, { passive: true });
    return () => window.removeEventListener('scroll', updateScroll);
  }, []);

  useEffect(() => {
    const pageTitle: Record<string, string> = {
      '/': 'Start',
      '/run': 'Recovery in progress',
      '/results': 'Results',
      '/custody': 'Custody log',
      '/report': 'Report',
    };
    document.title = `Trace | ${pageTitle[location.pathname] ?? 'Not found'}`;
  }, [location.pathname]);

  return (
    <div className="trace-app min-h-screen bg-cream text-forest">
      <SkipLink />
      <CursorLayer playfulMotionEnabled={settings.playfulMotion} />
      <A11yMenu
        settings={settings}
        onFontScale={setFontScale}
        onHighContrast={setHighContrast}
        onPlayfulMotion={setPlayfulMotion}
        onDyslexiaMode={setDyslexiaMode}
      />

      <header
        className={`site-header z-30 ${
          isHome
            ? `fixed inset-x-0 top-0 ${scrolled ? 'site-header--scrolled' : 'site-header--home'}`
            : 'sticky top-0 border-b border-line bg-cream backdrop-blur-sm'
        }`}
      >
        <div className="mx-auto flex max-w-6xl flex-col gap-2 px-4 py-3 md:flex-row md:items-center md:justify-between md:px-6">
          <div className="flex w-full items-center justify-between gap-4 md:w-auto">
            <NavLink to="/" className="inline-flex min-h-11 items-center gap-3 rounded-sm focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-forest focus-visible:ring-offset-2 focus-visible:ring-offset-cream" aria-label="Trace home">
              <img src={traceLogo} alt="Trace logo" className="h-auto w-[112px] sm:w-[132px]" />
            </NavLink>
            <div className="rounded-full border border-line bg-cream-deep px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-forest md:hidden">
              Ready for review
            </div>
          </div>

          <nav aria-label="Primary navigation" className="flex w-full flex-wrap items-center gap-0 md:w-auto md:gap-3">
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  `min-h-11 shrink-0 rounded-full border px-2 py-2 text-xs font-medium transition focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-forest focus-visible:ring-offset-2 focus-visible:ring-offset-cream md:px-3 md:text-sm ${
                    isActive ? 'border-line bg-cream-deep text-forest' : 'border-transparent text-forest hover:bg-cream-deep'
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>

          <div className="hidden rounded-full border border-line bg-cream-deep px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-forest md:block">
            Ready for review
          </div>
        </div>
      </header>

      <main id="main-content" className={isHome ? 'pb-0' : 'mx-auto max-w-6xl px-4 pb-20 pt-4 md:px-6 md:pt-8'}>
        <Routes>
          <Route path="/" element={<HomePage playfulMotionEnabled={settings.playfulMotion} />} />
          <Route path="/run" element={<RunPage />} />
          <Route path="/results" element={<ResultsPage />} />
          <Route path="/custody" element={<CustodyPage />} />
          <Route path="/report" element={<ReportPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </main>

      <footer className="border-t border-line bg-cream">
        <div className="mx-auto max-w-6xl px-4 py-6 text-sm leading-relaxed text-muted md:px-6">
          Trace helps recover evidence from damaged drives, but a partial or reconstructed file may still be uncertain. The review is a practical, evidence-led check — not a guarantee of perfect reconstruction.
        </div>
      </footer>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AppContent />
    </BrowserRouter>
  );
}
