import type { CSSProperties } from 'react';

export interface AeroShardsProps {
  shardColor: string;
  accentColor: string;
  placement: 'full';
  material: 'glass';
  markers: 'plus';
  count: number;
  depthOfField: number;
  vignette: number;
  mouseInteraction: boolean;
  pulseOnClick: boolean;
  holdToGather: boolean;
  lightMode: boolean;
  shardSize: number;
  spread: number;
  twist: number;
  billow: number;
  speed: number;
  scale: number;
  glow: number;
  grain: number;
  intro: boolean;
  mouseStrength: number;
  parallax: number;
  paused: boolean;
}

/**
 * PLACEHOLDER: the supplied AeroShards component was not present in the workspace.
 * Replace this file with the provided component; ShardBackground uses its props only.
 */
export default function AeroShards({
  shardColor,
  accentColor,
  count,
  speed,
  scale,
  paused,
  lightMode,
}: AeroShardsProps) {
  const shards = Array.from({ length: 44 }, (_, index) => {
    const column = index % 11;
    const row = Math.floor(index / 11);
    const offset = (index * 37) % 17;
    const width = 17 + ((index * 13) % 38);
    const height = 22 + ((index * 19) % 54);
    const style: CSSProperties = {
      left: `${column * 10 + (row % 2) * 4 + (offset % 4)}%`,
      top: `${row * 26 + offset}%`,
      width,
      height,
      background: index % 5 === 0 ? accentColor : shardColor,
      opacity: lightMode ? 0.12 + ((index * 7) % 12) / 100 : 0.18 + ((index * 7) % 15) / 100,
      animationDelay: `${(index % 9) * -0.8}s`,
      animationDuration: `${9 / Math.max(0.35, speed)}s`,
      transform: `rotate(${(index * 43) % 160 - 80}deg) scale(${scale * (0.65 + ((index * 11) % 7) / 10)})`,
    };

    return <i className="aero-placeholder__shard" key={index} style={style} />;
  });

  return (
    <div
      className={`aero-placeholder${paused ? ' is-paused' : ''}`}
      aria-hidden="true"
      data-shard-count={count}
    >
      <div className="aero-placeholder__field">{shards}</div>
    </div>
  );
}
