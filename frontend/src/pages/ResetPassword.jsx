import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Zap, Eye, EyeOff } from 'lucide-react'
import { authAPI } from '../api/client'
import Spinner from '../components/Spinner'
import ThemeToggle from '../components/ThemeToggle'
import toast from 'react-hot-toast'

export default function ResetPassword() {
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token') || ''
  const navigate = useNavigate()

  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [showPass, setShowPass] = useState(false)
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (password !== confirm) { toast.error('Passwords do not match'); return }
    if (password.length < 8)  { toast.error('Password must be at least 8 characters'); return }
    setLoading(true)
    try {
      await authAPI.resetPassword(token, password)
      toast.success('Password reset — log in with your new password')
      navigate('/login')
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Reset link is invalid or has expired')
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
          <h1 className="font-display text-2xl font-bold text-text-primary mb-1">Set a new password</h1>
          <p className="text-sm text-text-secondary mb-6">
            Choose a new password for your account.
          </p>

          {!token ? (
            <p className="text-sm text-red-400">
              Missing reset token — use the link from your email, or{' '}
              <Link to="/forgot-password" className="underline">request a new one</Link>.
            </p>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-text-secondary mb-1.5">New password</label>
                <div className="relative">
                  <input
                    type={showPass ? 'text' : 'password'}
                    className="input pr-10"
                    placeholder="Min. 8 characters"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    autoFocus
                  />
                  <button
                    type="button"
                    onClick={() => setShowPass(!showPass)}
                    aria-label={showPass ? "Hide password" : "Show password"}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-secondary"
                  >
                    {showPass ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-text-secondary mb-1.5">Confirm password</label>
                <input
                  type={showPass ? 'text' : 'password'}
                  className="input"
                  placeholder="Repeat the new password"
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  required
                />
                {confirm && confirm !== password && (
                  <p className="text-xs text-red-400 mt-1">Passwords do not match</p>
                )}
              </div>
              <button
                type="submit"
                disabled={loading || password.length < 8 || password !== confirm}
                className="btn-primary w-full flex items-center justify-center gap-2 mt-2"
              >
                {loading && <Spinner size="sm" color="white" />}
                {loading ? 'Resetting…' : 'Reset password'}
              </button>
            </form>
          )}
        </motion.div>

        <p className="text-center text-sm text-text-secondary mt-5">
          <Link to="/login" className="text-brand hover:text-brand-hover font-medium transition-colors">
            Back to login
          </Link>
        </p>
      </div>
    </div>
  )
}
