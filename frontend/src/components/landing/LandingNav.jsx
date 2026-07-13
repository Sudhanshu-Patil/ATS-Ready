import { Link } from 'react-router-dom'
import { Zap } from 'lucide-react'
import { useAuthStore } from '../../store/auth'

// Fixed glass nav for the public landing page. Auth-aware: logged-in users
// (session restored by App.jsx on mount) get a single "Open Dashboard" CTA
// instead of Login / Get Started — no forced redirect, the marketing page
// stays viewable either way.
export default function LandingNav() {
  const { accessToken } = useAuthStore()

  return (
    <nav className="fixed top-0 inset-x-0 z-50 card-glass rounded-none border-x-0 border-t-0 !p-0">
      <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-2.5 hover:opacity-80 transition-opacity">
          <div className="w-8 h-8 rounded-lg bg-brand flex items-center justify-center shadow-[0_0_16px_-2px_rgba(255,107,53,0.6)]">
            <Zap size={16} className="text-white" />
          </div>
          <span className="font-display font-bold text-text-primary text-lg tracking-tight">ATS-Ready</span>
        </Link>

        <div className="hidden sm:flex items-center gap-8">
          <a href="#how-it-works" className="text-sm text-text-secondary hover:text-text-primary transition-colors">
            How it works
          </a>
          <a href="#features" className="text-sm text-text-secondary hover:text-text-primary transition-colors">
            Features
          </a>
        </div>

        <div className="flex items-center gap-3">
          {accessToken ? (
            <Link to="/dashboard" className="btn-primary text-sm py-2">
              Open Dashboard
            </Link>
          ) : (
            <>
              <Link to="/login" className="text-sm text-text-secondary hover:text-text-primary transition-colors px-3 py-2">
                Login
              </Link>
              <Link to="/register" className="btn-primary text-sm py-2">
                Get Started
              </Link>
            </>
          )}
        </div>
      </div>
    </nav>
  )
}
