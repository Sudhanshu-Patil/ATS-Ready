import { useEffect, useState } from 'react'
import { useOutlet, useLocation, NavLink, useNavigate, Link } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import {
  LayoutDashboard, FileText, Database,
  Settings, LogOut, Zap, ChevronRight,
  BrainCircuit, Mail, Menu, X
} from 'lucide-react'
import { useAuthStore } from '../store/auth'
import { authAPI } from '../api/client'
import ThemeToggle from './ThemeToggle'
import QueuePanel from './QueuePanel'
import { useActivityStore } from '../store/activity'
import toast from 'react-hot-toast'
import clsx from 'clsx'

const NAV = [
  { to: '/dashboard',      icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/generate',       icon: Zap,             label: 'Generate Resume' },
  { to: '/cover-letter',   icon: Mail,            label: 'Cover Letter' },
  { to: '/interview-prep', icon: BrainCircuit,    label: 'Interview Prep' },
  { to: '/metabase',       icon: Database,        label: 'Metabase' },
  { to: '/settings',       icon: Settings,        label: 'Settings' },
]

function NavItem({ to, icon: Icon, label, onClick }) {
  return (
    <NavLink to={to} className="nav-item" onClick={onClick}>
      {({ isActive }) => (
        <>
          {isActive && (
            <motion.div
              layoutId="nav-pill"
              className="absolute inset-0 bg-brand-muted border border-brand/20 rounded-lg"
              transition={{ type: 'spring', bounce: 0.2, duration: 0.5 }}
            />
          )}
          <Icon size={17} className={clsx('relative z-10', isActive ? 'text-brand' : '')} />
          <span className={clsx('relative z-10 text-sm font-medium', isActive ? 'text-brand' : '')}>
            {label}
          </span>
        </>
      )}
    </NavLink>
  )
}

export default function Layout() {
  const { user, logout } = useAuthStore()
  const navigate = useNavigate()
  const location = useLocation()
  const element = useOutlet()
  const [mobileOpen, setMobileOpen] = useState(false)

  // Drawer shouldn't survive a navigation on mobile — otherwise the next
  // page loads underneath it still open.
  useEffect(() => { setMobileOpen(false) }, [location.pathname])

  // Escape closes the mobile drawer.
  useEffect(() => {
    if (!mobileOpen) return undefined
    const onKey = (e) => { if (e.key === 'Escape') setMobileOpen(false) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [mobileOpen])

  // Pick up work already running (reload, other tab) and forget it on logout.
  useEffect(() => {
    useActivityStore.getState().refresh()
    return () => useActivityStore.getState().reset()
  }, [])

  const handleLogout = async () => {
    try { await authAPI.logout() } catch {}
    logout()
    navigate('/login')
    toast.success('Logged out')
  }

  const planColor = {
    free: 'text-text-muted',
    pro:  'text-brand',
    team: 'text-score',
  }[user?.plan || 'free']

  return (
    <div className="flex h-screen overflow-hidden">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[100] focus:px-3 focus:py-2 focus:rounded-lg focus:bg-brand focus:text-white">
        Skip to content
      </a>
      {/* Backdrop — closes the drawer on outside tap, mobile only */}
      {mobileOpen && (
        <div
          aria-hidden="true"
          className="fixed inset-0 bg-black/50 z-40 lg:hidden"
          onClick={() => setMobileOpen(false)}
        />
      )}

      {/* Sidebar — glass panel over the aurora, one of the few backdrop-blur
          surfaces (persistent, singular — not a repeated list, so the perf
          tradeoff that keeps .card solid elsewhere doesn't apply here).
          Below `lg` it's an off-canvas drawer (fixed + translate-x); at
          `lg` and up it's the original static column. */}
      <aside aria-label="Sidebar" className={clsx(
        'w-60 flex-shrink-0 card-glass rounded-none border-y-0 border-l-0 p-0 flex flex-col',
        'fixed inset-y-0 left-0 z-50 transition-transform duration-200 ease-out',
        'lg:static lg:translate-x-0',
        mobileOpen ? 'translate-x-0' : '-translate-x-full'
      )}>
        {/* Logo */}
        <div className="px-5 py-5 border-b border-white/10">
          <div className="flex items-center justify-between gap-2.5">
            <Link to="/dashboard" className="flex items-center gap-2.5 hover:opacity-80 transition-opacity">
              <div className="w-8 h-8 rounded-lg bg-brand flex items-center justify-center shadow-[0_0_16px_-2px_rgba(255,107,53,0.6)]">
                <Zap size={16} className="text-white" />
              </div>
              <span className="font-display font-bold text-text-primary text-lg tracking-tight">ATS-Ready</span>
            </Link>
            <div className="flex items-center gap-1">
              <ThemeToggle />
              <button
                onClick={() => setMobileOpen(false)}
                className="lg:hidden p-1.5 rounded-md text-text-muted hover:text-text-primary hover:bg-white/[0.06] transition-colors"
                aria-label="Close menu"
              >
                <X size={18} />
              </button>
            </div>
          </div>
        </div>

        {/* Nav */}
        <nav className="flex-1 px-3 py-4 space-y-0.5 overflow-y-auto">
          <p className="px-3 pb-2 text-xs font-semibold text-text-muted uppercase tracking-wider">Tools</p>
          {NAV.slice(0, 4).map((item) => <NavItem key={item.to} {...item} onClick={() => setMobileOpen(false)} />)}

          <div className="py-2">
            <div className="border-t border-white/10" />
          </div>

          <p className="px-3 pb-2 text-xs font-semibold text-text-muted uppercase tracking-wider">Manage</p>
          {NAV.slice(4).map((item) => <NavItem key={item.to} {...item} onClick={() => setMobileOpen(false)} />)}
        </nav>

        {/* User block */}
        <div className="px-3 py-4 border-t border-white/10">
          <div className="px-3 py-2.5 rounded-lg bg-white/[0.03] mb-3">
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-xs text-text-secondary">Plan</span>
              <span className={clsx('text-xs font-semibold capitalize', planColor)}>
                {user?.plan || 'free'}
              </span>
            </div>
            {user?.plan === 'free' && (
              <Link to="/settings?section=plan"
                className="flex items-center gap-1 text-xs text-brand hover:text-brand-hover transition-colors">
                Upgrade to Pro <ChevronRight size={12} />
              </Link>
            )}
          </div>

          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-full bg-brand/20 border border-brand/30 flex items-center justify-center text-brand text-sm font-semibold">
              {user?.full_name?.[0]?.toUpperCase() || user?.email?.[0]?.toUpperCase() || '?'}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-text-primary truncate">{user?.full_name || 'User'}</p>
              <p className="text-xs text-text-muted truncate">{user?.email}</p>
            </div>
            <button onClick={handleLogout}
              className="p-1.5 rounded-md text-text-muted hover:text-red-400 hover:bg-red-400/10 transition-colors"
              title="Log out">
              <LogOut size={15} />
            </button>
          </div>
        </div>
      </aside>

      {/* Content column — mobile top bar (hamburger + logo) stacks above
          main below `lg`; hidden entirely once the static sidebar takes
          over. */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <header className="lg:hidden flex-shrink-0 flex items-center justify-between gap-3 px-4 py-3 border-b border-white/10 card-glass rounded-none">
          <button
            onClick={() => setMobileOpen(true)}
            className="p-1.5 -ml-1.5 rounded-md text-text-secondary hover:text-text-primary hover:bg-white/[0.06] transition-colors"
            aria-label="Open menu"
          >
            <Menu size={20} />
          </button>
          <Link to="/dashboard" className="flex items-center gap-2 hover:opacity-80 transition-opacity">
            <div className="w-7 h-7 rounded-lg bg-brand flex items-center justify-center">
              <Zap size={14} className="text-white" />
            </div>
            <span className="font-display font-bold text-text-primary text-base tracking-tight">ATS-Ready</span>
          </Link>
          <ThemeToggle />
        </header>

        {/* Main content — route transitions scoped here via useOutlet(), so the
            sidebar above (and its nav pill) never remounts on navigation. */}
        <main id="main" tabIndex={-1} className="flex-1 overflow-hidden outline-none">
          <AnimatePresence mode="wait" initial={false}>
            <motion.div
              key={location.pathname}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.2 }}
              className="h-full overflow-y-auto"
            >
              {element}
            </motion.div>
          </AnimatePresence>
        </main>
      </div>
      <QueuePanel />
    </div>
  )
}
