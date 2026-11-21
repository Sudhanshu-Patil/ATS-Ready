/** @type {import('tailwindcss').Config} */

// Colours come from CSS custom properties (index.css) as space-separated RGB triples, so Tailwind's opacity modifiers
// (bg-brand/20, text-text-muted/80) keep working while the actual values switch with [data-theme].
function withOpacity(variable) {
  return `rgb(var(${variable}) / <alpha-value>)`
}

export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        bg: {
          DEFAULT: withOpacity('--color-bg'),
          card:    withOpacity('--color-bg-card'),
          hover:   withOpacity('--color-bg-hover'),
          border:  withOpacity('--color-bg-border'),
        },
        // One accent, a proofreader's red-orange. `muted` carries its own alpha (used bare as bg-brand-muted).
        brand: {
          DEFAULT: withOpacity('--color-brand'),
          hover:   withOpacity('--color-brand-hover'),
          muted:   'var(--color-brand-muted)',
        },
        score: {
          DEFAULT: withOpacity('--color-score'),
          muted:   'var(--color-score-muted)',
        },
        warn: withOpacity('--color-warn'),
        bad:  withOpacity('--color-bad'),
        text: {
          primary:   withOpacity('--color-text-primary'),
          secondary: withOpacity('--color-text-secondary'),
          muted:     withOpacity('--color-text-muted'),
        },
      },
      fontFamily: {
        sans:    ['Instrument Sans Variable', 'system-ui', 'sans-serif'],
        mono:    ['Geist Mono Variable', 'ui-monospace', 'monospace'],
        // Large headings only (page titles, the landing headline). Never labels, buttons or figures.
        display: ['Newsreader Variable', 'Georgia', 'serif'],
      },
      keyframes: {
        shimmer: {
          '0%':   { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
      },
      animation: {
        'spin-slow': 'spin 2s linear infinite',
        shimmer:     'shimmer 1.6s ease-in-out infinite',
      },
    },
  },
  plugins: [],
}
