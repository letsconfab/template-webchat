import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import AdminLogin from './AdminLogin'

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({
    login: vi.fn(),
    user: null,
    isLoading: false,
    featuresLoaded: false,
  }),
}))

describe('AdminLogin', () => {
  it('sends new members to ALO signup on Outseta', () => {
    render(
      <MemoryRouter>
        <AdminLogin />
      </MemoryRouter>,
    )

    const link = screen.getByRole('link', { name: 'Register here' })
    const url = new URL(link.getAttribute('href') ?? '')

    expect(url.origin).toBe('https://a-loving-organization.outseta.com')
    expect(url.searchParams.get('widgetMode')).toBe('register')
    expect(url.searchParams.get('planFamilyUid')).toBe('pWrPx2Qn')
  })
})
