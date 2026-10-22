import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import LibraryLandingPage from './LibraryLandingPage'

const logout = vi.fn()

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 2, email: 'member@example.com', role: 'user' },
    logout,
  }),
}))

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/library']}>
      <LibraryLandingPage />
    </MemoryRouter>,
  )
}

describe('Resource Library landing page', () => {
  it('introduces the members-only Resource Library', () => {
    renderPage()

    expect(screen.getByText('MEMBERS-ONLY')).toBeVisible()
    expect(screen.getByRole('heading', { level: 1, name: 'ALO Resource Library' })).toBeVisible()
    expect(
      screen.getByText(
        "Every Loving System in Practice and INTEGRATE Field Guide the Consortium has published, organized two ways. Choose how you'd like to find what you need.",
      ),
    ).toBeVisible()
  })

  it('offers both paths into the library with routed calls to action', () => {
    renderPage()

    expect(screen.getByRole('heading', { name: 'Browse the Library' })).toBeVisible()
    expect(
      screen.getByText(
        'Search with your eyes. Click through folders of Loving Systems in Practice and Field Guides, organized by INTEGRATE domain.',
      ),
    ).toBeVisible()
    expect(screen.getByRole('link', { name: 'Access the Library' })).toHaveAttribute(
      'href',
      '/library/browse',
    )

    expect(screen.getByRole('heading', { name: 'Ask the Librarian' })).toBeVisible()
    expect(
      screen.getByText(
        "Search with your heart. Ask ALO's librarian a question in plain language, and it will answer only from the Consortium's own library.",
      ),
    ).toBeVisible()
    expect(screen.getByRole('link', { name: 'Speak with the Librarian' })).toHaveAttribute(
      'href',
      '/chat',
    )
  })

  it("lists the nine INTEGRATE Systems under What's Inside, each linking to its folder", () => {
    renderPage()

    expect(screen.getByRole('heading', { level: 2, name: "What's Inside" })).toBeVisible()
    expect(
      screen.getByText(
        'Both paths draw on the same library, organized around the nine INTEGRATE domains.',
      ),
    ).toBeVisible()

    const systems = within(screen.getByRole('list', { name: 'INTEGRATE Systems' }))
    const expected = [
      ['Inspire', '/library/browse/inspire', 'Leadership — from command to connection'],
      ['Nurture', '/library/browse/nurture', 'Teams — from silos to safe, healing units'],
      ['Trust', '/library/browse/trust', 'Information systems — from secrecy to transparency'],
      ['Embody', '/library/browse/embody', 'Culture — from slogans to lived values'],
      ['Guide', '/library/browse/guide', 'Management — from control to compassionate accountability'],
      ['Regulate', '/library/browse/regulate', 'Policies — from restriction to justice and care'],
      ['Align', '/library/browse/align', 'Workflows — from burnout cycles to humane rhythms'],
      ['Transcend', '/library/browse/transcend', 'Community & patients — from outreach to shared healing'],
      ['Engage', '/library/browse/engage', 'People systems — from tokenism to belonging and agency'],
    ]
    const links = systems.getAllByRole('link')
    expect(links).toHaveLength(9)
    expected.forEach(([name, href, description], index) => {
      expect(links[index]).toHaveAttribute('href', href)
      expect(within(links[index]).getByRole('heading', { name })).toBeVisible()
      expect(within(links[index]).getByText(description)).toBeVisible()
    })
  })

  it('wraps the page in the library header and footer', () => {
    renderPage()

    const nav = within(screen.getByRole('navigation', { name: 'Resource Library' }))
    expect(nav.getByRole('link', { name: 'Resource Library' })).toHaveAttribute('href', '/library')
    expect(nav.queryByRole('link', { name: 'Ask the Librarian' })).toBeNull()
    expect(screen.getByRole('button', { name: /log out/i })).toBeVisible()
    expect(screen.getByText('© 2026 All rights reserved A Loving Organization')).toBeVisible()
  })
})
