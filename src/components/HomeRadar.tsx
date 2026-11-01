import { Component, lazy, Suspense, useCallback, useEffect, useMemo, useState } from 'react';
import type { ErrorInfo, ReactNode } from 'react';
import { radarConfig } from '../config/radar';
import type { RadarProps } from './Radar';

const LazyRadar = lazy(() => import('./Radar'));
const PAUSE_STORAGE_KEY = 'trace-home-radar-paused';

interface BoundaryProps {
  children: ReactNode;
  fallback: ReactNode;
}

interface BoundaryState {
  failed: boolean;
}

class RadarErrorBoundary extends Component<BoundaryProps, BoundaryState> {
  state: BoundaryState = { failed: false };

  static getDerivedStateFromError(): BoundaryState {
    return { failed: true };
  }

  componentDidCatch(_error: Error, _info: ErrorInfo) {}

  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}

function readPausePreference() {
  try {
    return window.localStorage.getItem(PAUSE_STORAGE_KEY) === 'true';
  } catch {
    return false;
  }
}

function getLiteDevicePreference() {
  const threads = navigator.hardwareConcurrency;
  return window.innerWidth < 768
    || window.matchMedia('(pointer: coarse)').matches
    || (threads > 0 && threads <= 4);
}

function prefersReducedMotion() {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

function supportsWebGL2() {
  try {
    const canvas = document.createElement('canvas');
    const context = canvas.getContext('webgl2');
    const supported = context !== null;
    context?.getExtension('WEBGL_lose_context')?.loseContext();
    return supported;
  } catch {
    return false;
  }
}

function StaticRadar() {
  return (
    <svg className="radar-static" viewBox="0 0 100 100" aria-hidden="true" focusable="false">
      <circle cx="50" cy="50" r="44" />
      <circle cx="50" cy="50" r="33" />
      <circle cx="50" cy="50" r="22" />
      <circle cx="50" cy="50" r="11" />
    </svg>
  );
}

export function HomeRadar({
  playfulMotionEnabled,
  highContrastEnabled,
}: {
  playfulMotionEnabled: boolean;
  highContrastEnabled: boolean;
}) {
  const [userPaused, setUserPaused] = useState(readPausePreference);
  const [webglAvailable, setWebglAvailable] = useState(supportsWebGL2);
  const [useLite, setUseLite] = useState(getLiteDevicePreference);
  const [reducedMotion, setReducedMotion] = useState(prefersReducedMotion);

  useEffect(() => {
    const coarsePointer = window.matchMedia('(pointer: coarse)');
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
    const updateDevice = () => {
      const threads = navigator.hardwareConcurrency;
      setUseLite(
        window.innerWidth < 768
        || coarsePointer.matches
        || (threads > 0 && threads <= 4),
      );
    };
    const updateMotion = () => setReducedMotion(reduced.matches);
    window.addEventListener('resize', updateDevice, { passive: true });
    coarsePointer.addEventListener('change', updateDevice);
    reduced.addEventListener('change', updateMotion);
    return () => {
      window.removeEventListener('resize', updateDevice);
      coarsePointer.removeEventListener('change', updateDevice);
      reduced.removeEventListener('change', updateMotion);
    };
  }, []);

  const calmMode = reducedMotion || highContrastEnabled || !playfulMotionEnabled;
  const configuration = useMemo(
    () => calmMode ? radarConfig.calm : useLite ? radarConfig.lite : radarConfig.desktop,
    [calmMode, useLite],
  );
  const radarProps = useMemo<RadarProps>(
    () => ({ ...configuration, paused: Boolean(configuration.paused || userPaused) }),
    [configuration, userPaused],
  );
  const showStatic = webglAvailable !== true;
  const markUnavailable = useCallback(() => setWebglAvailable(false), []);
  const markFailed = useCallback(() => setWebglAvailable(false), []);

  const fallback = <StaticRadar />;

  return (
    <>
      <div className="radar-layer" aria-hidden="true">
        {showStatic ? (
          fallback
        ) : (
          <RadarErrorBoundary fallback={fallback}>
            <Suspense fallback={fallback}>
              <LazyRadar
                {...radarProps}
                onUnavailable={markUnavailable}
                onError={markFailed}
              />
            </Suspense>
          </RadarErrorBoundary>
        )}
      </div>
      <div className="orbit-rings" aria-hidden="true" />
      <span className="floating-token" style={{ top: '21%', left: '59%' }} aria-hidden="true">.jpg</span>
      <span className="floating-token" style={{ top: '69%', left: '16%' }} aria-hidden="true">.pdf</span>
      <span className="floating-token" style={{ top: '33%', right: '13%' }} aria-hidden="true">.dvr</span>
      <span className="floating-token" style={{ bottom: '19%', right: '34%' }} aria-hidden="true">a3f9...</span>
      <button
        type="button"
        className="hero-pause-button"
        aria-pressed={userPaused}
        aria-label={userPaused ? 'Resume background animation' : 'Pause background animation'}
        onClick={() => {
          setUserPaused((current) => {
            const next = !current;
            try {
              window.localStorage.setItem(PAUSE_STORAGE_KEY, String(next));
            } catch {
              return next;
            }
            return next;
          });
        }}
      >
        {userPaused ? 'Resume background animation' : 'Pause background animation'}
      </button>
    </>
  );
}
