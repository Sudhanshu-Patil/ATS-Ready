import { useState, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Settings as SettingsIcon } from 'lucide-react'
import { useAuthStore } from '../store/auth'
import { authAPI, billingAPI } from '../api/client'
import { fadeInUp } from '../lib/motion'
import Spinner from '../components/Spinner'
import toast from 'react-hot-toast'
import clsx from 'clsx'

const SECTIONS = ['account', 'security', 'plan']

export default function Settings() {
  const { user, login, accessToken } = useAuthStore()
  // Deep-linkable sections: /settings?section=plan (used by the "Upgrade to
  // Pro" links in the sidebar and dashboard). The effect — not just the
  // useState initializer — matters: navigating from /settings to
  // /settings?section=plan changes only the search params, so the component
  // doesn't remount (Layout keys its route transition on pathname alone).
  const [searchParams] = useSearchParams()
  const sectionParam = searchParams.get('section')
  const [activeSection, setActiveSection] = useState(
    SECTIONS.includes(sectionParam) ? sectionParam : 'account'
  )

  useEffect(() => {
    if (sectionParam && SECTIONS.includes(sectionParam)) {
      setActiveSection(sectionParam)
    }
  }, [sectionParam])

  return (
    <div className="p-8 max-w-5xl mx-auto">
      <motion.div initial="hidden" animate="visible" variants={fadeInUp} className="mb-8">
        <div className="flex items-center gap-3 mb-2">
          <div className="w-9 h-9 rounded-xl bg-brand-muted flex items-center justify-center">
            <SettingsIcon size={18} className="text-brand" />
          </div>
          <h1 className="font-display text-2xl font-bold text-text-primary">Settings</h1>
        </div>
        <p className="text-text-secondary">Manage your account and subscription.</p>
      </motion.div>

      <div className="flex gap-6">
        {/* Sidebar nav — self-contained active styling (not the shared
            .nav-item class, which Layout.jsx's main sidebar now drives via a
            Framer layoutId pill rather than a static CSS active state). */}
        <div className="w-44 flex-shrink-0">
          <nav className="space-y-1">
            {SECTIONS.map(s => (
              <button
                key={s}
                onClick={() => setActiveSection(s)}
                className={clsx(
                  'w-full text-left px-3 py-2.5 rounded-lg text-sm font-medium capitalize transition-colors',
                  activeSection === s
                    ? 'bg-brand-muted text-brand border border-brand/20'
                    : 'text-text-secondary hover:text-text-primary hover:bg-bg-hover border border-transparent'
                )}
              >
                {s}
              </button>
            ))}
          </nav>
        </div>

        {/* Content */}
        <div className="flex-1">
          {activeSection === 'account'  && <AccountSection user={user} login={login} accessToken={accessToken} />}
          {activeSection === 'security' && <SecuritySection />}
          {activeSection === 'plan'     && <PlanSection user={user} />}
        </div>
      </div>
    </div>
  )
}

function AccountSection({ user, login, accessToken }) {
  const [name, setName]   = useState(user?.full_name || '')
  const [saving, setSaving] = useState(false)

  const save = async () => {
    setSaving(true)
    try {
      await authAPI.updateMe({ full_name: name })
      login(accessToken, { ...user, full_name: name })
      toast.success('Name updated')
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Update failed')
    } finally { setSaving(false) }
  }

  return (
    <motion.div initial="hidden" animate="visible" variants={fadeInUp} className="card space-y-4">
      <h2 className="font-semibold text-text-primary">Account</h2>
      <div>
        <label className="block text-sm font-medium text-text-secondary mb-1.5">Full name</label>
        <input className="input" value={name} onChange={e => setName(e.target.value)} />
      </div>
      <div>
        <label className="block text-sm font-medium text-text-secondary mb-1.5">Email</label>
        <input className="input opacity-60" value={user?.email || ''} disabled />
        <p className="text-xs text-text-muted mt-1">Email cannot be changed.</p>
      </div>
      <div className="pt-2">
        <button onClick={save} disabled={saving} className="btn-primary text-sm flex items-center gap-2">
          {saving && <Spinner size="sm" color="white" />}
          {saving ? 'Saving…' : 'Save changes'}
        </button>
      </div>
    </motion.div>
  )
}

function SecuritySection() {
  const [form, setForm]   = useState({ current_password: '', new_password: '', confirm: '' })
  const [saving, setSaving] = useState(false)

  const save = async () => {
    if (form.new_password !== form.confirm) { toast.error('Passwords do not match'); return }
    if (form.new_password.length < 8)       { toast.error('Min 8 characters'); return }
    setSaving(true)
    try {
      await authAPI.changePassword(form.current_password, form.new_password)
      toast.success('Password changed')
      setForm({ current_password: '', new_password: '', confirm: '' })
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to change password')
    } finally { setSaving(false) }
  }

  return (
    <motion.div initial="hidden" animate="visible" variants={fadeInUp} className="card space-y-4">
      <h2 className="font-semibold text-text-primary">Change password</h2>
      {['current_password', 'new_password', 'confirm'].map(key => (
        <div key={key}>
          <label className="block text-sm font-medium text-text-secondary mb-1.5 capitalize">
            {key.replace(/_/g, ' ')}
          </label>
          <input
            type="password"
            className="input"
            value={form[key]}
            onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))}
          />
        </div>
      ))}
      <button onClick={save} disabled={saving} className="btn-primary text-sm flex items-center gap-2">
        {saving && <Spinner size="sm" color="white" />}
        {saving ? 'Changing…' : 'Change password'}
      </button>
    </motion.div>
  )
}

function PlanSection({ user }) {
  const [loading, setLoading] = useState(false)

  const handleUpgrade = async (plan) => {
    setLoading(true)
    try {
      const res = await billingAPI.checkout(plan)
      if (res.data.checkout_url) {
        window.location.href = res.data.checkout_url
      } else {
        toast(res.data.message || 'Billing not enabled yet.', { icon: 'ℹ️' })
      }
    } catch { toast.error('Could not start checkout') }
    finally { setLoading(false) }
  }

  const plans = [
    { id: 'free', label: 'Free', price: '$0', features: ['3 resumes/month', 'ATS scoring', 'DOCX download'], current: user?.plan === 'free' },
    { id: 'pro',  label: 'Pro',  price: '$19/mo', features: ['Unlimited resumes', 'Cover letters', 'Priority AI'], current: user?.plan === 'pro' },
    { id: 'team', label: 'Team', price: '$49/mo', features: ['Everything in Pro', 'API access', '5 seats'], current: user?.plan === 'team' },
  ]

  return (
    <motion.div initial="hidden" animate="visible" variants={fadeInUp} className="space-y-4">
      <h2 className="font-semibold text-text-primary">Subscription</h2>
      {plans.map(plan => (
        <div key={plan.id} className={clsx('card flex items-center justify-between', plan.current && 'border-brand/40 bg-brand/5')}>
          <div>
            <div className="flex items-center gap-2 mb-1">
              <p className="font-semibold text-text-primary">{plan.label}</p>
              {plan.current && <span className="badge bg-brand-muted text-brand">Current</span>}
            </div>
            <p className="text-sm text-text-secondary mb-2">{plan.price}</p>
            <ul className="space-y-0.5">
              {plan.features.map(f => <li key={f} className="text-xs text-text-muted">✓ {f}</li>)}
            </ul>
          </div>
          {!plan.current && plan.id !== 'free' && (
            <button
              onClick={() => handleUpgrade(plan.id)}
              disabled={loading}
              className="btn-primary text-sm flex-shrink-0"
            >
              Upgrade
            </button>
          )}
        </div>
      ))}
    </motion.div>
  )
}
