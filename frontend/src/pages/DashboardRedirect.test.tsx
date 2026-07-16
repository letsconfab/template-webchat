import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, http } from 'msw'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import ProtectedRoute from '../components/ProtectedRoute'
import { AuthProvider } from '../contexts/AuthContext'
import { server } from '../test/server'
import AdminLogin from './AdminLogin'

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

function LocationProbe({ label }: { label: string }) {
  const location = useLocation()
  return (
    <div>
      <h1>{label}</h1>
      <p data-testid="current-path">{location.pathname}</p>
    </div>
  )
}

function LoginSearchProbe() {
  const location = useLocation()
  return <p data-testid="login-search">{location.search.replace(/^\?/, '')}</p>
}

function renderDashboardRoutes(initialEntries: string[]) {
  return render(
    <AuthProvider>
      <MemoryRouter initialEntries={initialEntries}>
        <Routes>
          <Route
            path="/login"
            element={
              <>
                <AdminLogin />
                <LoginSearchProbe />
              </>
            }
          />
          <Route
            path="/chat"
            element={
              <ProtectedRoute>
                <LocationProbe label="Chat page" />
              </ProtectedRoute>
            }
          />
          <Route
            path="/dashboard"
            element={
              <ProtectedRoute requireAdmin>
                <LocationProbe label="Legacy dashboard redirect" />
              </ProtectedRoute>
            }
          />
          <Route
            path="/admin/dashboard"
            element={
              <ProtectedRoute requireAdmin>
                <LocationProbe label="Admin dashboard" />
              </ProtectedRoute>
            }
          />
        </Routes>
      </MemoryRouter>
    </AuthProvider>,
  )
}

describe('dashboard route protection and redirect', () => {
  it('stores returnTo and sends unauthenticated /dashboard hits to login', async () => {
    renderDashboardRoutes(['/dashboard'])

    expect(await screen.findByRole('heading', { name: 'Login Here!' })).toBeVisible()
    await waitFor(() => {
      expect(screen.getByTestId('login-search')).toHaveTextContent(
        `returnTo=${encodeURIComponent('/dashboard')}`,
      )
    })
  })

  it('recovers session-stored returnTo=/dashboard after login for an admin', async () => {
    sessionStorage.setItem('postLoginReturnTo', '/dashboard')
    server.use(
      http.post('/api/auth/login', () =>
        HttpResponse.json({ access_token: 'test-token' }),
      ),
      http.get('/api/auth/me', () =>
        HttpResponse.json({
          id: 1,
          email: 'admin@example.com',
          role: 'admin',
          is_active: true,
          created_at: '2026-07-14T12:00:00Z',
          updated_at: '2026-07-14T12:00:00Z',
        }),
      ),
      http.get('/api/settings/features', () =>
        HttpResponse.json({
          admin_replay_enabled: true,
          tester_correspondence_enabled: true,
          tester_email_notifications_enabled: true,
        }),
      ),
    )

    const user = userEvent.setup()
    renderDashboardRoutes(['/login'])

    await user.type(screen.getByLabelText('Email Address'), 'admin@example.com')
    await user.type(screen.getByLabelText('Password'), 'password123')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => {
      expect(screen.getByTestId('current-path')).toHaveTextContent('/dashboard')
    })
    expect(screen.getByRole('heading', { name: 'Legacy dashboard redirect' })).toBeVisible()
  })

  it('honours /login?returnTo=/dashboard for an admin', async () => {
    server.use(
      http.post('/api/auth/login', () =>
        HttpResponse.json({ access_token: 'test-token' }),
      ),
      http.get('/api/auth/me', () =>
        HttpResponse.json({
          id: 1,
          email: 'admin@example.com',
          role: 'admin',
          is_active: true,
          created_at: '2026-07-14T12:00:00Z',
          updated_at: '2026-07-14T12:00:00Z',
        }),
      ),
      http.get('/api/settings/features', () =>
        HttpResponse.json({
          admin_replay_enabled: true,
          tester_correspondence_enabled: true,
          tester_email_notifications_enabled: true,
        }),
      ),
    )

    const user = userEvent.setup()
    renderDashboardRoutes([`/login?returnTo=${encodeURIComponent('/dashboard')}`])

    await user.type(screen.getByLabelText('Email Address'), 'admin@example.com')
    await user.type(screen.getByLabelText('Password'), 'password123')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => {
      expect(screen.getByTestId('current-path')).toHaveTextContent('/dashboard')
    })
  })

  it('blocks a non-admin from /dashboard after login with returnTo', async () => {
    server.use(
      http.post('/api/auth/login', () =>
        HttpResponse.json({ access_token: 'test-token' }),
      ),
      http.get('/api/auth/me', () =>
        HttpResponse.json({
          id: 2,
          email: 'user@example.com',
          role: 'user',
          is_active: true,
          created_at: '2026-07-14T12:00:00Z',
          updated_at: '2026-07-14T12:00:00Z',
        }),
      ),
      http.get('/api/settings/features', () =>
        HttpResponse.json({
          admin_replay_enabled: false,
          tester_correspondence_enabled: true,
          tester_email_notifications_enabled: true,
        }),
      ),
    )

    const user = userEvent.setup()
    renderDashboardRoutes([`/login?returnTo=${encodeURIComponent('/dashboard')}`])

    await user.type(screen.getByLabelText('Email Address'), 'user@example.com')
    await user.type(screen.getByLabelText('Password'), 'password123')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    // Non-admin must not land on the admin dashboard; eventually settles off /dashboard
    await waitFor(() => {
      expect(screen.queryByRole('heading', { name: 'Legacy dashboard redirect' })).not.toBeInTheDocument()
      expect(screen.queryByRole('heading', { name: 'Admin dashboard' })).not.toBeInTheDocument()
    })
    expect(screen.getByTestId('current-path').textContent).not.toBe('/dashboard')
    expect(screen.getByTestId('current-path').textContent).not.toBe('/admin/dashboard')
  })
})
