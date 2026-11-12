import { useState } from 'react'
import { Link } from 'react-router-dom'

const KEY = 'cookie-notice-seen'
const seen = () => { try { return localStorage.getItem(KEY) === '1' } catch { return false } }

// ATS-Ready sets only strictly necessary cookies (login session). Nothing here
// gates tracking; if analytics are ever added they must wait for an explicit opt-in.
export default function CookieNotice() {
  const [open, setOpen] = useState(!seen())
  if (!open) return null
  const dismiss = () => { try { localStorage.setItem(KEY, '1') } catch { /* private mode */ } setOpen(false) }
  return (
    <div role="region" aria-label="Cookie notice"
         className="fixed bottom-4 left-4 right-4 sm:left-auto sm:max-w-sm z-50 card text-sm space-y-3 shadow-xl">
      <p className="text-text-secondary">
        We use only the cookies needed to keep you signed in. No advertising or tracking cookies.{' '}
        <Link to="/privacy" className="text-brand underline">Privacy policy</Link>
      </p>
      <button className="btn-primary text-sm" onClick={dismiss}>Got it</button>
    </div>
  )
}
