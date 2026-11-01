import { Component, lazy, Suspense, useEffect, useRef, useState } from 'react';
import type { ErrorInfo, ReactNode } from 'react';
import { shardsConfig } from './archive/shards';
import type { AeroShardsProps } from './archive/AeroShards';
import traceLogo from '../assets/trace-logo.png';

const AeroShards = lazy(() => import('./archive/AeroShards'));
const PAUSE_STORAGE_KEY = 'trace-background-paused';

interface BoundaryProps {
  children: ReactNode;
  fallback: ReactNode;
}

interface BoundaryState {
  failed: boolean;
}

class ShardsErrorBoundary extends Component<BoundaryProps, BoundaryState> {
  state: BoundaryState = { failed: false };

  static getDerivedStateFromError(): BoundaryState {
    return { failed: true };
  }

  componentDidCatch(_error: Error, _info: ErrorInfo) {
    // Keep the decorative layer's failure isolated from the evidence workflow.
  }

  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}

function readPausePreference(): boolean {
  try {
    return window.localStorage.getItem(PAUSE_STORAGE_KEY) === 'true';
  } catch {
    return false;
  }
}

function getLowPowerMode(): boolean {
  const nav = navigator as Navigator & { deviceMemory?: number };
  return (nav.hardwareConcurrency > 0 && nav.hardwareConcurrency <= 4)
    || (nav.deviceMemory !== undefined && nav.deviceMemory <= 4);
}

export function ShardBackground({ playfulMotionEnabled }: { playfulMotionEnabled: boolean }) {
  const observerTarget = useRef<HTMLDivElement>(null);
  const [userPaused, setUserPaused] = useState(readPausePreference);
  const [inView, setInView] = useState(false);
  const [tabVisible, setTabVisible] = useState(true);
  const [smallScreen, setSmallScreen] = useState(false);
  const [reducedMotion, setReducedMotion] = useState(false);
  const staticMode = reducedMotion || !playfulMotionEnabled;
  const lowPower = getLowPowerMode();
  const useLite = smallScreen || lowPower;
  const baseConfig = useLite ? shardsConfig.lite : shardsConfig.desktop;
  const paused = userPaused || !inView || !tabVisible || staticMode;

  useEffect(() => {
    const media = window.matchMedia('(max-width: 767px), (pointer: coarse)');
    const updateScreen = () => setSmallScreen(media.matches || window.innerWidth < 768);
    updateScreen();
    media.addEventListener('change', updateScreen);
    return () => media.removeEventListener('change', updateScreen);
  }, []);

  useEffect(() => {
    const media = window.matchMedia('(prefers-reduced-motion: reduce)');
    const updateReducedMotion = () => setReducedMotion(media.matches);
    updateReducedMotion();
    media.addEventListener('change', updateReducedMotion);
    return () => media.removeEventListener('change', updateReducedMotion);
  }, []);

  useEffect(() => {
    const target = observerTarget.current;
    if (!target) return undefined;
    const observer = new IntersectionObserver(
      ([entry]) => setInView(entry.isIntersecting),
      { threshold: 0.01 },
    );
    observer.observe(target);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const updateVisibility = () => setTabVisible(document.visibilityState === 'visible');
    updateVisibility();
    document.addEventListener('visibilitychange', updateVisibility);
    return () => document.removeEventListener('visibilitychange', updateVisibility);
  }, []);

  const fallback = (
    <div className="shards-fallback">
      <img src={traceLogo} alt="" aria-hidden="true" className="shards-fallback__logo" />
    </div>
  );
  const componentProps: AeroShardsProps = {
    ...baseConfig,
    count: staticMode ? 300 : baseConfig.count,
    paused,
    mouseInteraction: staticMode ? false : baseConfig.mouseInteraction,
    pulseOnClick: staticMode ? false : baseConfig.pulseOnClick,
    holdToGather: staticMode ? false : baseConfig.holdToGather,
    intro: staticMode ? false : baseConfig.intro,
  };

  const togglePaused = () => {
    setUserPaused((current) => {
      const next = !current;
      try {
        window.localStorage.setItem(PAUSE_STORAGE_KEY, String(next));
      } catch {
        // The animation remains controllable when storage is unavailable.
      }
      return next;
    });
  };

  return (
    <>
      <div
        ref={observerTarget}
        className="shard-layer"
        aria-hidden="true"
        role="presentation"
        tabIndex={-1}
      >
        <ShardsErrorBoundary fallback={fallback}>
          <Suspense fallback={fallback}>
            <AeroShards {...componentProps} />
          </Suspense>
        </ShardsErrorBoundary>
      </div>
      <button
        type="button"
        className="hero-pause-button"
        aria-pressed={userPaused}
        onPointerDown={(event) => event.stopPropagation()}
        onClick={(event) => {
          event.stopPropagation();
          togglePaused();
        }}
      >
        {userPaused ? 'Resume background animation' : 'Pause background animation'}
      </button>
    </>
  );
}
