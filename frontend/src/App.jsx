import { useEffect } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from './store/auth'
import { useJobsStore } from './store/jobs'
import { authAPI } from './api/client'

import AuroraBackground from './components/AuroraBackground'
import Layout from './components/Layout'
import ProtectedRoute from './components/ProtectedRoute'
import Login from './pages/Login'
import Register from './pages/Register'
import Dashboard from './pages/Dashboard'
import Generator from './pages/Generator'
import History from './pages/History'
import Metabase from './pages/Metabase'
import Settings from './pages/Settings'
import CoverLetter from './pages/CoverLetter'
import InterviewPrep from './pages/InterviewPrep'

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
      <Routes>
        <Route path="/login"    element={<Login />} />
        <Route path="/register" element={<Register />} />

        <Route element={<ProtectedRoute><Layout /></ProtectedRoute>}>
          <Route path="/dashboard"      element={<Dashboard />} />
          <Route path="/generate"       element={<Generator />} />
          <Route path="/cover-letter"   element={<CoverLetter />} />
          <Route path="/interview-prep" element={<InterviewPrep />} />
          <Route path="/history"        element={<History />} />
          <Route path="/metabase"       element={<Metabase />} />
          <Route path="/settings"       element={<Settings />} />
        </Route>

        <Route path="/"  element={<Navigate to="/dashboard" replace />} />
        <Route path="*"  element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </>
  )
}
