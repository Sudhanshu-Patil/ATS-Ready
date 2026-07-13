import { motion } from 'framer-motion'
import { fadeInUp, staggerContainer } from '../../lib/motion'

// EXTRACT / INJECT / PERFECT — the brief's three looping card videos,
// replaced with pure-CSS vignettes (orbit / fall-loop keyframes from
// tailwind.config.js + pulse-slow). Zero video assets, zero requests.

function ExtractVignette() {
  return (
    <div className="relative h-44 flex items-center justify-center overflow-hidden">
      {/* mini core */}
      <div className="w-14 h-[72px] rounded-lg border border-brand/40 bg-gradient-to-br from-[#1c1620] to-[#0b0910] shadow-[0_0_30px_-6px_rgba(255,107,53,0.5)]" />
      {/* orbiting chips — same keyframe, phase-offset via negative delays */}
      {['Python', 'RAG', 'SQL'].map((label, i) => (
        <div
          key={label}
          className="absolute animate-orbit px-2 py-0.5 rounded-full bg-brand/15 border border-brand/40 text-brand text-[10px] font-medium"
          style={{ animationDelay: `${i * -4}s` }}
        >
          {label}
        </div>
      ))}
    </div>
  )
}

function InjectVignette() {
  return (
    <div className="relative h-44 flex items-center justify-center overflow-hidden">
      {/* mini glass grid */}
      <div className="w-32 rounded-lg border border-white/10 bg-white/[0.04] p-3 space-y-2">
        {[90, 70, 82, 55].map((w, i) => (
          <div key={i} className="h-1.5 rounded bg-gradient-to-r from-brand/50 to-amber-400/40" style={{ width: `${w}%` }} />
        ))}
      </div>
      {/* falling chips */}
      {[22, 48, 74].map((left, i) => (
        <div
          key={left}
          className="absolute top-1/2 -mt-16 w-2 h-2 rounded-full bg-brand animate-fall-loop"
          style={{ left: `${left}%`, animationDelay: `${i * -1}s`, boxShadow: '0 0 8px rgba(255,107,53,0.8)' }}
        />
      ))}
    </div>
  )
}

function PerfectVignette() {
  return (
    <div className="relative h-44 flex items-center justify-center overflow-hidden">
      <div className="relative w-24 h-24 animate-pulse-slow">
        <svg viewBox="0 0 96 96" className="w-full h-full -rotate-90">
          <circle cx="48" cy="48" r="38" fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="7" />
          <circle
            cx="48" cy="48" r="38" fill="none"
            stroke="#34D399" strokeWidth="7" strokeLinecap="round"
            strokeDasharray={2 * Math.PI * 38}
            strokeDashoffset={2 * Math.PI * 38 * 0.02}
          />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-2xl font-bold font-mono text-score">98</span>
        </div>
      </div>
      <div className="absolute inset-0 pointer-events-none"
        style={{ background: 'radial-gradient(circle at 50% 50%, rgba(52,211,153,0.08), transparent 60%)' }} />
    </div>
  )
}

const CARDS = [
  {
    eyebrow: 'Extract',
    title: 'Parse any job description',
    desc: 'Paste a JD or a URL — the AI pulls out every required skill, keyword, and qualification an ATS will scan for.',
    Vignette: ExtractVignette,
  },
  {
    eyebrow: 'Inject',
    title: 'Tailor your real experience',
    desc: 'Missing keywords flow into your strongest bullet points — never fabricated, always drawn from your actual profile.',
    Vignette: InjectVignette,
  },
  {
    eyebrow: 'Perfect',
    title: 'Score before you send',
    desc: 'Every resume is graded 0–100 against the exact JD, with a breakdown and one-click keyword boosts.',
    Vignette: PerfectVignette,
  },
]

export default function FeatureCards() {
  return (
    <section id="features" className="relative bg-[#050409] py-24 px-6">
      <div className="max-w-6xl mx-auto">
        <motion.div
          initial="hidden" whileInView="visible" viewport={{ once: true, margin: '-80px' }}
          variants={fadeInUp} className="text-center mb-14"
        >
          <p className="eyebrow !text-brand mb-3">The pipeline</p>
          <h2 className="font-display text-3xl sm:text-4xl font-bold text-text-primary">
            Three moves. One interview-ready resume.
          </h2>
        </motion.div>

        <motion.div
          initial="hidden" whileInView="visible" viewport={{ once: true, margin: '-80px' }}
          variants={staggerContainer}
          className="grid sm:grid-cols-3 gap-6"
        >
          {CARDS.map(({ eyebrow, title, desc, Vignette }) => (
            <motion.div
              key={eyebrow} variants={fadeInUp}
              className="card !p-0 overflow-hidden hover:border-brand/40 hover:shadow-lg hover:shadow-brand/5 transition-all duration-300"
            >
              <Vignette />
              <div className="p-6 border-t border-bg-border">
                <p className="eyebrow !text-brand mb-2">{eyebrow}</p>
                <h3 className="text-lg font-semibold text-text-primary mb-2">{title}</h3>
                <p className="text-sm text-text-secondary leading-relaxed">{desc}</p>
              </div>
            </motion.div>
          ))}
        </motion.div>
      </div>
    </section>
  )
}
