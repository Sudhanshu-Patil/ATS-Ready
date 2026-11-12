import { Suspense, lazy, useEffect } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from './store/auth'
import { useJobsStore } from './store/jobs'
import { authAPI } from './api/client'

import AuroraBackground from './components/AuroraBackground'
import Layout from './components/Layout'
import ProtectedRoute from './components/ProtectedRoute'
const Landing = lazy(() => import('./pages/Landing'))
const Login = lazy(() => import('./pages/Login'))
const Register = lazy(() => import('./pages/Register'))
const ForgotPassword = lazy(() => import('./pages/ForgotPassword'))
const ResetPassword = lazy(() => import('./pages/ResetPassword'))
const VerifyEmail = lazy(() => import('./pages/VerifyEmail'))
const Dashboard = lazy(() => import('./pages/Dashboard'))
const Generator = lazy(() => import('./pages/Generator'))
const Metabase = lazy(() => import('./pages/Metabase'))
const Settings = lazy(() => import('./pages/Settings'))
const CoverLetter = lazy(() => import('./pages/CoverLetter'))
const InterviewPrep = lazy(() => import('./pages/InterviewPrep'))
const NotFound = lazy(() => import('./pages/NotFound'))
import CookieNotice from './components/CookieNotice'
import ConfirmHost from './components/ConfirmDialog'
const Privacy = lazy(() => import('./pages/Legal').then((m) => ({ default: m.Privacy })))
const Terms = lazy(() => import('./pages/Legal').then((m) => ({ default: m.Terms })))
const Admin = lazy(() => import('./pages/Admin'))
import PageMeta from './components/PageMeta'
import Spinner from './components/Spinner'
import { initMonitoring } from './lib/monitoring'

export default function App() {
  const { login, logout, setLoading } = useAuthStore()
  const { fetchAll, reset } = useJobsStore()

  useEffect(() => {
    async function restoreSession() {
      try {
        const res = await authAPI.refresh()
        login(res.data.access_token, {
          id:        res.data.user_id,
          email:     res.data.email,
          full_name: res.data.full_name,
          plan:      res.data.plan,
        })
        fetchAll()
      } catch {
        logout()
        reset()
      } finally {
        setLoading(false)
      }
    }
    restoreSession()
    initMonitoring()
  }, [])

  return (
    <>
      {/* Mounted once, persists across navigation — see AuroraBackground.jsx */}
      <AuroraBackground />

      {/* NOTE: do not wrap this in AnimatePresence / key off location here —
          Layout (sidebar + nav pill) is rendered BY this same Routes tree as
          the wrapping route's element, so keying at this level would remount
          the sidebar on every navigation. Route-level transitions live inside
          Layout.jsx instead, via useOutlet(). */}
      <PageMeta />
      <Suspense fallback={<div className="min-h-screen flex items-center justify-center"><Spinner size="lg" /></div>}>
      <Routes>
        <Route path="/login"           element={<Login />} />
        <Route path="/register"        element={<Register />} />
        <Route path="/forgot-password" element={<ForgotPassword />} />
        <Route path="/reset-password"  element={<ResetPassword />} />
        <Route path="/verify-email"    element={<VerifyEmail />} />

        <Route element={<ProtectedRoute><Layout /></ProtectedRoute>}>
          <Route path="/dashboard"      element={<Dashboard />} />
          <Route path="/generate"       element={<Generator />} />
          <Route path="/cover-letter"   element={<CoverLetter />} />
          <Route path="/interview-prep" element={<InterviewPrep />} />
          <Route path="/history"        element={<Navigate to="/generate?tab=history" replace />} />
          <Route path="/metabase"       element={<Metabase />} />
          <Route path="/settings"       element={<Settings />} />
          <Route path="/admin"          element={<Admin />} />
        </Route>

        {/* Public cinematic landing — logged-in users see auth-aware CTAs
            instead of being force-redirected (session restore is async). */}
        <Route path="/"  element={<Landing />} />
        <Route path="/privacy" element={<Privacy />} />
        <Route path="/terms"   element={<Terms />} />
        <Route path="*"  element={<NotFound />} />
      </Routes>
      </Suspense>
      <CookieNotice />
      <ConfirmHost />
    </>
  )
}
