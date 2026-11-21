import { Link } from 'react-router-dom'

// The mark is a tick on a solid square: the thing the product is for (a resume that passes). One colour, no effects.
export function Mark({ size = 20 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
      <rect width="24" height="24" rx="6" fill="rgb(var(--color-brand))" />
      <path d="M6.5 12.5l3.6 3.6 7.4-8" fill="none" stroke="#fff" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export function Wordmark({ to = '/', className = '', size = 'text-[17px]' }) {
  return (
    <Link to={to} className={`inline-flex items-center gap-2 text-text-primary ${className}`} aria-label="ATS-Ready home">
      <Mark />
      <span className={`${size} font-semibold leading-none`}>ATS-Ready</span>
    </Link>
  )
}
