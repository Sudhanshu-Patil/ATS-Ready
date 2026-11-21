import { Link } from 'react-router-dom'
import { useAuthStore } from '../../store/auth'
import { Wordmark } from '../Brand'
import ThemeToggle from '../ThemeToggle'

// Public navigation. Signed-in visitors get one link to their dashboard; no forced redirect.
export default function LandingNav() {
  const { accessToken } = useAuthStore()
  return (
    <header className="sticky top-0 z-40 bg-bg border-b border-bg-border">
      <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
        <Wordmark />
        <nav aria-label="Main" className="hidden sm:flex items-center gap-8 text-sm text-text-secondary">
          <a href="#how-it-works" className="hover:text-text-primary transition-colors">How it works</a>
          <a href="#features" className="hover:text-text-primary transition-colors">What you get</a>
          <a href="#pricing" className="hover:text-text-primary transition-colors">Pricing</a>
        </nav>
        <div className="flex items-center gap-2">
          <ThemeToggle />
          {accessToken ? (
            <Link to="/dashboard" className="btn-primary text-sm !py-1.5">Open dashboard</Link>
          ) : (
            <>
              <Link to="/login" className="text-sm text-text-secondary hover:text-text-primary transition-colors px-3 py-2">Log in</Link>
              <Link to="/register" className="btn-primary text-sm !py-1.5">Start free</Link>
            </>
          )}
        </div>
      </div>
    </header>
  )
}
