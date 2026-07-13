import { useState } from 'react'
import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Zap, MailCheck } from 'lucide-react'
import { authAPI } from '../api/client'
import Spinner from '../components/Spinner'
import ThemeToggle from '../components/ThemeToggle'
import toast from 'react-hot-toast'

export default function ForgotPassword() {
  const [email, setEmail] = useState('')
  const [loading, setLoading] = useState(false)
  const [sent, setSent] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    try {
      await authAPI.forgotPassword(email)
      setSent(true)
    } catch {
      // Same UX either way — the endpoint never reveals whether the
      // account exists, so neither should client-side error handling.
      toast.error('Something went wrong — please try again')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <ThemeToggle className="fixed top-5 right-5" />
      <div className="w-full max-w-sm">
        <motion.div
          initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}
          className="flex items-center gap-2.5 justify-center mb-8"
        >
          <div className="w-9 h-9 rounded-xl bg-brand flex items-center justify-center shadow-[0_0_20px_-3px_rgba(255,107,53,0.6)]">
            <Zap size={18} className="text-white" />
          </div>
          <span className="font-display font-bold text-text-primary text-xl tracking-tight">ATS-Ready</span>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, delay: 0.08 }}
          className="card-glass"
        >
          {sent ? (
            <div className="text-center py-4">
              <MailCheck size={36} className="text-score mx-auto mb-3" />
              <h1 className="font-display text-xl font-bold text-text-primary mb-2">Check your inbox</h1>
              <p className="text-sm text-text-secondary">
                If <span className="text-text-primary">{email}</span> is registered,
                a reset link is on its way. It expires in 30 minutes.
              </p>
            </div>
          ) : (
            <>
              <h1 className="font-display text-2xl font-bold text-text-primary mb-1">Forgot password</h1>
              <p className="text-sm text-text-secondary mb-6">
                Enter your email and we'll send you a reset link.
              </p>

              <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-text-secondary mb-1.5">Email</label>
                  <input
                    type="email"
                    className="input"
                    placeholder="you@example.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                    autoFocus
                  />
                </div>
                <button
                  type="submit"
                  disabled={loading}
                  className="btn-primary w-full flex items-center justify-center gap-2 mt-2"
                >
                  {loading && <Spinner size="sm" color="white" />}
                  {loading ? 'Sending…' : 'Send reset link'}
                </button>
              </form>
            </>
          )}
        </motion.div>

        <p className="text-center text-sm text-text-secondary mt-5">
          Remembered it?{' '}
          <Link to="/login" className="text-brand hover:text-brand-hover font-medium transition-colors">
            Back to login
          </Link>
        </p>
      </div>
    </div>
  )
}
