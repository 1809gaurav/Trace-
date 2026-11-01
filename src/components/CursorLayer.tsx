import { motion, useMotionValue, useReducedMotion, useSpring } from 'framer-motion';
import { useEffect, useState } from 'react';

function getInteractionType(target: EventTarget | null) {
  const node = target as HTMLElement | null;
  if (!node) return 'default';
  if (node.closest('input, textarea, select')) return 'input';
  if (node.closest('.upload-zone')) return 'dropzone';
  if (node.closest('button, a, [role="button"]')) return 'button';
  if (node.closest('.home-hero')) return 'hero';
  if (node.closest('.interactive')) return 'button';
  return 'default';
}

export function CursorLayer({ playfulMotionEnabled }: { playfulMotionEnabled: boolean }) {
  const reduceMotion = useReducedMotion();
  const [enabled, setEnabled] = useState(false);
  const [interaction, setInteraction] = useState<'default' | 'button' | 'input' | 'dropzone' | 'hero'>('default');
  const [holding, setHolding] = useState(false);
  const dotX = useMotionValue(0);
  const dotY = useMotionValue(0);
  const ringX = useMotionValue(0);
  const ringY = useMotionValue(0);

  const ringSpringX = useSpring(ringX, { stiffness: 220, damping: 20, mass: 0.35 });
  const ringSpringY = useSpring(ringY, { stiffness: 220, damping: 20, mass: 0.35 });

  useEffect(() => {
    const media = window.matchMedia('(pointer: coarse)');
    const motionMedia = window.matchMedia('(prefers-reduced-motion: reduce)');
    const update = () => {
      setEnabled(!media.matches && !motionMedia.matches && playfulMotionEnabled);
    };
    update();
    media.addEventListener('change', update);
    motionMedia.addEventListener('change', update);
    return () => {
      media.removeEventListener('change', update);
      motionMedia.removeEventListener('change', update);
    };
  }, [playfulMotionEnabled]);

  useEffect(() => {
    if (!enabled || reduceMotion) return undefined;

    const handleMove = (event: PointerEvent) => {
      const { clientX: x, clientY: y } = event;
      dotX.set(x);
      dotY.set(y);
      ringX.set(x);
      ringY.set(y);
      const nextInteraction = getInteractionType(event.target);
      setInteraction((current) => current === nextInteraction ? current : nextInteraction);
    };
    const handleDown = (event: PointerEvent) => {
      if ((event.target as HTMLElement | null)?.closest('.home-hero')) setHolding(true);
    };
    const handleUp = () => setHolding(false);

    window.addEventListener('pointermove', handleMove);
    window.addEventListener('pointerdown', handleDown);
    window.addEventListener('pointerup', handleUp);
    window.addEventListener('pointercancel', handleUp);
    return () => {
      window.removeEventListener('pointermove', handleMove);
      window.removeEventListener('pointerdown', handleDown);
      window.removeEventListener('pointerup', handleUp);
      window.removeEventListener('pointercancel', handleUp);
    };
  }, [dotX, dotY, enabled, reduceMotion, ringX, ringY]);

  if (!enabled || reduceMotion) {
    return null;
  }

  return (
    <div aria-hidden="true" className="pointer-events-none fixed inset-0 z-50 hidden md:block">
      <motion.div
        className="absolute h-2.5 w-2.5 rounded-full bg-forest"
        style={{ x: dotX, y: dotY, translateX: '-50%', translateY: '-50%' }}
      />
      <motion.div
        className={`absolute rounded-full border border-line ${interaction === 'button' ? 'leaf-wash-20' : 'bg-transparent'} ${interaction === 'input' ? 'h-7 w-1 rounded-sm border-l-2 border-r-0 border-y-0' : 'h-9 w-9'}`}
        style={{
          x: ringSpringX,
          y: ringSpringY,
          translateX: '-50%',
          translateY: '-50%',
          opacity: interaction === 'dropzone' ? 1 : interaction === 'hero' ? 0.35 : 0.9,
          scale: holding && interaction === 'hero' ? 0.68 : 1,
        }}
      >
        {interaction === 'dropzone' && (
          <span className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 text-[10px] uppercase tracking-[0.18em] text-forest">
            Drop here
          </span>
        )}
      </motion.div>
    </div>
  );
}
