import { Suspense, useEffect, useState } from 'react'
import { useOutlet, useLocation, NavLink, useNavigate, Link } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import {
  LayoutDashboard, FileText, UserRound,
  Settings, LogOut, ChevronRight,
  BrainCircuit, Mail, Menu, X, BarChart3, MessageSquare, ClipboardList
} from 'lucide-react'
import { useAuthStore } from '../store/auth'
import { authAPI } from '../api/client'
import ThemeToggle from './ThemeToggle'
import { Wordmark } from './Brand'
import QueuePanel from './QueuePanel'
import AttentionModal from './AttentionModal'
import CreditsModal from './CreditsModal'
import { useCreditsStore } from '../store/credits'
import { prefetch } from '../lib/prefetch'
import { PageSkeleton } from './Skeleton'
import { useActivityStore } from '../store/activity'
import toast from 'react-hot-toast'
import clsx from 'clsx'

const NAV = [
  { to: '/dashboard',      icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/jobs',           icon: ClipboardList,   label: 'Jobs' },
  { to: '/generate',       icon: FileText,        label: 'Generate resume' },
  { to: '/cover-letter',   icon: Mail,            label: 'Cover letter' },
  { to: '/interview-prep', icon: BrainCircuit,    label: 'Interview prep' },
  { to: '/assistant',      icon: MessageSquare,   label: 'Application answers' },
  { to: '/metabase',       icon: UserRound,       label: 'My profile' },
  { to: '/settings',       icon: Settings,        label: 'Settings' },
]

function NavItem({ to, icon: Icon, label, onClick }) {
  return (
    <NavLink to={to} onClick={onClick} onMouseEnter={() => prefetch(to)} onFocus={() => prefetch(to)}
             className={({ isActive }) => clsx('nav-item', isActive && 'bg-bg-hover !text-text-primary font-medium')}>
      {({ isActive }) => (
        <>
          <Icon size={16} className={isActive ? 'text-text-primary' : 'text-text-muted'} aria-hidden="true" />
          <span>{label}</span>
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
  const [isAdmin, setIsAdmin] = useState(false)
  const [unverified, setUnverified] = useState(false)
  useEffect(() => {
    authAPI.me().then((r) => { setIsAdmin(!!r.data.is_admin); setUnverified(r.data.is_verified === false) }).catch(() => {})
  }, [])

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
    try { await authAPI.logout() } catch { /* logout is best-effort */ }
    logout()
    navigate('/login')
    toast.success('Logged out')
  }

  const { credits, billingEnabled } = useCreditsStore()
  useEffect(() => { useCreditsStore.getState().refresh() }, [])

  return (
    <div className="flex h-[100dvh] overflow-hidden">
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

      {/* Sidebar: a flat column with a hairline. Below `lg` it is an off-canvas drawer. */}
      <aside aria-label="Sidebar" className={clsx(
        'w-60 flex-shrink-0 bg-bg border-r border-bg-border flex flex-col',
        'fixed inset-y-0 left-0 z-50 transition-transform duration-200 ease-out',
        'lg:static lg:translate-x-0',
        mobileOpen ? 'translate-x-0' : '-translate-x-full'
      )}>
        {/* Logo */}
        <div className="px-5 h-16 flex items-center justify-between border-b border-bg-border">
          <Wordmark to="/dashboard" />
          <div className="flex items-center gap-1">
            <ThemeToggle />
            <button onClick={() => setMobileOpen(false)} className="lg:hidden p-1.5 rounded-md text-text-muted hover:text-text-primary hover:bg-bg-hover transition-colors" aria-label="Close menu">
              <X size={18} />
            </button>
          </div>
        </div>

        {/* Nav */}
        <nav className="flex-1 px-3 py-4 space-y-0.5 overflow-y-auto">
          <p className="px-3 pb-1.5 text-xs text-text-muted">Workspace</p>
          {NAV.slice(0, 6).map((item) => <NavItem key={item.to} {...item} onClick={() => setMobileOpen(false)} />)}

          <p className="px-3 pt-6 pb-1.5 text-xs text-text-muted">Account</p>
          {NAV.slice(6).map((item) => <NavItem key={item.to} {...item} onClick={() => setMobileOpen(false)} />)}
          {isAdmin && <NavItem to="/admin" icon={BarChart3} label="Admin" onClick={() => setMobileOpen(false)} />}
        </nav>

        {/* User block */}
        <div className="px-3 py-4 border-t border-bg-border">
          {billingEnabled && (
          <div className="px-3 py-2.5 rounded-lg border border-bg-border mb-3">
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-xs text-text-secondary">Credits</span>
              <span className="text-xs font-medium text-text-primary figure" data-testid="credits-badge">
                {credits ? `${credits.job} job${credits.resume ? ` + ${credits.resume} resume` : ''}` : '…'}
              </span>
            </div>
            <Link to="/settings?section=billing"
                className="flex items-center gap-1 text-xs text-text-secondary hover:text-text-primary transition-colors">
                Get credits or invite a friend <ChevronRight size={12} />
              </Link>
          </div>
          )}

          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-md bg-bg-hover flex items-center justify-center text-text-primary text-sm font-medium" aria-hidden="true">
              {user?.full_name?.[0]?.toUpperCase() || user?.email?.[0]?.toUpperCase() || '?'}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-text-primary truncate">{user?.full_name || 'User'}</p>
              <p className="text-xs text-text-muted truncate">{user?.email}</p>
            </div>
            <button onClick={handleLogout}
              className="p-1.5 rounded-md text-text-muted hover:text-text-primary hover:bg-bg-hover transition-colors"
              title="Log out" aria-label="Log out">
              <LogOut size={15} />
            </button>
          </div>
        </div>
      </aside>

      {/* Content column — mobile top bar (hamburger + logo) stacks above
          main below `lg`; hidden entirely once the static sidebar takes
          over. */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <header className="lg:hidden flex-shrink-0 flex items-center justify-between gap-3 px-4 h-14 border-b border-bg-border bg-bg">
          <button onClick={() => setMobileOpen(true)} className="p-1.5 -ml-1.5 rounded-md text-text-secondary hover:text-text-primary hover:bg-bg-hover transition-colors" aria-label="Open menu">
            <Menu size={20} />
          </button>
          <Wordmark to="/dashboard" size="text-base" />
          <ThemeToggle />
        </header>

        {/* Main content — route transitions scoped here via useOutlet(), so the
            sidebar above (and its nav pill) never remounts on navigation. */}
        <main id="main" tabIndex={-1} className="flex-1 overflow-hidden outline-none flex flex-col">
          {unverified && (
            <div role="status" className="px-4 py-2 text-sm bg-bg-hover border-b border-bg-border flex items-center gap-3 flex-wrap">
              <span className="text-text-primary">Verify your email to use the AI tools and get your free credits. We sent a link to {user?.email}; check spam too.</span>
              <button className="text-text-primary underline underline-offset-2 hover:text-brand"
                onClick={() => authAPI.sendVerification().then(() => toast.success('Verification email sent'))
                  .catch((e) => toast.error(e.response?.data?.detail || 'Could not send the email'))}>
                Send it again
              </button>
            </div>
          )}
          <AnimatePresence mode="wait" initial={false}>
            <motion.div
              key={location.pathname}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.16, ease: [0.22, 1, 0.36, 1] }}
              className="flex-1 min-h-0 overflow-y-auto"
            >
              <Suspense fallback={<PageSkeleton />}>{element}</Suspense>
            </motion.div>
          </AnimatePresence>
        </main>
      </div>
      <QueuePanel />
      <AttentionModal />
      <CreditsModal />
    </div>
  )
}
