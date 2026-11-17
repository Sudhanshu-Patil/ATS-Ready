import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Check } from 'lucide-react'
import { fadeInUp } from '../../lib/motion'
import { useAuthStore } from '../../store/auth'

// Public pricing. Shows the live catalog from the server and falls back to the same numbers if it is unreachable.
const FALLBACK = [
  { id: 'single', label: 'Single', credits: 1, inr: 1000, per_credit_inr: 10 },
  { id: 'starter', label: 'Starter', credits: 6, inr: 4900, per_credit_inr: 8.2 },
  { id: 'hunt', label: 'Job hunt', credits: 15, inr: 9900, per_credit_inr: 6.6 },
  { id: 'power', label: 'Power', credits: 35, inr: 19900, per_credit_inr: 5.7 },
]
const INCLUDES = [
  'Up to 3 tailored resumes, one page each, as Word and PDF, with an ATS score',
  'Up to 3 cover letters, with a length limit if the form has one',
  'Answers to the application form questions (copy and paste)',
  'Interview prep with answers in your own voice',
  'LinkedIn referral messages and follow-up drafts',
]

export default function LandingPricing() {
  const [packs, setPacks] = useState(FALLBACK)
  const { accessToken } = useAuthStore()
  useEffect(() => {
    fetch('/api/billing/catalog').then((r) => (r.ok ? r.json() : null)).then((d) => { if (d?.packs?.length) setPacks(d.packs) }).catch(() => {})
  }, [])

  return (
    <section id="pricing" className="relative bg-[#050409] pb-24 px-6" aria-labelledby="pricing-title">
      <div className="max-w-5xl mx-auto">
        <motion.div initial="hidden" whileInView="visible" viewport={{ once: true, margin: '-80px' }} variants={fadeInUp} className="text-center mb-10">
          <p className="eyebrow !text-brand mb-3">Pricing</p>
          <h2 id="pricing-title" className="font-display text-3xl sm:text-4xl font-bold text-text-primary">Pay per job. No subscription.</h2>
          <p className="text-text-secondary mt-3 max-w-2xl mx-auto">
            One job credit covers everything for one job. Your first job is free, plus two extra resumes. Credits never expire.
          </p>
        </motion.div>

        <div className="grid lg:grid-cols-5 gap-6">
          <div className="lg:col-span-2 card p-6">
            <h3 className="font-semibold text-text-primary mb-3">One credit, one job</h3>
            <ul className="space-y-2.5">
              {INCLUDES.map((t) => (
                <li key={t} className="flex gap-2 text-sm text-text-secondary"><Check size={15} className="text-score mt-0.5 flex-shrink-0" />{t}</li>
              ))}
            </ul>
            <p className="text-xs text-text-muted mt-4">
              A job is one job description. Starting another posting is another job. A failed first run returns your credit automatically.
            </p>
          </div>

          <div className="lg:col-span-3 grid grid-cols-2 gap-4">
            {packs.map((p) => (
              <div key={p.id} className={`card p-5 flex flex-col ${p.id === 'hunt' ? 'border-brand/50' : ''}`}>
                <div className="flex items-center justify-between">
                  <p className="font-semibold text-text-primary">{p.label}</p>
                  {p.id === 'hunt' && <span className="badge bg-brand-muted text-brand">Popular</span>}
                </div>
                <p className="text-3xl font-bold text-text-primary mt-2">₹{(p.inr / 100).toLocaleString('en-IN')}</p>
                <p className="text-xs text-text-secondary mt-1">
                  {p.credits} job credit{p.credits > 1 ? 's' : ''}{p.credits > 1 ? ` · ₹${p.per_credit_inr} each` : ''}
                </p>
              </div>
            ))}
            <p className="col-span-2 text-xs text-text-muted">
              Prices include taxes. Pay with UPI, cards or netbanking through Razorpay. Outside India, pay in dollars with PayPal.
            </p>
          </div>
        </div>

        <div className="text-center mt-8">
          <Link to={accessToken ? '/dashboard' : '/register'} className="btn-primary text-sm py-3 px-8 inline-block">
            {accessToken ? 'Open your dashboard' : 'Start your first job free'}
          </Link>
        </div>
      </div>
    </section>
  )
}
