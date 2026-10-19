import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import LibraryLayout from './LibraryLayout'

const logout = vi.fn()

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 2, email: 'member@example.com', role: 'user' },
    logout,
  }),
}))

function renderLayout() {
  return render(
    <MemoryRouter initialEntries={['/library']}>
      <Routes>
        <Route path="/library" element={<LibraryLayout>Library content</LibraryLayout>} />
        <Route path="/login" element={<h1>Login page</h1>} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('LibraryLayout', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
    logout.mockClear()
  })

  it('links back to the Members Portal when its URL is configured', () => {
    vi.stubEnv('VITE_MEMBERS_PORTAL_URL', 'https://members.example.test/portal')
    renderLayout()

    expect(screen.getByRole('link', { name: 'Members Portal' })).toHaveAttribute(
      'href',
      'https://members.example.test/portal',
    )
  })

  it('hides the Members Portal link when no URL is configured', () => {
    vi.stubEnv('VITE_MEMBERS_PORTAL_URL', '')
    renderLayout()

    expect(screen.queryByRole('link', { name: 'Members Portal' })).not.toBeInTheDocument()
  })

  it('logs the Member out of the app and returns to login', async () => {
    renderLayout()

    await userEvent.setup().click(screen.getByRole('button', { name: /log out/i }))

    expect(logout).toHaveBeenCalledOnce()
    expect(screen.getByRole('heading', { name: 'Login page' })).toBeVisible()
  })
})
