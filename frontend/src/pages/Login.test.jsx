import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import toast from 'react-hot-toast'
import Login from './Login'
import { authAPI } from '../api/client'
import { useAuthStore } from '../store/auth'

vi.mock('../api/client', () => ({
  authAPI: { login: vi.fn(), config: vi.fn(() => Promise.resolve({ data: { google_client_id: null } })) },
}))

const navigateMock = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return { ...actual, useNavigate: () => navigateMock }
})

vi.mock('react-hot-toast', () => ({
  default: { success: vi.fn(), error: vi.fn() },
}))

function renderLogin() {
  return render(
    <MemoryRouter>
      <Login />
    </MemoryRouter>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  useAuthStore.setState({ accessToken: null, user: null, isLoading: false })
})

describe('Login', () => {
  it('logs in and redirects to /dashboard on success', async () => {
    authAPI.login.mockResolvedValue({
      data: {
        access_token: 'tok-123',
        user_id: 'u1',
        email: 'jane@example.com',
        full_name: 'Jane Doe',
        plan: 'free',
      },
    })

    renderLogin()
    await userEvent.type(screen.getByPlaceholderText('you@example.com'), 'jane@example.com')
    await userEvent.type(screen.getByPlaceholderText('••••••••'), 'correct-password')
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => expect(authAPI.login).toHaveBeenCalledWith('jane@example.com', 'correct-password'))
    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith('/dashboard'))

    // The access token should now be in the global store
    expect(useAuthStore.getState().accessToken).toBe('tok-123')
    expect(toast.success).toHaveBeenCalled()
  })

  it('shows an error toast and does not navigate on invalid credentials', async () => {
    authAPI.login.mockRejectedValue({
      response: { data: { detail: 'Invalid email or password' } },
    })

    renderLogin()
    await userEvent.type(screen.getByPlaceholderText('you@example.com'), 'jane@example.com')
    await userEvent.type(screen.getByPlaceholderText('••••••••'), 'wrong-password')
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Invalid email or password'))
    expect(navigateMock).not.toHaveBeenCalled()
    expect(useAuthStore.getState().accessToken).toBeNull()
  })
})
