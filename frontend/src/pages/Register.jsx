import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Zap, Eye, EyeOff } from 'lucide-react'
import { useAuthStore } from '../store/auth'
import { authAPI } from '../api/client'
import Spinner from '../components/Spinner'
import GoogleButton from '../components/GoogleButton'
import ThemeToggle from '../components/ThemeToggle'
import toast from 'react-hot-toast'

export default function Register() {
  const [fullName, setFullName] = useState('')
  const [email, setEmail]       = useState('')
  const [password, setPassword] = useState('')
  const [showPass, setShowPass] = useState(false)
  const [loading, setLoading]   = useState(false)
  const { login } = useAuthStore()
  const navigate = useNavigate()

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (password.length < 8) {
      toast.error('Password must be at least 8 characters')
      return
    }
    setLoading(true)
    try {
      const res = await authAPI.register(email, password, fullName)
      login(res.data.access_token, {
        id:        res.data.user_id,
        email:     res.data.email,
        full_name: res.data.full_name,
        plan:      res.data.plan,
      })
      toast.success('Account created! Fill in your Metabase to get started.')
      navigate('/metabase')
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Registration failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <ThemeToggle className="fixed top-5 right-5" />
      <div className="w-full max-w-sm">
        {/* Logo */}
        <motion.div
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="flex items-center gap-2.5 justify-center mb-8"
        >
          <div className="w-9 h-9 rounded-xl bg-brand flex items-center justify-center shadow-[0_0_20px_-3px_rgba(255,107,53,0.6)]">
            <Zap size={18} className="text-white" />
          </div>
          <span className="font-display font-bold text-text-primary text-xl tracking-tight">ATS-Ready</span>
        </motion.div>

        {/* Card */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.08 }}
          className="card-glass"
        >
          <h1 className="font-display text-2xl font-bold text-text-primary mb-1">Create account</h1>
          <p className="text-sm text-text-secondary mb-6">
            Start with 3 free resumes/month. No credit card required.
          </p>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-text-secondary mb-1.5">
                Full name
              </label>
              <input
                type="text"
                className="input"
                placeholder="Priya Sharma"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                required
                autoFocus
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-text-secondary mb-1.5">
                Email
              </label>
              <input
                type="email"
                className="input"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-text-secondary mb-1.5">
                Password
              </label>
              <div className="relative">
                <input
                  type={showPass ? 'text' : 'password'}
                  className="input pr-10"
                  placeholder="Min. 8 characters"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPass(!showPass)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-secondary"
                >
                  {showPass ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
              {password && password.length < 8 && (
                <p className="text-xs text-red-400 mt-1">At least 8 characters required</p>
              )}
            </div>

            <button
              type="submit"
              disabled={loading || password.length < 8}
              className="btn-primary w-full flex items-center justify-center gap-2 mt-2"
            >
              {loading && <Spinner size="sm" color="white" />}
              {loading ? 'Creating account…' : 'Create account'}
            </button>
          </form>
          <GoogleButton />
        </motion.div>

        <p className="text-center text-sm text-text-secondary mt-5">
          Already have an account?{' '}
          <Link to="/login" className="text-brand hover:text-brand-hover font-medium transition-colors">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  )
}
