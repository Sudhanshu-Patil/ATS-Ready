/** @type {import('tailwindcss').Config} */

// Colors are sourced from CSS custom properties (defined in index.css as
// space-separated RGB triples, e.g. "255 107 53") rather than hard-coded hex.
// This is the standard Tailwind pattern for runtime-switchable themes: the
// `<alpha-value>` placeholder lets Tailwind's opacity modifiers (bg-brand/20,
// text-brand/40, etc.) keep working normally, while the actual R/G/B channels
// resolve from whichever [data-theme] scope is active — so every existing
// bg-*/text-*/border-* utility across the app adapts to light/dark with zero
// changes to the components using them.
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
        // Brand/accent hues are theme-invariant (ember reads fine on both a
        // dark and light base) — plain static values, no CSS variable
        // indirection needed. `muted` bakes its own low alpha directly into
        // the hex (it's used bare, e.g. `bg-brand-muted`, never with a
        // Tailwind opacity suffix) since <alpha-value> defaults to 1 (fully
        // opaque) when no suffix is present, which would break that pattern.
        brand: {
          DEFAULT: '#FF6B35',
          hover:   '#FF8555',
          muted:   '#FF6B3520',
        },
        accent: {
          violet:  '#7C3AED',
          magenta: '#FF3D77',
        },
        score: {
          DEFAULT: withOpacity('--color-score'),
          // Full rgba() string per theme (see index.css) — same bare-usage
          // reasoning as brand.muted above, but score's hue DOES need to
          // shift per theme, so this can't be a static hex like brand.muted.
          muted: 'var(--color-score-muted)',
        },
        text: {
          primary:   withOpacity('--color-text-primary'),
          secondary: withOpacity('--color-text-secondary'),
          muted:     withOpacity('--color-text-muted'),
        },
      },
      fontFamily: {
        sans:    ['Plus Jakarta Sans Variable', 'system-ui', 'sans-serif'],
        mono:    ['JetBrains Mono', 'monospace'],
        display: ['Bricolage Grotesque Variable', 'Plus Jakarta Sans Variable', 'system-ui', 'sans-serif'],
      },
      keyframes: {
        // Blob position/opacity only — never animate blur radius itself
        // (re-rasterizes every frame). Blur is applied once as a static filter.
        'aurora-drift': {
          '0%, 100%': { transform: 'translate(0%, 0%) scale(1)', opacity: '0.9' },
          '33%':      { transform: 'translate(6%, -8%) scale(1.08)', opacity: '1' },
          '66%':      { transform: 'translate(-5%, 5%) scale(0.96)', opacity: '0.85' },
        },
        shimmer: {
          '0%':   { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
        // Landing-page idle motion (hero core, feature-card vignettes)
        float: {
          '0%, 100%': { transform: 'translateY(0) rotate(-2deg)' },
          '50%':      { transform: 'translateY(-14px) rotate(2deg)' },
        },
        orbit: {
          '0%':   { transform: 'rotate(0deg) translateX(70px) rotate(0deg)' },
          '100%': { transform: 'rotate(360deg) translateX(70px) rotate(-360deg)' },
        },
        'fall-loop': {
          '0%':   { transform: 'translateY(-60px)', opacity: '0' },
          '15%':  { opacity: '1' },
          '85%':  { opacity: '1' },
          '100%': { transform: 'translateY(60px)', opacity: '0' },
        },
      },
      animation: {
        'pulse-slow':   'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'spin-slow':    'spin 2s linear infinite',
        'aurora-drift': 'aurora-drift 22s ease-in-out infinite',
        shimmer:        'shimmer 1.6s ease-in-out infinite',
        float:          'float 7s ease-in-out infinite',
        orbit:          'orbit 12s linear infinite',
        'fall-loop':    'fall-loop 3s ease-in infinite',
      },
    },
  },
  plugins: [],
}
