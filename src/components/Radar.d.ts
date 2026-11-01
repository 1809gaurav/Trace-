import type { CSSProperties, JSX } from 'react';

export interface RadarProps {
  mode?: 'sweep' | 'static';
  speed?: number;
  trail?: number;
  scale?: number;
  ringCount?: number;
  spokeCount?: number;
  ticks?: boolean;
  targets?: number;
  clutter?: number;
  glow?: number;
  brightness?: number;
  gridOpacity?: number;
  lineWidth?: number;
  tilt?: number;
  mouseInteraction?: boolean;
  intro?: boolean;
  grain?: number;
  fade?: number;
  opacity?: number;
  dpr?: number;
  centerX?: number;
  centerY?: number;
  lightMode?: boolean;
  backgroundColor?: string;
  color?: string;
  paused?: boolean;
  className?: string;
  style?: CSSProperties;
  onUnavailable?: () => void;
  onError?: () => void;
}

declare function Radar(props: RadarProps): JSX.Element;
export default Radar;
