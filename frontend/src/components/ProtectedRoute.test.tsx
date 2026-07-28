import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import type { RuntimeFeatures } from '../contexts/AuthContext'
import ProtectedRoute from './ProtectedRoute'

const authState = vi.hoisted(() => {
  const defaultFeatures: RuntimeFeatures = {
    admin_replay_enabled: false,
    tester_correspondence_enabled: false,
    tester_email_notifications_enabled: false,
  }
  return {
    defaultFeatures,
    current: {
      isAuthenticated: true,
      isAdmin: false,
      isLoading: false,
      featuresLoaded: false,
      features: defaultFeatures,
    },
  }
})

const defaultFeatures = authState.defaultFeatures
vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => authState.current,
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

function renderAtFeedback() {
  return render(
    <MemoryRouter initialEntries={['/feedback/a7b7c2df-a857-42fc-880c-a771328dc5a8']}>
      <Routes>
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
    </MemoryRouter>,
  )
}

describe('ProtectedRoute feature gate', () => {
  it('does not bounce to /chat while runtime features are still loading', () => {
    authState.current = {
      isAuthenticated: true,
      isAdmin: false,
      isLoading: false,
      featuresLoaded: false,
      features: defaultFeatures,
    }

    renderAtFeedback()

    expect(screen.queryByRole('heading', { name: 'Chat page' })).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Feedback case page' })).not.toBeInTheDocument()
    expect(document.querySelector('.animate-spin')).toBeTruthy()
  })

  it('allows the feedback route once features have loaded and the flag is on', () => {
    authState.current = {
      isAuthenticated: true,
      isAdmin: false,
      isLoading: false,
      featuresLoaded: true,
      features: {
        ...defaultFeatures,
        tester_correspondence_enabled: true,
      },
    }

    renderAtFeedback()

    expect(screen.getByRole('heading', { name: 'Feedback case page' })).toBeVisible()
    expect(screen.getByTestId('current-path')).toHaveTextContent(
      '/feedback/a7b7c2df-a857-42fc-880c-a771328dc5a8',
    )
  })

  it('bounces to /chat only after features loaded and the flag is off', () => {
    authState.current = {
      isAuthenticated: true,
      isAdmin: false,
      isLoading: false,
      featuresLoaded: true,
      features: defaultFeatures,
    }

    renderAtFeedback()

    expect(screen.getByRole('heading', { name: 'Chat page' })).toBeVisible()
    expect(screen.getByTestId('current-path')).toHaveTextContent('/chat')
  })
})

function renderAtFeedbackSummary() {
  return render(
    <MemoryRouter initialEntries={['/admin/feedback/summaries/demo-artifact']}>
      <Routes>
        <Route path="/login" element={<LocationProbe label="Login page" />} />
        <Route
          path="/admin/dashboard"
          element={<LocationProbe label="Admin dashboard" />}
        />
        <Route
          path="/admin/feedback/summaries/:artifactId"
          element={
            <ProtectedRoute requireAdmin requiredFeature="admin_replay_enabled">
              <LocationProbe label="Feedback summary page" />
            </ProtectedRoute>
          }
        />
      </Routes>
    </MemoryRouter>,
  )
}

describe('ProtectedRoute feedback summary admin gate', () => {
  it('rejects unauthenticated access to the summary detail route', () => {
    authState.current = {
      isAuthenticated: false,
      isAdmin: false,
      isLoading: false,
      featuresLoaded: true,
      features: defaultFeatures,
    }

    renderAtFeedbackSummary()

    expect(screen.getByRole('heading', { name: 'Login page' })).toBeVisible()
  })

  it('rejects non-admin authenticated users', () => {
    authState.current = {
      isAuthenticated: true,
      isAdmin: false,
      isLoading: false,
      featuresLoaded: true,
      features: {
        ...defaultFeatures,
        admin_replay_enabled: true,
      },
    }

    renderAtFeedbackSummary()

    expect(screen.getByRole('heading', { name: 'Login page' })).toBeVisible()
  })

  it('rejects admins when admin_replay_enabled is off', () => {
    authState.current = {
      isAuthenticated: true,
      isAdmin: true,
      isLoading: false,
      featuresLoaded: true,
      features: defaultFeatures,
    }

    renderAtFeedbackSummary()

    expect(screen.getByRole('heading', { name: 'Admin dashboard' })).toBeVisible()
  })

  it('allows admins when admin_replay_enabled is on', () => {
    authState.current = {
      isAuthenticated: true,
      isAdmin: true,
      isLoading: false,
      featuresLoaded: true,
      features: {
        ...defaultFeatures,
        admin_replay_enabled: true,
      },
    }

    renderAtFeedbackSummary()

    expect(
      screen.getByRole('heading', { name: 'Feedback summary page' }),
    ).toBeVisible()
  })
})
