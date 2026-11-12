import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  motion, useScroll, useSpring, useTransform,
  useMotionValueEvent, AnimatePresence, useReducedMotion,
} from 'framer-motion'
import { useAuthStore } from '../../store/auth'

// ─────────────────────────────────────────────────────────────────────────────
// The cinematic scroll journey — the design brief's 15s scrub video,
// reimplemented as pure DOM/CSS driven by scroll position. A tall track
// (400vh) pins a full-viewport stage; scroll progress (0→1, spring-smoothed)
// drives every layer via MotionValues. No canvas, no video, no new deps.
//
// Perf rules (from plan): continuous animation binds MotionValues in `style`
// only — the single piece of React state is the 3-value phase index for the
// caption card, updated at thresholds via useMotionValueEvent. Only children
// of the sticky stage animate, never the sticky container itself.
// ─────────────────────────────────────────────────────────────────────────────

const ORBIT_CHIPS = [
  { label: 'Python',        tx: -180, ty: -120 },
  { label: 'FastAPI',       tx:  175, ty: -140 },
  { label: 'RAG',           tx: -235, ty:   15 },
  { label: 'PostgreSQL',    tx:  235, ty:  -10 },
  { label: 'LLMs',          tx: -160, ty:  130 },
  { label: 'Docker',        tx:  185, ty:  120 },
  { label: 'Kubernetes',    tx:  -60, ty: -195 },
  { label: 'System Design', tx:   75, ty:  185 },
  { label: 'CI/CD',         tx:  -15, ty:  205 },
  { label: 'AWS',           tx:   35, ty: -215 },
]

const CASCADE_COUNT = 48

// Deterministic pseudo-random — same field every render, no Math.random()
// re-rolls, no state needed.
function seeded(i) {
  const x = Math.sin(i * 127.1 + 311.7) * 43758.5453
  return x - Math.floor(x)
}

const PHASES = [
  { title: 'Parsing your profile',        desc: 'Skills, experience and projects are read from your Metabase and structured for semantic matching.' },
  { title: 'Injecting targeted keywords', desc: 'The job description is parsed and missing ATS keywords flow into your strongest bullet points.' },
  { title: 'Synthesis complete',          desc: 'A recruiter-ready .docx, scored live against the exact JD you pasted.' },
]

const TEMPLATE_LINES = [92, 78, 85, 60, 88, 72, 80, 55]

// ── The unparsed document core (rendered twice, clipped into halves) ─────────
function CoreCard() {
  return (
    <div className="w-40 h-56 rounded-xl border border-brand/30 relative overflow-hidden
                    bg-gradient-to-br from-[#1c1620] via-[#141019] to-[#0b0910]
                    shadow-[0_0_60px_-10px_rgba(255,107,53,0.55)]">
      {/* crystalline facets */}
      <div className="absolute inset-0 opacity-60"
        style={{ background: 'linear-gradient(135deg, transparent 30%, rgba(255,107,53,0.14) 45%, transparent 60%)' }} />
      <div className="absolute inset-0"
        style={{ background: 'linear-gradient(45deg, transparent 55%, rgba(255,255,255,0.06) 65%, transparent 75%)' }} />
      {/* faint unparsed text lines */}
      <div className="absolute inset-x-5 top-6 space-y-2.5">
        {[85, 65, 78, 50, 82, 60, 72].map((w, i) => (
          <div key={i} className="h-1.5 rounded bg-white/10" style={{ width: `${w}%` }} />
        ))}
      </div>
      <div className="absolute bottom-4 left-5 w-8 h-8 rounded-md bg-brand/20 border border-brand/40" />
    </div>
  )
}

// ── One falling token in the cascade field ───────────────────────────────────
function CascadeToken({ progress, index }) {
  const r1 = seeded(index)
  const r2 = seeded(index + 100)
  const r3 = seeded(index + 200)
  const left  = 6 + r1 * 88          // vw-relative %
  const delay = r2 * 0.1             // stagger within the phase window
  const size  = 4 + Math.round(r3 * 5)

  const y = useTransform(progress, [0.36 + delay, 0.62 + delay], ['-12vh', '88vh'])
  const opacity = useTransform(
    progress,
    [0.36 + delay, 0.41 + delay, 0.55 + delay, 0.62 + delay],
    [0, 1, 1, 0]
  )

  return (
    <motion.div
      className="absolute top-0 rounded-full bg-brand"
      style={{
        left: `${left}%`, width: size, height: size, y, opacity,
        boxShadow: '0 0 8px rgba(255,107,53,0.8)',
      }}
    />
  )
}

// ── One orbital keyword chip (reveals on cleave, falls with the cascade) ─────
function OrbitChip({ progress, cfg, reduce }) {
  const x = useTransform(progress, [0.22, 0.4, 0.58], [0, cfg.tx, cfg.tx * 1.15])
  const y = useTransform(progress, [0.22, 0.4, 0.58], [0, cfg.ty, cfg.ty + 420])
  const opacity = useTransform(progress, [0.22, 0.28, 0.5, 0.58], [0, 1, 1, 0])
  const scale = useTransform(progress, [0.22, 0.3], [0.5, 1])

  return (
    <motion.div
      className="absolute px-2.5 py-1 rounded-full bg-brand/15 border border-brand/40
                 text-brand text-[11px] font-medium whitespace-nowrap"
      style={{
        x: reduce ? 0 : x, y: reduce ? 0 : y, opacity, scale,
        boxShadow: '0 0 14px rgba(255,107,53,0.35)',
      }}
    >
      {cfg.label}
    </motion.div>
  )
}

// ── One resume-template line that "lights up" as tokens land ─────────────────
function TemplateLine({ progress, index, width }) {
  const fill = useTransform(progress, [0.64 + index * 0.022, 0.72 + index * 0.022], [0, 1])
  return (
    <div className="relative h-2 rounded bg-white/10 overflow-hidden" style={{ width: `${width}%` }}>
      <motion.div
        className="absolute inset-0 rounded origin-left bg-gradient-to-r from-brand/80 to-amber-400/80"
        style={{ scaleX: fill }}
      />
    </div>
  )
}

export default function ScrollJourney() {
  const trackRef = useRef(null)
  const reduce = useReducedMotion()
  const { accessToken } = useAuthStore()
  const [phase, setPhase] = useState(0)

  const { scrollYProgress } = useScroll({ target: trackRef, offset: ['start start', 'end end'] })
  // Spring-smoothed progress gives the "buttery scrub" feel Lenis would —
  // without adding a smooth-scroll dependency.
  const progress = useSpring(scrollYProgress, { stiffness: 100, damping: 30, restDelta: 0.001 })

  // The ONLY React state in the scroll path — a 3-value phase index for the
  // caption card, guarded so it re-renders solely on threshold crossings.
  useMotionValueEvent(progress, 'change', (v) => {
    const next = v < 0.33 ? 0 : v < 0.7 ? 1 : 2
    setPhase((p) => (p === next ? p : next))
  })

  // Core: settle → cleave apart → hand off to the template
  const coreScale   = useTransform(progress, [0, 0.18], [0.9, 1])
  const coreOpacity = useTransform(progress, [0.5, 0.62], [1, 0])
  const leftX  = useTransform(progress, [0.2, 0.4], [0, -110])
  const rightX = useTransform(progress, [0.2, 0.4], [0, 110])
  const leftR  = useTransform(progress, [0.2, 0.4], [0, -12])
  const rightR = useTransform(progress, [0.2, 0.4], [0, 12])

  // Spotlight cone intensifies as the journey begins
  const spotOpacity = useTransform(progress, [0, 0.15], [0.35, 0.85])

  // Template: rises during infusion, glows at synthesis
  const templateY       = useTransform(progress, [0.56, 0.72], ['45vh', '0vh'])
  const templateOpacity = useTransform(progress, [0.56, 0.66], [0, 1])
  const glowOpacity     = useTransform(progress, [0.8, 0.95], [0, 1])

  // Score gauge: 0 → 98, ring + number driven by the same range
  const GAUGE_R = 30
  const circ = 2 * Math.PI * GAUGE_R
  const gaugeDash    = useTransform(progress, [0.8, 0.95], [circ, circ * 0.02])
  const gaugeOpacity = useTransform(progress, [0.78, 0.85], [0, 1])
  const scoreRounded = useTransform(
    useTransform(progress, [0.8, 0.95], [0, 98]),
    (v) => Math.round(v)
  )

  return (
    <section ref={trackRef} id="how-it-works" className="relative h-[400vh] bg-[#050409]">
      <div className="sticky top-0 h-screen overflow-hidden flex items-center justify-center">

        {/* Spotlight from above */}
        <motion.div
          className="absolute inset-0 pointer-events-none"
          style={{
            opacity: spotOpacity,
            background: 'radial-gradient(ellipse 60% 45% at 50% 0%, rgba(255,107,53,0.16), transparent 70%)',
          }}
        />

        {/* Center anchor for core + chips */}
        <div className="relative flex items-center justify-center">
          {/* Core halves — identical card clipped left/right so the split
              genuinely reads as one object cleaving */}
          <motion.div
            className="absolute"
            style={{ x: reduce ? 0 : leftX, rotate: reduce ? 0 : leftR, scale: coreScale, opacity: coreOpacity, willChange: 'transform' }}
          >
            <div style={{ clipPath: 'inset(-40px 50% -40px -40px)' }}><CoreCard /></div>
          </motion.div>
          <motion.div
            className="absolute"
            style={{ x: reduce ? 0 : rightX, rotate: reduce ? 0 : rightR, scale: coreScale, opacity: coreOpacity, willChange: 'transform' }}
          >
            <div style={{ clipPath: 'inset(-40px -40px -40px 50%)' }}><CoreCard /></div>
          </motion.div>

          {/* Orbital keyword chips */}
          {ORBIT_CHIPS.map((cfg) => (
            <OrbitChip key={cfg.label} progress={progress} cfg={cfg} reduce={reduce} />
          ))}
        </div>

        {/* Cascade field — skipped entirely under reduced motion */}
        {!reduce && (
          <div className="absolute inset-0 pointer-events-none" aria-hidden="true">
            {Array.from({ length: CASCADE_COUNT }, (_, i) => (
              <CascadeToken key={i} progress={progress} index={i} />
            ))}
          </div>
        )}

        {/* Glassmorphic resume template */}
        <motion.div
          className="absolute"
          style={{ y: reduce ? 0 : templateY, opacity: templateOpacity, willChange: 'transform' }}
        >
          <div className="relative w-[300px] rounded-2xl border border-white/10 bg-white/[0.05] backdrop-blur-xl p-6">
            {/* synthesis glow */}
            <motion.div
              className="absolute -inset-1 rounded-2xl pointer-events-none"
              style={{ opacity: glowOpacity, boxShadow: '0 0 80px -8px rgba(255,107,53,0.65), inset 0 0 40px -20px rgba(255,170,60,0.4)' }}
            />
            {/* header */}
            <div className="mb-4">
              <div className="h-3 w-32 rounded bg-white/25 mb-2" />
              <div className="h-2 w-44 rounded bg-white/12" />
            </div>
            {/* skill chips */}
            <div className="flex gap-1.5 mb-5">
              {['a', 'b', 'c', 'd'].map((k, i) => (
                <div key={k} className="h-4 rounded-full bg-brand/25 border border-brand/40" style={{ width: 34 + i * 8 }} />
              ))}
            </div>
            {/* lines that light up */}
            <div className="space-y-2.5">
              {TEMPLATE_LINES.map((w, i) => (
                <TemplateLine key={i} progress={progress} index={i} width={w} />
              ))}
            </div>

            {/* score gauge — top-right corner */}
            <motion.div className="absolute -top-8 -right-8 w-20 h-20" style={{ opacity: gaugeOpacity }}>
              <svg viewBox="0 0 80 80" className="w-full h-full -rotate-90">
                <circle cx="40" cy="40" r={GAUGE_R} fill="#0b0910" stroke="rgba(255,255,255,0.1)" strokeWidth="6" />
                <motion.circle
                  cx="40" cy="40" r={GAUGE_R} fill="none"
                  stroke="#34D399" strokeWidth="6" strokeLinecap="round"
                  strokeDasharray={circ}
                  style={{ strokeDashoffset: gaugeDash }}
                />
              </svg>
              <div className="absolute inset-0 flex items-center justify-center">
                <motion.span className="text-lg font-bold font-mono text-score">{scoreRounded}</motion.span>
              </div>
            </motion.div>
          </div>
        </motion.div>

        {/* Phase caption card (the brief's bottom panel) */}
        <div className="absolute inset-x-0 bottom-8 z-20 flex justify-center px-6">
          <div className="w-full max-w-xl card-glass !p-5">
            <div className="flex items-center justify-between mb-3">
              <span className="eyebrow !text-brand">Active Optimization Phase</span>
              <span className="text-xs font-mono text-text-muted">{phase + 1} / 3</span>
            </div>
            <div className="h-16 relative overflow-hidden">
              <AnimatePresence mode="wait">
                <motion.div
                  key={phase}
                  initial={{ y: 15, opacity: 0 }}
                  animate={{ y: 0, opacity: 1 }}
                  exit={{ y: -15, opacity: 0 }}
                  transition={{ duration: 0.2 }}
                  className="absolute inset-0 flex items-center justify-between gap-4"
                >
                  <div className="min-w-0">
                    <p className={`text-base font-semibold ${phase === 2 ? 'text-score' : phase === 1 ? 'text-brand' : 'text-text-primary'}`}>
                      {phase + 1}. {PHASES[phase].title}
                    </p>
                    <p className="text-xs text-text-secondary mt-1 line-clamp-2">{PHASES[phase].desc}</p>
                  </div>
                  {phase === 2 && (
                    <Link
                      to={accessToken ? '/generate' : '/register'}
                      className="btn-primary text-xs whitespace-nowrap flex-shrink-0"
                    >
                      Build yours →
                    </Link>
                  )}
                </motion.div>
              </AnimatePresence>
            </div>
            <div className="mt-3 h-1 bg-white/10 rounded-full overflow-hidden">
              <motion.div
                className="h-full origin-left bg-gradient-to-r from-brand to-accent-magenta"
                style={{ scaleX: scrollYProgress }}
              />
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
