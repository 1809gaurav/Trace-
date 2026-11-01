import type { AeroShardsProps } from './AeroShards';

const colors = {
  shardColor: 'var(--forest)',
  accentColor: 'var(--leaf)',
  lightMode: true,
};

const desktop: AeroShardsProps = {
  ...colors,
  placement: 'full',
  material: 'glass',
  markers: 'plus',
  count: 1300,
  depthOfField: 0.75,
  vignette: 0.3,
  mouseInteraction: true,
  pulseOnClick: true,
  holdToGather: true,
  shardSize: 1,
  spread: 1,
  twist: 1,
  billow: 1,
  speed: 1,
  scale: 1,
  glow: 0.35,
  grain: 0.06,
  intro: true,
  mouseStrength: 0.6,
  parallax: 0.5,
  paused: false,
};

const lite: AeroShardsProps = {
  ...desktop,
  count: 500,
  glow: 0.2,
  grain: 0.04,
  mouseStrength: 0.4,
  parallax: 0.3,
};

export const shardsConfig = {
  desktop,
  lite,
} satisfies {
  desktop: AeroShardsProps;
  lite: AeroShardsProps;
};
