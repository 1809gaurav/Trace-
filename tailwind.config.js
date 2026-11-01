/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        cream: 'var(--cream)',
        'cream-deep': 'var(--cream-deep)',
        line: 'var(--line)',
        forest: 'var(--forest)',
        'forest-card': 'var(--forest-card)',
        leaf: 'var(--leaf)',
        tile: 'var(--tile)',
        muted: 'var(--muted)',
        mint: 'var(--mint)',
        'on-dark': 'var(--on-dark)',
      },
      fontFamily: {
        display: ['Fraunces', 'Georgia', 'serif'],
        body: ['Atkinson Hyperlegible', 'Arial', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      boxShadow: {
        paper: '4px 4px 0 color-mix(in srgb, var(--forest) 12%, transparent)',
        marker: '2px 2px 0 color-mix(in srgb, var(--forest) 12%, transparent)',
      },
      ringWidth: {
        3: '3px',
      },
      ringOffsetWidth: {
        2: '2px',
      },
    },
  },
  plugins: [],
};
