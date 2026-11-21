import { motion } from 'framer-motion'
import AnimatedNumber from './AnimatedNumber'

// Consolidates the two score rings that used to be hand-rolled independently
// (JobRecommendations' conic-gradient div, Generator's inline SVG) into one
// component with a size variant.

const SIZES = {
  sm: { box: 56,  viewBox: 120, r: 52, stroke: 10, fontSize: 'text-xs',   showLabel: false },
  lg: { box: 144, viewBox: 120, r: 54, stroke: 7, fontSize: 'text-3xl',  showLabel: true  },
}

// Shared score→color convention — was previously re-derived ad hoc in
// Dashboard, Generator, and History. Import this wherever a score needs a
// consistent color instead of re-checking the >=80/>=60 thresholds locally.
export function scoreColor(score) {
  if (score >= 80) return 'rgb(var(--color-score))'
  if (score >= 60) return 'rgb(var(--color-warn))'
  return 'rgb(var(--color-bad))'
}

export function scoreColorClass(score) {
  if (score >= 80) return 'text-score'
  if (score >= 60) return 'text-warn'
  return 'text-bad'
}

export default function ScoreRing({ score = 0, size = 'sm' }) {
  const cfg = SIZES[size] || SIZES.sm
  const circ = 2 * Math.PI * cfg.r
  const fill = (score / 100) * circ
  const color = scoreColor(score)

  return (
    <div
      className="relative flex-shrink-0"
      style={{ width: cfg.box, height: cfg.box }}
    >
      <svg viewBox={`0 0 ${cfg.viewBox} ${cfg.viewBox}`} className="w-full h-full -rotate-90">
        <circle
          cx={cfg.viewBox / 2} cy={cfg.viewBox / 2} r={cfg.r}
          fill="none" stroke="rgb(var(--color-bg-border))" strokeWidth={cfg.stroke}
        />
        <motion.circle
          cx={cfg.viewBox / 2} cy={cfg.viewBox / 2} r={cfg.r}
          fill="none" stroke={color} strokeWidth={cfg.stroke} strokeLinecap="butt"
          strokeDasharray={circ}
          initial={{ strokeDashoffset: circ }}
          animate={{ strokeDashoffset: circ - fill }}
          transition={{ duration: 0.9, ease: [0.16, 1, 0.3, 1] }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className={`font-medium figure ${cfg.fontSize}`} style={{ color }}>
          {size === 'lg' ? <AnimatedNumber value={score} decimals={1} /> : <><AnimatedNumber value={Math.round(score)} />%</>}
        </span>
        {cfg.showLabel && <span className="text-xs text-text-muted">ATS Score</span>}
      </div>
    </div>
  )
}
