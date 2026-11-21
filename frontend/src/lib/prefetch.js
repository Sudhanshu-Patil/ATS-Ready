// Start loading a page's code when the pointer or keyboard reaches its link, so the click feels instant.
// The import() calls use the same module paths as the lazy routes in App.jsx, so the browser reuses the download.
const ROUTES = {
  '/dashboard': () => import('../pages/Dashboard'),
  '/jobs': () => import('../pages/Jobs'),
  '/generate': () => import('../pages/Generator'),
  '/cover-letter': () => import('../pages/CoverLetter'),
  '/interview-prep': () => import('../pages/InterviewPrep'),
  '/assistant': () => import('../pages/Assistant'),
  '/metabase': () => import('../pages/Metabase'),
  '/settings': () => import('../pages/Settings'),
  '/admin': () => import('../pages/Admin'),
}
const done = new Set()

export function prefetch(to) {
  const path = to.split('?')[0]
  if (done.has(path) || !ROUTES[path]) return
  done.add(path)
  ROUTES[path]().catch(() => done.delete(path))
}
