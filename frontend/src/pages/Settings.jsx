import { useState, useEffect } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Settings as SettingsIcon } from 'lucide-react'
import { useAuthStore } from '../store/auth'
import { authAPI, billingAPI } from '../api/client'
import BuyCredits from '../components/BuyCredits'
import { useCreditsStore } from '../store/credits'
import { fadeInUp } from '../lib/motion'
import Spinner from '../components/Spinner'
import toast from 'react-hot-toast'
import clsx from 'clsx'

const SECTIONS = ['account', 'security', 'billing']

export default function Settings() {
  const { user, login, accessToken } = useAuthStore()
  // Deep-linkable sections: /settings?section=plan (used by the "Upgrade to
  // Pro" links in the sidebar and dashboard). The effect — not just the
  // useState initializer — matters: navigating from /settings to
  // /settings?section=plan changes only the search params, so the component
  // doesn't remount (Layout keys its route transition on pathname alone).
  const [searchParams] = useSearchParams()
  const sectionParam = searchParams.get('section') === 'plan' ? 'billing' : searchParams.get('section')   // old links
  const [activeSection, setActiveSection] = useState(
    SECTIONS.includes(sectionParam) ? sectionParam : 'account'
  )

  useEffect(() => {
    if (sectionParam && SECTIONS.includes(sectionParam)) {
      setActiveSection(sectionParam)
    }
  }, [sectionParam])

  return (
    <div className="p-4 sm:p-8 max-w-5xl mx-auto">
      <motion.div initial="hidden" animate="visible" variants={fadeInUp} className="mb-8">
        <div className="flex items-center gap-3 mb-2">
          <div className="w-9 h-9 rounded-xl bg-brand-muted flex items-center justify-center">
            <SettingsIcon size={18} className="text-brand" />
          </div>
          <h1 className="font-display text-2xl font-bold text-text-primary">Settings</h1>
        </div>
        <p className="text-text-secondary">Manage your account, credits and invites.</p>
      </motion.div>

      <div className="flex flex-col sm:flex-row gap-4 sm:gap-6">
        {/* Sidebar nav — self-contained active styling (not the shared
            .nav-item class, which Layout.jsx's main sidebar now drives via a
            Framer layoutId pill rather than a static CSS active state).
            Horizontal pill row below `sm`, vertical sidebar at `sm` and up. */}
        <div className="sm:w-44 flex-shrink-0">
          <nav className="flex flex-row gap-2 sm:flex-col sm:space-y-1 sm:gap-0">
            {SECTIONS.map(s => (
              <button
                key={s}
                onClick={() => setActiveSection(s)}
                className={clsx(
                  'text-left px-3 py-2.5 rounded-lg text-sm font-medium capitalize transition-colors',
                  'flex-1 sm:flex-none sm:w-full',
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
          {activeSection === 'billing'  && <BillingSection />}
        </div>
      </div>
    </div>
  )
}

function AccountSection({ user, login, accessToken }) {
  const [name, setName]   = useState(user?.full_name || '')
  const [saving, setSaving] = useState(false)
  const [verified, setVerified] = useState(null)   // null = loading
  const [sendingVerify, setSendingVerify] = useState(false)

  useEffect(() => {
    authAPI.me().then(r => setVerified(r.data.is_verified)).catch(() => {})
  }, [])

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

  const resendVerification = async () => {
    setSendingVerify(true)
    try {
      const r = await authAPI.sendVerification()
      if (r.data.already_verified) setVerified(true)
      else toast.success('Verification email sent — check your inbox')
    } catch { toast.error('Could not send verification email') }
    finally { setSendingVerify(false) }
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
        <div className="flex items-center flex-wrap gap-2 mt-1.5">
          {verified === true && (
            <span className="badge bg-score-muted text-score">✓ Verified</span>
          )}
          {verified === false && (
            <>
              <span className="badge bg-yellow-400/10 text-yellow-400">Unverified</span>
              <button
                onClick={resendVerification}
                disabled={sendingVerify}
                className="text-xs text-brand hover:text-brand-hover transition-colors disabled:opacity-50"
              >
                {sendingVerify ? 'Sending…' : 'Resend verification email'}
              </button>
            </>
          )}
          <p className="text-xs text-text-muted">Email cannot be changed.</p>
        </div>
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

const PASSWORD_FIELDS = [
  { key: 'current_password', label: 'Current password', autoComplete: 'current-password' },
  { key: 'new_password',     label: 'New password',     autoComplete: 'new-password' },
  { key: 'confirm',          label: 'Confirm new password', autoComplete: 'new-password' },
]

function SecuritySection() {
  const { user, logout } = useAuthStore()
  const navigate = useNavigate()
  const [form, setForm]   = useState({ current_password: '', new_password: '', confirm: '' })
  const [saving, setSaving] = useState(false)

  const save = async () => {
    if (form.new_password !== form.confirm) { toast.error('Passwords do not match'); return }
    if (form.new_password.length < 8)       { toast.error('Min 8 characters'); return }
    setSaving(true)
    try {
      await authAPI.changePassword(form.current_password, form.new_password)
      toast.success('Password changed. Other devices were signed out.')
      setForm({ current_password: '', new_password: '', confirm: '' })
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to change password')
    } finally { setSaving(false) }
  }

  const signOutEverywhere = async () => {
    try {
      await authAPI.logoutAll()
      logout()
      navigate('/login')
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Could not sign out everywhere')
    }
  }

  return (
    <motion.div initial="hidden" animate="visible" variants={fadeInUp} className="space-y-6">
      <form className="card space-y-4" onSubmit={e => { e.preventDefault(); save() }}>
        <h2 className="font-semibold text-text-primary">Change password</h2>
        {PASSWORD_FIELDS.map(({ key, label, autoComplete }) => (
          <div key={key}>
            <label htmlFor={`pw-${key}`} className="block text-sm font-medium text-text-secondary mb-1.5">
              {label}
            </label>
            <input
              id={`pw-${key}`}
              type="password"
              autoComplete={autoComplete}
              className="input"
              value={form[key]}
              onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))}
            />
          </div>
        ))}
        <button type="submit" disabled={saving} className="btn-primary text-sm flex items-center gap-2">
          {saving && <Spinner size="sm" color="white" />}
          {saving ? 'Changing…' : 'Change password'}
        </button>
      </form>

      <div className="card space-y-3">
        <h2 className="font-semibold text-text-primary">Sessions</h2>
        <p className="text-sm text-text-secondary">Sign out on every device where you are logged in, including this one.</p>
        <button onClick={signOutEverywhere} className="btn-ghost text-sm">Sign out everywhere</button>
      </div>

      <PrivacySection email={user?.email} />
    </motion.div>
  )
}

function PrivacySection({ email }) {
  const [confirming, setConfirming] = useState(false)
  const [confirmEmail, setConfirmEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)

  const download = async () => {
    try {
      const { data } = await authAPI.exportData()
      const url = URL.createObjectURL(data)
      const a = Object.assign(document.createElement('a'), { href: url, download: 'ats-ready-data.json' })
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      toast.error('Could not export your data')
    }
  }

  const remove = async (e) => {
    e.preventDefault()
    setBusy(true)
    try {
      await authAPI.deleteAccount(confirmEmail, password)
      // A full page load drops every in-memory store; a client-side logout() here races the
      // protected route, which bounces to /login before the landing page can show.
      window.location.assign('/')
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Could not delete the account')
      setBusy(false)
    }
  }

  return (
    <div className="card space-y-4">
      <h2 className="font-semibold text-text-primary">Your data</h2>
      <div>
        <p className="text-sm text-text-secondary mb-2">Download everything we store about you as a JSON file.</p>
        <button onClick={download} className="btn-ghost text-sm">Download my data</button>
      </div>
      <div className="border-t border-bg-border pt-4">
        <h3 className="text-sm font-medium text-red-400 mb-1">Delete account</h3>
        <p className="text-sm text-text-secondary mb-3">
          Permanently deletes your profile, resumes, cover letters, interview prep and generated files. This cannot be undone.
        </p>
        {!confirming ? (
          <button onClick={() => setConfirming(true)} className="btn-ghost text-sm text-red-400">Delete my account…</button>
        ) : (
          <form onSubmit={remove} className="space-y-3">
            <div>
              <label htmlFor="del-email" className="block text-sm font-medium text-text-secondary mb-1.5">
                Type your email ({email}) to confirm
              </label>
              <input id="del-email" type="email" autoComplete="off" className="input" required
                     value={confirmEmail} onChange={e => setConfirmEmail(e.target.value)} />
            </div>
            <div>
              <label htmlFor="del-pw" className="block text-sm font-medium text-text-secondary mb-1.5">
                Password (leave empty if you only use Google)
              </label>
              <input id="del-pw" type="password" autoComplete="current-password" className="input"
                     value={password} onChange={e => setPassword(e.target.value)} />
            </div>
            <div className="flex gap-2">
              <button type="submit" disabled={busy || !confirmEmail} className="btn-primary text-sm bg-red-600 hover:bg-red-500">
                {busy ? 'Deleting…' : 'Delete everything'}
              </button>
              <button type="button" onClick={() => setConfirming(false)} className="btn-ghost text-sm">Cancel</button>
            </div>
          </form>
        )}
      </div>
    </div>
  )
}

// Credits: balance, packs, invite link and the ledger. PayPal returns here with ?token=<order id>.
function BillingSection() {
  const { credits, referral, ledger, billingEnabled, refresh } = useCreditsStore()

  useEffect(() => {
    const orderId = new URLSearchParams(window.location.search).get('token')
    if (orderId) {
      window.history.replaceState({}, '', '/settings?section=billing')
      billingAPI.sync(orderId)
        .then(() => { toast.success('Payment received. Credits added.'); refresh() })
        .catch(() => toast.error('Could not confirm your PayPal payment'))
    } else {
      refresh()
    }
  }, [])  // eslint-disable-line react-hooks/exhaustive-deps

  const copy = async () => {
    try { await navigator.clipboard.writeText(referral.link); toast.success('Invite link copied') }
    catch { toast.error('Could not copy. Select the link and copy it.') }
  }
  const REASON = { signup: 'Welcome gift', purchase: 'Purchase', referral: 'Friend joined', unlock: 'Unlocked a job',
                   refund: 'Refund (it did not work out)', admin: 'Added by us' }

  return (
    <motion.div initial="hidden" animate="visible" variants={fadeInUp} className="space-y-5">
      <div className="card">
        <h2 className="font-semibold text-text-primary mb-3">Your credits</h2>
        <div className="flex gap-6 flex-wrap">
          <div><p className="text-3xl font-bold text-text-primary" data-testid="credits-job">{credits?.job ?? '…'}</p>
            <p className="text-xs text-text-muted">job credits</p></div>
          <div><p className="text-3xl font-bold text-text-primary" data-testid="credits-resume">{credits?.resume ?? '…'}</p>
            <p className="text-xs text-text-muted">resume-only credits</p></div>
        </div>
        <p className="text-xs text-text-muted mt-3">
          A job credit unlocks one job completely: up to 3 resumes, 3 cover letters, the application answers,
          interview prep and reach-out messages. A resume-only credit unlocks just that job's resume. Credits never expire.
        </p>
      </div>

      {billingEnabled && (
        <div className="card space-y-3">
          <h2 className="font-semibold text-text-primary">Get more credits</h2>
          <BuyCredits />
        </div>
      )}

      {referral && (
        <div className="card space-y-3">
          <h2 className="font-semibold text-text-primary">Invite friends, get credits</h2>
          <p className="text-sm text-text-secondary">
            You get {referral.reward} free job credit when a friend joins with your link, verifies their email and
            starts their first job (up to {referral.cap}). They get their free starter credits too.
          </p>
          <div className="flex gap-2">
            <input readOnly aria-label="Your invite link" className="input text-sm" value={referral.link} onFocus={(e) => e.target.select()} />
            <button onClick={copy} className="btn-primary text-sm px-4">Copy</button>
          </div>
          <p className="text-xs text-text-muted">{referral.rewarded} rewarded · {referral.pending} waiting to start their first job</p>
        </div>
      )}

      {ledger.length > 0 && (
        <div className="card">
          <h2 className="font-semibold text-text-primary mb-3">History</h2>
          <ul className="divide-y divide-bg-border">
            {ledger.map((r) => (
              <li key={r.id} className="py-2 flex items-center justify-between text-sm">
                <span className="text-text-secondary">{REASON[r.reason] || r.reason}
                  <span className="text-text-muted"> · {r.kind === 'job' ? 'job' : 'resume-only'} · {new Date(r.created_at).toLocaleDateString()}</span></span>
                <span className={clsx('font-mono', r.delta > 0 ? 'text-score' : 'text-text-secondary')}>{r.delta > 0 ? '+' : ''}{r.delta}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </motion.div>
  )
}
