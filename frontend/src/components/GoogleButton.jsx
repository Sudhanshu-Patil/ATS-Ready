import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import toast from 'react-hot-toast'
import { authAPI } from '../api/client'
import { useAuthStore } from '../store/auth'

const GIS_SRC = 'https://accounts.google.com/gsi/client'

function loadGoogleScript() {
  return new Promise((resolve, reject) => {
    if (window.google?.accounts?.id) return resolve()
    const existing = document.querySelector(`script[src="${GIS_SRC}"]`)
    const script = existing || Object.assign(document.createElement('script'), {
      src: GIS_SRC, async: true, defer: true,
    })
    script.addEventListener('load', resolve, { once: true })
    script.addEventListener('error', reject, { once: true })
    if (!existing) document.head.appendChild(script)
  })
}

// "Continue with Google". Renders nothing unless the server has a client id
// configured, so the app works unchanged without Google set up.
export default function GoogleButton() {
  const [clientId, setClientId] = useState(null)
  const ref = useRef(null)
  const { login } = useAuthStore()
  const navigate = useNavigate()

  useEffect(() => {
    let alive = true
    authAPI.config()
      .then((r) => { if (alive) setClientId(r.data.google_client_id || null) })
      .catch(() => {})
    return () => { alive = false }
  }, [])

  useEffect(() => {
    if (!clientId || !ref.current) return undefined
    let cancelled = false

    const onCredential = async ({ credential }) => {
      try {
        const { data } = await authAPI.google(credential)
        login(data.access_token, {
          id: data.user_id, email: data.email, full_name: data.full_name, plan: data.plan,
        })
        toast.success(data.is_new ? 'Account created — welcome!' : `Welcome back, ${data.full_name || data.email}!`)
        navigate(data.is_new ? '/metabase' : '/dashboard')
      } catch (err) {
        toast.error(err.response?.data?.detail || 'Google sign-in failed')
      }
    }

    loadGoogleScript().then(() => {
      if (cancelled || !ref.current) return
      window.google.accounts.id.initialize({ client_id: clientId, callback: onCredential })
      window.google.accounts.id.renderButton(ref.current, {
        theme: 'outline', size: 'large', text: 'continue_with', width: 320,
      })
    }).catch(() => {})                       // blocked script: email login still works

    return () => { cancelled = true }
  }, [clientId])  // eslint-disable-line react-hooks/exhaustive-deps

  if (!clientId) return null
  return (
    <div className="mt-5">
      <div className="flex items-center gap-3 mb-4 text-xs text-text-muted">
        <span className="flex-1 h-px bg-bg-border" /> or <span className="flex-1 h-px bg-bg-border" />
      </div>
      <div ref={ref} className="flex justify-center min-h-[44px]" />
    </div>
  )
}
