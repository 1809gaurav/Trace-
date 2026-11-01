import { motion, useMotionValue, useSpring, type HTMLMotionProps } from 'framer-motion';
import type { MouseEvent, PropsWithChildren } from 'react';

interface MagneticButtonProps extends HTMLMotionProps<'button'> {
  className?: string;
  variant?: 'primary' | 'secondary';
}

export function MagneticButton({
  children,
  className = '',
  variant = 'primary',
  ...props
}: PropsWithChildren<MagneticButtonProps>) {
  const x = useMotionValue(0);
  const y = useMotionValue(0);
  const springX = useSpring(x, { stiffness: 260, damping: 18, mass: 0.4 });
  const springY = useSpring(y, { stiffness: 260, damping: 18, mass: 0.4 });

  const handleMove = (event: MouseEvent<HTMLButtonElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const offsetX = event.clientX - (rect.left + rect.width / 2);
    const offsetY = event.clientY - (rect.top + rect.height / 2);
    x.set(Math.max(-8, Math.min(8, offsetX / 10)));
    y.set(Math.max(-8, Math.min(8, offsetY / 10)));
  };

  const handleLeave = () => {
    x.set(0);
    y.set(0);
  };

  return (
    <motion.button
      type="button"
      className={`inline-flex items-center justify-center rounded-[18px] px-4 py-3 text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-offset-2 focus-visible:ring-offset-cream ${
        variant === 'primary'
          ? 'border-2 border-forest bg-forest text-on-forest hover:bg-forest focus-visible:ring-forest'
          : 'border-2 border-forest bg-transparent text-forest hover:bg-cream-deep focus-visible:ring-forest'
      } ${className}`}
      onMouseMove={handleMove}
      onMouseLeave={handleLeave}
      style={{
        x: springX,
        y: springY,
      }}
      {...props}
    >
      {children}
    </motion.button>
  );
}
