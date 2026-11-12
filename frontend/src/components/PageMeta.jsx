import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'

const SITE = 'https://ats-ready.onrender.com'
const DEFAULT_TITLE = 'ATS-Ready | AI Resume Tailoring, ATS Score and Cover Letters'

// path -> [title, indexable]. Signed-in app screens are noindex; the sitemap
// lists only the indexable public pages.
const PAGES = {
  '/':                [DEFAULT_TITLE, true],
  '/login':           ['Log in | ATS-Ready', true],
  '/register':        ['Create your account | ATS-Ready', true],
  '/privacy':         ['Privacy policy | ATS-Ready', true],
  '/terms':           ['Terms of service | ATS-Ready', true],
  '/forgot-password': ['Reset your password | ATS-Ready', false],
  '/reset-password':  ['Choose a new password | ATS-Ready', false],
  '/verify-email':    ['Verify your email | ATS-Ready', false],
  '/dashboard':       ['Dashboard | ATS-Ready', false],
  '/generate':        ['Generate resume | ATS-Ready', false],
  '/cover-letter':    ['Cover letters | ATS-Ready', false],
  '/interview-prep':  ['Interview prep | ATS-Ready', false],
  '/metabase':        ['Your profile | ATS-Ready', false],
  '/settings':        ['Settings | ATS-Ready', false],
  '/admin':           ['Admin | ATS-Ready', false],
}

function setMeta(name, content) {
  let el = document.head.querySelector(`meta[name="${name}"]`)
  if (!el) {
    el = document.createElement('meta')
    el.setAttribute('name', name)
    document.head.appendChild(el)
  }
  el.setAttribute('content', content)
}

// Keeps <title>, robots and the canonical URL right on every client-side navigation.
export default function PageMeta() {
  const { pathname } = useLocation()
  useEffect(() => {
    const known = PAGES[pathname]
    const [title, indexable] = known || ['Page not found | ATS-Ready', false]
    document.title = title
    setMeta('robots', indexable ? 'index, follow' : 'noindex, nofollow')
    const link = document.head.querySelector('link[rel="canonical"]')
    if (link && known) link.setAttribute('href', `${SITE}${pathname === '/' ? '/' : pathname}`)
  }, [pathname])
  return null
}
