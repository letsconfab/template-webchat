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

const caseId = 'a7b7c2df-a857-42fc-880c-a771328dc5a8'
const feedbackPath = `/feedback/${caseId}`

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

function renderEmailLinkFlow() {
  return render(
    <AuthProvider>
      <MemoryRouter initialEntries={[feedbackPath]}>
        <Routes>
          <Route path="/login" element={<AdminLogin />} />
          <Route
            path="/chat"
            element={
              <ProtectedRoute>
                <LocationProbe label="Chat page" />
              </ProtectedRoute>
            }
          />
          <Route
            path="/feedback/:caseId"
            element={
              <ProtectedRoute requiredFeature="tester_correspondence_enabled">
                <LocationProbe label="Feedback case page" />
              </ProtectedRoute>
            }
          />
        </Routes>
      </MemoryRouter>
    </AuthProvider>,
  )
}

describe('post-login redirect from email feedback link', () => {
  it('returns the user to the feedback case after login when they were not already authenticated', async () => {
    server.use(
      http.post('/api/auth/login', () =>
        HttpResponse.json({ access_token: 'test-token' }),
      ),
      http.get('/api/auth/me', () =>
        HttpResponse.json({
          id: 1,
          email: 'tester@example.com',
          role: 'user',
          is_active: true,
          created_at: '2026-07-14T12:00:00Z',
          updated_at: '2026-07-14T12:00:00Z',
        }),
      ),
      // Production has latency between /auth/me and /settings/features; that gap is load-bearing.
      http.get('/api/settings/features', async () => {
        await new Promise((resolve) => setTimeout(resolve, 20))
        return HttpResponse.json({
          admin_replay_enabled: true,
          tester_correspondence_enabled: true,
          tester_email_notifications_enabled: true,
        })
      }),
    )

    const user = userEvent.setup()
    renderEmailLinkFlow()

    expect(await screen.findByRole('heading', { name: 'Login Here!' })).toBeVisible()

    await user.type(screen.getByLabelText('Email Address'), 'tester@example.com')
    await user.type(screen.getByLabelText('Password'), 'password123')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => {
      expect(screen.getByTestId('current-path')).toHaveTextContent(feedbackPath)
    })
    expect(screen.getByRole('heading', { name: 'Feedback case page' })).toBeVisible()
    expect(screen.queryByRole('heading', { name: 'Chat page' })).not.toBeInTheDocument()
  })

  it('recovers the feedback deep link from sessionStorage when returnTo is missing from the query', async () => {
    sessionStorage.setItem('postLoginReturnTo', feedbackPath)
    server.use(
      http.post('/api/auth/login', () =>
        HttpResponse.json({ access_token: 'test-token' }),
      ),
      http.get('/api/auth/me', () =>
        HttpResponse.json({
          id: 1,
          email: 'tester@example.com',
          role: 'user',
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
    render(
      <AuthProvider>
        <MemoryRouter initialEntries={['/login']}>
          <Routes>
            <Route path="/login" element={<AdminLogin />} />
            <Route
              path="/chat"
              element={
                <ProtectedRoute>
                  <LocationProbe label="Chat page" />
                </ProtectedRoute>
              }
            />
            <Route
              path="/feedback/:caseId"
              element={
                <ProtectedRoute requiredFeature="tester_correspondence_enabled">
                  <LocationProbe label="Feedback case page" />
                </ProtectedRoute>
              }
            />
          </Routes>
        </MemoryRouter>
      </AuthProvider>,
    )

    await user.type(screen.getByLabelText('Email Address'), 'tester@example.com')
    await user.type(screen.getByLabelText('Password'), 'password123')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => {
      expect(screen.getByTestId('current-path')).toHaveTextContent(feedbackPath)
    })
    expect(screen.queryByRole('heading', { name: 'Chat page' })).not.toBeInTheDocument()
  })

  it('still returns to the Feedback Case after sessionStorage is cleared once returnTo is in the query', async () => {
    sessionStorage.setItem('postLoginReturnTo', feedbackPath)
    server.use(
      http.post('/api/auth/login', () =>
        HttpResponse.json({ access_token: 'test-token' }),
      ),
      http.get('/api/auth/me', () =>
        HttpResponse.json({
          id: 1,
          email: 'tester@example.com',
          role: 'user',
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
    render(
      <AuthProvider>
        <MemoryRouter initialEntries={['/login']}>
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
              path="/feedback/:caseId"
              element={
                <ProtectedRoute requiredFeature="tester_correspondence_enabled">
                  <LocationProbe label="Feedback case page" />
                </ProtectedRoute>
              }
            />
          </Routes>
        </MemoryRouter>
      </AuthProvider>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('login-search')).toHaveTextContent(
        `returnTo=${encodeURIComponent(feedbackPath)}`,
      )
    })

    // Simulate a destructive read / StrictMode remount clearing the session key
    // after the deep link has already been promoted into the query.
    sessionStorage.removeItem('postLoginReturnTo')

    await user.type(screen.getByLabelText('Email Address'), 'tester@example.com')
    await user.type(screen.getByLabelText('Password'), 'password123')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => {
      expect(screen.getByTestId('current-path')).toHaveTextContent(feedbackPath)
    })
    expect(screen.queryByRole('heading', { name: 'Chat page' })).not.toBeInTheDocument()
  })

  it('sends a normal user without a return target to /chat', async () => {
    server.use(
      http.post('/api/auth/login', () =>
        HttpResponse.json({ access_token: 'test-token' }),
      ),
      http.get('/api/auth/me', () =>
        HttpResponse.json({
          id: 1,
          email: 'tester@example.com',
          role: 'user',
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
    render(
      <AuthProvider>
        <MemoryRouter initialEntries={['/login']}>
          <Routes>
            <Route path="/login" element={<AdminLogin />} />
            <Route
              path="/chat"
              element={
                <ProtectedRoute>
                  <LocationProbe label="Chat page" />
                </ProtectedRoute>
              }
            />
            <Route
              path="/feedback/:caseId"
              element={
                <ProtectedRoute requiredFeature="tester_correspondence_enabled">
                  <LocationProbe label="Feedback case page" />
                </ProtectedRoute>
              }
            />
          </Routes>
        </MemoryRouter>
      </AuthProvider>,
    )

    await user.type(screen.getByLabelText('Email Address'), 'tester@example.com')
    await user.type(screen.getByLabelText('Password'), 'password123')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => {
      expect(screen.getByTestId('current-path')).toHaveTextContent('/chat')
    })
  })
})
