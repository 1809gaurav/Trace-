import { NavLink, Route, Routes, useLocation } from 'react-router-dom';
import { BrowserRouter } from 'react-router-dom';
import { Menu, X } from 'lucide-react';
import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchEngineMode, getDemoDataMode, subscribeDemoDataMode, USE_MOCK } from './api/client';
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
import traceLogo from './assets/trace-logo.png';

const navItems = [
  { label: 'Home', to: '/' },
  { label: 'Results', to: '/results' },
  { label: 'Custody log', to: '/custody' },
  { label: 'Report', to: '/report' },
];

function AppContent() {
  const location = useLocation();
  const navigate = useNavigate();
  const [mobileMenuState, setMobileMenuState] = useState(() => ({
    pathname: location.pathname,
    open: false,
  }));
  const [engineStatus, setEngineStatus] = useState<'checking' | 'real' | 'fake' | 'unavailable'>(
    USE_MOCK ? 'fake' : 'checking',
  );
  const mobileMenuOpen = mobileMenuState.pathname === location.pathname && mobileMenuState.open;
  const demoData = useSyncExternalStore(subscribeDemoDataMode, getDemoDataMode, getDemoDataMode);
  const menuRef = useRef<HTMLDivElement>(null);
  const menuToggleRef = useRef<HTMLButtonElement>(null);
  const {
    settings,
    setFontScale,
    setHighContrast,
    setPlayfulMotion,
    setDyslexiaMode,
  } = useA11ySettings();
  const isHome = location.pathname === '/';
  const authMode = import.meta.env.VITE_AUTH_MODE;
  const showLogin = authMode === 'apikey' || authMode === 'jwt';

  const closeMobileMenu = useCallback(
    () => setMobileMenuState({ pathname: location.pathname, open: false }),
    [location.pathname],
  );

  useEffect(() => {
    const pageTitle: Record<string, string> = {
      '/': 'Home',
      '/run': 'Recovery in progress',
      '/results': 'Results',
      '/custody': 'Custody log',
      '/report': 'Report',
    };
    document.title = `Trace | ${pageTitle[location.pathname] ?? 'Not found'}`;
  }, [location.pathname]);

  useEffect(() => {
    if (USE_MOCK) return undefined;
    let active = true;
    void fetchEngineMode()
      .then((mode) => {
        if (active) setEngineStatus(mode);
      })
      .catch((error: unknown) => {
        console.error('Unable to determine the recovery engine mode.', error);
        if (active) setEngineStatus('unavailable');
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!mobileMenuOpen) return undefined;
    const menu = menuRef.current;
    if (!menu) return undefined;
    const focusable = () => Array.from(
      menu.querySelectorAll<HTMLElement>('a[href], button:not([disabled])'),
    );
    const first = focusable()[0];
    first?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        closeMobileMenu();
        menuToggleRef.current?.focus();
        return;
      }
      if (event.key !== 'Tab') return;
      const items = focusable();
      const firstItem = items[0];
      const lastItem = items[items.length - 1];
      if (!firstItem || !lastItem) return;
      if (event.shiftKey && document.activeElement === firstItem) {
        event.preventDefault();
        lastItem.focus();
      } else if (!event.shiftKey && document.activeElement === lastItem) {
        event.preventDefault();
        firstItem.focus();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [closeMobileMenu, mobileMenuOpen]);

  const startCase = () => {
    closeMobileMenu();
    if (isHome) {
      document.getElementById('upload-zone')?.focus();
      document.getElementById('upload-zone')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    } else {
      navigate('/#upload-zone');
    }
  };

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

      <header className="site-header">
        <div className="nav-shell">
          <NavLink to="/" className="brand-lockup" aria-label="Trace home">
            <span className="brand-mark">
              <img src={traceLogo} alt="" />
            </span>
          </NavLink>
          <button
            ref={menuToggleRef}
            type="button"
            className="nav-menu-toggle"
            aria-expanded={mobileMenuOpen}
            aria-controls="primary-navigation"
            aria-label={mobileMenuOpen ? 'Close navigation menu' : 'Open navigation menu'}
            onClick={() => setMobileMenuState({ pathname: location.pathname, open: !mobileMenuOpen })}
          >
            {mobileMenuOpen ? <X size={20} aria-hidden="true" /> : <Menu size={20} aria-hidden="true" />}
          </button>
          <div
            ref={menuRef}
            id="primary-navigation"
            className={`nav-actions ${mobileMenuOpen ? 'is-open' : ''}`}
          >
          <nav aria-label="Primary navigation" className="primary-nav">
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === '/'}
                className="nav-link"
                onClick={closeMobileMenu}
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
          {demoData || engineStatus === 'fake' ? (
            <span className="demo-pill" role="status">Demo data</span>
          ) : engineStatus === 'unavailable' ? (
            <span className="demo-pill" role="status">Engine status unavailable</span>
          ) : null}
          {showLogin ? <NavLink to="/login" className="nav-login">Log in</NavLink> : null}
          <button type="button" className="nav-cta" onClick={startCase}>Start a case</button>
          </div>
        </div>
      </header>

      <main id="main-content" className={isHome ? 'pb-0' : 'mx-auto max-w-6xl px-4 pb-20 pt-4 md:px-6 md:pt-8'}>
        <Routes>
          <Route path="/" element={<HomePage playfulMotionEnabled={settings.playfulMotion} highContrastEnabled={settings.highContrast} />} />
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
