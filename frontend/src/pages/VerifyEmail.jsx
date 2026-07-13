import { useEffect, useState, useRef } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Zap, CheckCircle, XCircle } from 'lucide-react'
import { authAPI } from '../api/client'
import Spinner from '../components/Spinner'

export default function VerifyEmail() {
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token') || ''
  const [state, setState] = useState(token ? 'verifying' : 'invalid') // verifying | done | invalid
  const ran = useRef(false)

  useEffect(() => {
    if (!token || ran.current) return
    ran.current = true // StrictMode double-mount guard — verify once
    authAPI.verifyEmail(token)
      .then(() => setState('done'))
      .catch(() => setState('invalid'))
  }, [token])

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <div className="w-full max-w-sm text-center">
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
          className="card-glass py-10"
        >
          {state === 'verifying' && (
            <>
              <Spinner size="lg" color="brand" className="mx-auto mb-4" />
              <p className="text-text-secondary text-sm">Verifying your email…</p>
            </>
          )}
          {state === 'done' && (
            <>
              <CheckCircle size={40} className="text-score mx-auto mb-3" />
              <h1 className="font-display text-xl font-bold text-text-primary mb-2">Email verified</h1>
              <p className="text-sm text-text-secondary mb-6">Your account is confirmed. You're all set.</p>
              <Link to="/dashboard" className="btn-primary text-sm inline-flex">Go to Dashboard</Link>
            </>
          )}
          {state === 'invalid' && (
            <>
              <XCircle size={40} className="text-red-400 mx-auto mb-3" />
              <h1 className="font-display text-xl font-bold text-text-primary mb-2">Link invalid or expired</h1>
              <p className="text-sm text-text-secondary mb-6">
                Request a fresh verification email from Settings after logging in.
              </p>
              <Link to="/login" className="btn-primary text-sm inline-flex">Back to login</Link>
            </>
          )}
        </motion.div>
      </div>
    </div>
  )
}
