import { Navigate } from 'react-router-dom'
import { useAuthStore } from '../store/auth'
import Spinner from './Spinner'

export default function ProtectedRoute({ children }) {
  const { accessToken, isLoading } = useAuthStore()

  // Show nothing while checking session (avoids flash of login page)
  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <Spinner size="lg" color="brand" />
      </div>
    )
  }

  if (!accessToken) {
    return <Navigate to="/login" replace />
  }

  return children
}
