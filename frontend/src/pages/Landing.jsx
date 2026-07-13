import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Zap, Mail, BrainCircuit, Sparkles, FileText, ChevronDown } from 'lucide-react'
import { useAuthStore } from '../store/auth'
import { fadeInUp, staggerContainer } from '../lib/motion'
import LandingNav from '../components/landing/LandingNav'
import ScrollJourney from '../components/landing/ScrollJourney'
import FeatureCards from '../components/landing/FeatureCards'
import CursorFX from '../components/landing/CursorFX'

// Public cinematic landing page at "/". Sits OUTSIDE ProtectedRoute/Layout —
// scrolls the window natively, aurora background (mounted globally in
// App.jsx) shows through the hero, journey/feature sections sit on opaque
// near-black so the stage reads cinematic. Dark-committed by design: no
// ThemeToggle here.

const APP_FEATURES = [
  { icon: FileText,     title: 'ATS scoring',    desc: 'Weighted 0–100 grade with a keyword-level breakdown per JD.' },
  { icon: Mail,         title: 'Cover letters',  desc: 'Personalized, tone-adjustable letters — never templated.' },
  { icon: BrainCircuit, title: 'Interview prep', desc: '10 tailored questions with model answers from your real experience.' },
  { icon: Sparkles,     title: 'Job matching',   desc: 'Live listings from 5+ sources, scored against your skills.' },
]

export default function Landing() {
  const { accessToken } = useAuthStore()
  const primaryTo = accessToken ? '/dashboard' : '/register'

  return (
    <div className="min-h-screen custom-cursor-zone">
      <CursorFX />
      <LandingNav />

      {/* ── Hero ──────────────────────────────────────────────────────────── */}
      <header className="relative min-h-screen flex items-center px-6 pt-16">
        <div className="max-w-6xl mx-auto w-full grid lg:grid-cols-2 gap-14 items-center">
          <div>
            <motion.p
              initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }}
              className="eyebrow !text-brand mb-4"
            >
              AI Resume Tailoring
            </motion.p>
            <motion.h1
              initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.08 }}
              className="font-display text-4xl sm:text-5xl lg:text-6xl font-bold text-text-primary leading-[1.05] tracking-tight"
            >
              Your resume,{' '}
              <span className="text-transparent bg-clip-text bg-gradient-to-r from-brand to-accent-magenta">
                rebuilt
              </span>{' '}
              for every job description.
            </motion.h1>
            <motion.p
              initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.16 }}
              className="text-text-secondary text-lg mt-6 max-w-md leading-relaxed"
            >
              Paste a JD. Get an ATS-optimized .docx built from your real
              experience, scored live — in about 30 seconds.
            </motion.p>
            <motion.div
              initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.24 }}
              className="flex items-center gap-3 mt-8"
            >
              <Link to={primaryTo} className="btn-primary text-sm py-3 px-6 flex items-center gap-2">
                <Zap size={15} /> {accessToken ? 'Open Dashboard' : 'Build my resume free'}
              </Link>
              {!accessToken && (
                <Link to="/login" className="btn-ghost text-sm py-3 px-6">
                  Login
                </Link>
              )}
            </motion.div>
          </div>

          {/* Floating mini-core — the journey's protagonist, idling */}
          <motion.div
            initial={{ opacity: 0, scale: 0.92 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.7, delay: 0.2 }}
            className="hidden lg:flex items-center justify-center"
            aria-hidden="true"
          >
            <div className="animate-float">
              <div className="w-52 h-72 rounded-2xl border border-brand/30 relative overflow-hidden
                              bg-gradient-to-br from-[#1c1620] via-[#141019] to-[#0b0910]
                              shadow-[0_0_90px_-16px_rgba(255,107,53,0.6)]">
                <div className="absolute inset-0 opacity-60"
                  style={{ background: 'linear-gradient(135deg, transparent 30%, rgba(255,107,53,0.14) 45%, transparent 60%)' }} />
                <div className="absolute inset-x-6 top-8 space-y-3">
                  {[85, 60, 78, 50, 82, 65, 72, 55].map((w, i) => (
                    <div key={i} className="h-2 rounded bg-white/10" style={{ width: `${w}%` }} />
                  ))}
                </div>
                <div className="absolute bottom-5 left-6 flex gap-1.5">
                  {[40, 52, 34].map((w, i) => (
                    <div key={i} className="h-4 rounded-full bg-brand/25 border border-brand/40" style={{ width: w }} />
                  ))}
                </div>
              </div>
            </div>
          </motion.div>
        </div>

        {/* Scroll hint */}
        <a
          href="#how-it-works"
          className="absolute bottom-8 left-1/2 -translate-x-1/2 flex flex-col items-center gap-1 text-text-muted hover:text-text-secondary transition-colors"
        >
          <span className="text-[11px] font-mono uppercase tracking-[0.18em]">Scroll</span>
          <ChevronDown size={16} className="animate-pulse-slow" />
        </a>
      </header>

      {/* ── The cinematic scroll journey ─────────────────────────────────── */}
      <ScrollJourney />

      {/* ── EXTRACT / INJECT / PERFECT ───────────────────────────────────── */}
      <FeatureCards />

      {/* ── Everything else the platform does ────────────────────────────── */}
      <section className="relative bg-[#050409] pb-24 px-6">
        <div className="max-w-6xl mx-auto">
          <motion.div
            initial="hidden" whileInView="visible" viewport={{ once: true, margin: '-80px' }}
            variants={staggerContainer}
            className="grid grid-cols-2 lg:grid-cols-4 gap-4"
          >
            {APP_FEATURES.map(({ icon: Icon, title, desc }) => (
              <motion.div key={title} variants={fadeInUp} className="card p-5">
                <div className="w-9 h-9 rounded-lg bg-brand-muted flex items-center justify-center mb-3">
                  <Icon size={17} className="text-brand" />
                </div>
                <p className="text-sm font-semibold text-text-primary mb-1">{title}</p>
                <p className="text-xs text-text-secondary leading-relaxed">{desc}</p>
              </motion.div>
            ))}
          </motion.div>
        </div>
      </section>

      {/* ── Final CTA + footer ───────────────────────────────────────────── */}
      <section className="relative bg-[#050409] pb-28 px-6 text-center">
        <motion.div
          initial="hidden" whileInView="visible" viewport={{ once: true, margin: '-60px' }}
          variants={fadeInUp} className="max-w-2xl mx-auto"
        >
          <h2 className="font-display text-3xl sm:text-4xl font-bold text-text-primary mb-4">
            Stop rewriting. Start interviewing.
          </h2>
          <p className="text-text-secondary mb-8">
            3 free resumes a month. No credit card required.
          </p>
          <Link to={primaryTo} className="btn-primary text-sm py-3 px-8 inline-flex items-center gap-2">
            <Zap size={15} /> {accessToken ? 'Open Dashboard' : 'Get started free'}
          </Link>
        </motion.div>
      </section>

      <footer className="border-t border-bg-border bg-[#050409] py-8 px-6">
        <div className="max-w-6xl mx-auto flex items-center justify-between flex-wrap gap-4">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded-md bg-brand flex items-center justify-center">
              <Zap size={12} className="text-white" />
            </div>
            <span className="font-display font-bold text-text-primary text-sm">ATS-Ready</span>
          </div>
          <p className="text-xs text-text-muted">
            © {new Date().getFullYear()} ATS-Ready — AI resume tailoring, honestly.
          </p>
        </div>
      </footer>
    </div>
  )
}
