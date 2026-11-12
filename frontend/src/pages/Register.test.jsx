import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import Register from './Register'
import { authAPI } from '../api/client'
import { useAuthStore } from '../store/auth'

vi.mock('../api/client', () => ({
  authAPI: { register: vi.fn(), config: vi.fn(() => Promise.resolve({ data: { google_client_id: null } })) },
}))

const navigateMock = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return { ...actual, useNavigate: () => navigateMock }
})

vi.mock('react-hot-toast', () => ({
  default: { success: vi.fn(), error: vi.fn() },
}))

function renderRegister() {
  return render(
    <MemoryRouter>
      <Register />
    </MemoryRouter>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  useAuthStore.setState({ accessToken: null, user: null, isLoading: false })
})

describe('Register', () => {
  it('disables submit for a password under 8 characters and never calls the API', async () => {
    renderRegister()
    await userEvent.type(screen.getByPlaceholderText('Priya Sharma'), 'New User')
    await userEvent.type(screen.getByPlaceholderText('you@example.com'), 'new@example.com')
    await userEvent.type(screen.getByPlaceholderText('Min. 8 characters'), 'short')

    const submitButton = screen.getByRole('button', { name: /create account/i })
    expect(submitButton).toBeDisabled()
    expect(screen.getByText('At least 8 characters required')).toBeInTheDocument()
    expect(authAPI.register).not.toHaveBeenCalled()
  })

  it('registers and redirects to /metabase on success', async () => {
    authAPI.register.mockResolvedValue({
      data: {
        access_token: 'tok-456',
        user_id: 'u2',
        email: 'new@example.com',
        full_name: 'New User',
        plan: 'free',
      },
    })

    renderRegister()
    await userEvent.type(screen.getByPlaceholderText('Priya Sharma'), 'New User')
    await userEvent.type(screen.getByPlaceholderText('you@example.com'), 'new@example.com')
    await userEvent.type(screen.getByPlaceholderText('Min. 8 characters'), 'long-enough-pass')
    await userEvent.click(screen.getByRole('button', { name: /create account/i }))

    await waitFor(() => expect(authAPI.register).toHaveBeenCalledWith('new@example.com', 'long-enough-pass', 'New User'))
    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith('/metabase'))
    expect(useAuthStore.getState().accessToken).toBe('tok-456')
  })
})
