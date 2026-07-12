import { motion } from 'framer-motion'

// Consolidates the two score rings that used to be hand-rolled independently
// (JobRecommendations' conic-gradient div, Generator's inline SVG) into one
// component with a size variant.

const SIZES = {
  sm: { box: 56,  viewBox: 120, r: 52, stroke: 10, fontSize: 'text-xs',   showLabel: false },
  lg: { box: 144, viewBox: 120, r: 54, stroke: 10, fontSize: 'text-3xl',  showLabel: true  },
}

// Shared score→color convention — was previously re-derived ad hoc in
// Dashboard, Generator, and History. Import this wherever a score needs a
// consistent color instead of re-checking the >=80/>=60 thresholds locally.
export function scoreColor(score) {
  if (score >= 80) return '#34D399' // score
  if (score >= 60) return '#facc15' // yellow-400
  return '#f87171'                  // red-400
}

export function scoreColorClass(score) {
  if (score >= 80) return 'text-score'
  if (score >= 60) return 'text-yellow-400'
  return 'text-red-400'
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
          fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth={cfg.stroke}
        />
        <motion.circle
          cx={cfg.viewBox / 2} cy={cfg.viewBox / 2} r={cfg.r}
          fill="none" stroke={color} strokeWidth={cfg.stroke} strokeLinecap="round"
          strokeDasharray={circ}
          initial={{ strokeDashoffset: circ }}
          animate={{ strokeDashoffset: circ - fill }}
          transition={{ duration: 0.9, ease: [0.16, 1, 0.3, 1] }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className={`font-bold font-mono ${cfg.fontSize}`} style={{ color }}>
          {size === 'lg' ? score.toFixed(1) : `${Math.round(score)}%`}
        </span>
        {cfg.showLabel && <span className="text-xs text-text-muted">ATS Score</span>}
      </div>
    </div>
  )
}
