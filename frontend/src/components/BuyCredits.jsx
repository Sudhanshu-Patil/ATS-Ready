import { useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import clsx from 'clsx'
import api from '../api/client'
import Spinner from './Spinner'

const inr = (paise) => `₹${(paise / 100).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`
const usd = (cents) => `$${(cents / 100).toFixed(2)}`

let razorpayScript
function loadRazorpay() {
  if (window.Razorpay) return Promise.resolve()
  razorpayScript = razorpayScript || new Promise((resolve, reject) => {
    const s = document.createElement('script')
    s.src = 'https://checkout.razorpay.com/v1/checkout.js'
    s.onload = resolve
    s.onerror = () => { razorpayScript = null; reject(new Error('Could not load the payment window')) }
    document.head.appendChild(s)
  })
  return razorpayScript
}

/** The packs, and a way to pay: rupees (UPI, cards, netbanking) with Razorpay, or dollars with PayPal. */
export default function BuyCredits({ onPaid, compact = false }) {
  const [catalog, setCatalog] = useState(null)
  const [busy, setBusy] = useState('')

  useEffect(() => { api.get('/billing/catalog').then(r => setCatalog(r.data)).catch(() => setCatalog({ packs: [] })) }, [])
  if (!catalog) return <div className="py-6 flex justify-center"><Spinner /></div>
  if (!catalog.billing_enabled) return <p className="text-sm text-text-secondary">Payments are not switched on yet.</p>

  const payRazorpay = async (pack) => {
    setBusy(pack.id + 'r')
    try {
      const { data } = await api.post('/billing/checkout', { pack_id: pack.id, provider: 'razorpay' })
      await loadRazorpay()
      const me = await api.get('/auth/me').then(r => r.data).catch(() => ({}))
      new window.Razorpay({
        key: data.key_id, order_id: data.order_id, amount: data.amount, currency: data.currency,
        name: 'ATS-Ready', description: `${pack.label}: ${pack.credits} credit${pack.credits > 1 ? 's' : ''}`,
        prefill: { email: me.email, name: me.full_name },
        theme: { color: '#C2410C' },
        handler: async (resp) => {
          try {
            await api.post('/billing/razorpay/verify', {
              order_id: resp.razorpay_order_id, payment_id: resp.razorpay_payment_id, signature: resp.razorpay_signature,
            })
            toast.success(`${pack.credits} credit${pack.credits > 1 ? 's' : ''} added`)
            window.dispatchEvent(new Event('ats-credits-changed'))
            onPaid?.()
          } catch {
            toast.error('We could not confirm the payment yet. If money was taken, your credits will appear shortly.')
            window.dispatchEvent(new Event('ats-credits-changed'))
          }
        },
        modal: { ondismiss: () => setBusy('') },
      }).open()
    } catch (err) {
      toast.error(err.response?.data?.detail || err.message || 'Could not start the payment')
    } finally {
      setBusy('')
    }
  }

  const payPaypal = async (pack) => {
    setBusy(pack.id + 'p')
    try {
      const { data } = await api.post('/billing/checkout', { pack_id: pack.id, provider: 'paypal' })
      window.location.href = data.approve_url
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Could not start the payment')
      setBusy('')
    }
  }

  return (
    <div className={clsx('grid gap-3 grid-cols-2', !compact && 'lg:grid-cols-4')}>
      {catalog.packs.map((p) => (
        <div key={p.id} className={clsx('rounded-xl border p-4 flex flex-col gap-2', p.id === 'hunt' ? 'border-text-muted bg-bg-hover' : 'border-bg-border')}>
          <div className="flex items-baseline justify-between">
            <p className="font-semibold text-text-primary">{p.label}</p>
            {p.id === 'hunt' && <span className="badge bg-bg-hover text-brand">Popular</span>}
          </div>
          <p className="text-2xl font-semibold text-text-primary">{inr(p.inr)}</p>
          <p className="text-xs text-text-secondary">
            {p.credits} job credit{p.credits > 1 ? 's' : ''}{p.credits > 1 ? ` · ₹${p.per_credit_inr} each` : ''}
          </p>
          {catalog.razorpay && (
            <button disabled={!!busy} onClick={() => payRazorpay(p)} className="btn-primary text-sm py-2 mt-auto">
              {busy === p.id + 'r' ? 'Opening…' : `Pay ${inr(p.inr)}`}
            </button>
          )}
          {catalog.paypal && p.usd > 0 && (
            <button disabled={!!busy} onClick={() => payPaypal(p)} className="btn-ghost text-xs py-1.5" title="For buyers outside India">
              {busy === p.id + 'p' ? 'Opening…' : `${usd(p.usd)} PayPal`}
            </button>
          )}
        </div>
      ))}
    </div>
  )
}
