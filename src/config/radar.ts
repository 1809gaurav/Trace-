import type { RadarProps } from '../components/Radar';

const common = {
  mode: 'sweep',
  speed: 0.8,
  trail: 0.35,
  scale: 0.95,
  ringCount: 6,
  spokeCount: 12,
  ticks: true,
  targets: 6,
  clutter: 0.25,
  glow: 0.6,
  brightness: 1,
  gridOpacity: 0.9,
  lineWidth: 1,
  tilt: 0,
  mouseInteraction: true,
  intro: true,
  grain: 0.03,
  fade: 0.35,
  opacity: 0.85,
  dpr: 2,
  centerX: 0.5,
  centerY: 0.5,
  lightMode: true,
  backgroundColor: 'transparent',
  color: 'var(--leaf)',
} satisfies Partial<RadarProps>;

const desktop: Partial<RadarProps> = { ...common };

const lite: Partial<RadarProps> = {
  ...common,
  scale: 0.85,
  ringCount: 4,
  spokeCount: 8,
  targets: 3,
  clutter: 0.15,
  glow: 0.3,
  dpr: 1.5,
};

const calm: Partial<RadarProps> = {
  ...common,
  paused: true,
  intro: false,
  mouseInteraction: false,
  opacity: 0.5,
  targets: 0,
  clutter: 0,
};

export const radarConfig = { desktop, lite, calm };
