import { useEffect, useState } from 'react'
import { authAPI } from '../api/client'

// Public settings the server hands to every visitor (contact details for the legal pages and the footer).
// Fetched once per page load and shared.
let cached
export function useSiteConfig() {
  const [config, setConfig] = useState(cached || {})
  useEffect(() => {
    if (cached) return undefined
    let live = true
    authAPI.config().then((r) => { cached = r.data; if (live) setConfig(r.data) }).catch(() => {})
    return () => { live = false }
  }, [])
  return config
}
