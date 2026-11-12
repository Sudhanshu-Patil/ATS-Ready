import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import GoogleButton from './GoogleButton'
import { authAPI } from '../api/client'

vi.mock('../api/client', () => ({
  authAPI: { config: vi.fn(), google: vi.fn() },
}))
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }))

const renderButton = () => render(<MemoryRouter><GoogleButton /></MemoryRouter>)

describe('GoogleButton', () => {
  beforeEach(() => vi.clearAllMocks())

  it('renders nothing when Google sign-in is not configured', async () => {
    authAPI.config.mockResolvedValue({ data: { google_client_id: null } })
    const { container } = renderButton()
    await waitFor(() => expect(authAPI.config).toHaveBeenCalled())
    expect(container).toBeEmptyDOMElement()
  })

  it('renders nothing when the config request fails', async () => {
    authAPI.config.mockRejectedValue(new Error('offline'))
    const { container } = renderButton()
    await waitFor(() => expect(authAPI.config).toHaveBeenCalled())
    expect(container).toBeEmptyDOMElement()
  })

  it('shows the divider and button slot when a client id is configured', async () => {
    authAPI.config.mockResolvedValue({ data: { google_client_id: 'abc.apps.googleusercontent.com' } })
    renderButton()
    expect(await screen.findByText('or')).toBeInTheDocument()
  })
})
