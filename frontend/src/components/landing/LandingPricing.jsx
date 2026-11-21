import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuthStore } from '../../store/auth'

// Public pricing. Shows the live catalog from the server and falls back to the same numbers if it is unreachable.
const FALLBACK = [
  { id: 'single', label: 'Single', credits: 1, inr: 1000, per_credit_inr: 10 },
  { id: 'starter', label: 'Starter', credits: 6, inr: 4900, per_credit_inr: 8.2 },
  { id: 'hunt', label: 'Job hunt', credits: 15, inr: 9900, per_credit_inr: 6.6 },
  { id: 'power', label: 'Power', credits: 35, inr: 19900, per_credit_inr: 5.7 },
]
const INCLUDES = [
  'Up to 3 one-page resumes as Word and PDF, each with an ATS score',
  'Up to 3 cover letters, with a length limit if the form has one',
  'Answers to the application form questions',
  'Interview prep with answers in your own voice',
  'Referral messages and follow-up drafts',
]

export default function LandingPricing() {
  const [packs, setPacks] = useState(FALLBACK)
  const { accessToken } = useAuthStore()
  useEffect(() => {
    fetch('/api/billing/catalog').then((r) => (r.ok ? r.json() : null)).then((d) => { if (d?.packs?.length) setPacks(d.packs) }).catch(() => {})
  }, [])

  return (
    <section id="pricing" className="scroll-mt-16 border-t border-bg-border" aria-labelledby="pricing-title">
      <div className="max-w-6xl mx-auto px-6 py-24 grid lg:grid-cols-12 gap-x-12 gap-y-10">
        <div className="lg:col-span-4">
          <h2 id="pricing-title" className="font-display text-4xl font-medium tracking-[-0.02em] leading-tight">Pay per job</h2>
          <p className="mt-4 text-text-secondary max-w-xs">No subscription. Your first job is free, with two extra resume credits. Credits never expire.</p>
        </div>

        <div className="lg:col-span-8">
          <div className="grid sm:grid-cols-2 border-y border-bg-border divide-y sm:divide-y-0 sm:divide-x divide-bg-border">
            <div className="py-6 sm:pr-8">
              <p className="font-medium">One credit covers one job</p>
              <ul className="mt-3 space-y-2 text-sm text-text-secondary">
                {INCLUDES.map((t) => <li key={t} className="flex gap-2"><span aria-hidden="true" className="text-text-muted">·</span>{t}</li>)}
              </ul>
              <p className="mt-4 text-xs text-text-muted">A job is one job description. Another posting is another job. If the first run fails, the credit comes back.</p>
            </div>
            <table className="sm:pl-8 py-6 w-full text-sm self-start">
              <caption className="sr-only">Credit packs and prices</caption>
              <thead className="sr-only"><tr><th>Pack</th><th>Credits</th><th>Price</th></tr></thead>
              <tbody>
                {packs.map((p) => (
                  <tr key={p.id} className="border-b last:border-0 border-bg-border">
                    <td className="py-3.5 pr-3 sm:pl-8">
                      <span className="font-medium">{p.label}</span>
                      <span className="block text-xs text-text-muted">{p.credits} job credit{p.credits > 1 ? 's' : ''}{p.credits > 1 ? ` · ₹${p.per_credit_inr} each` : ''}</span>
                    </td>
                    <td className="py-3.5 text-right figure font-mono text-lg pr-1">₹{(p.inr / 100).toLocaleString('en-IN')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-6 flex flex-wrap items-center gap-x-6 gap-y-3">
            <Link to={accessToken ? '/dashboard' : '/register'} className="btn-primary">{accessToken ? 'Open your dashboard' : 'Start your first job free'}</Link>
            <p className="text-xs text-text-muted">Prices include taxes. Pay with UPI, cards or netbanking. Outside India, pay in dollars with PayPal.</p>
          </div>
        </div>
      </div>
    </section>
  )
}
