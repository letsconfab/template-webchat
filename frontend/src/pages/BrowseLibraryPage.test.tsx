import { render, screen, within } from '@testing-library/react'
import { HttpResponse, http } from 'msw'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import { server } from '../test/server'
import BrowseLibraryPage from './BrowseLibraryPage'

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 2, email: 'member@example.com', role: 'user' },
    logout: vi.fn(),
  }),
}))

const counts: Record<string, number> = {
  inspire: 3,
  nurture: 1,
  trust: 0,
  embody: 2,
  guide: 4,
  regulate: 1,
  align: 2,
  transcend: 1,
  engage: 5,
}

function systemsHandler() {
  return http.get('/api/library/systems', () =>
    HttpResponse.json(
      Object.entries(counts).map(([slug, document_count]) => ({
        slug,
        name: slug[0].toUpperCase() + slug.slice(1),
        document_count,
      })),
    ),
  )
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/library/browse']}>
      <BrowseLibraryPage />
    </MemoryRouter>,
  )
}

describe('Browse the Library', () => {
  it('shows a folder per INTEGRATE System with its document count, in canonical order', async () => {
    server.use(systemsHandler())
    renderPage()

    expect(screen.getByRole('heading', { level: 1, name: 'Browse the Library' })).toBeVisible()
    const folders = within(await screen.findByRole('list', { name: 'INTEGRATE Systems' }))
    const items = folders.getAllByRole('listitem')
    expect(items.map((item) => within(item).getByRole('heading').textContent)).toEqual([
      'Inspire',
      'Nurture',
      'Trust',
      'Embody',
      'Guide',
      'Regulate',
      'Align',
      'Transcend',
      'Engage',
    ])

    const inspire = items[0]
    expect(within(inspire).getByRole('link')).toHaveAttribute('href', '/library/browse/inspire')
    expect(within(inspire).getByText('Leadership — from command to connection')).toBeVisible()
    expect(within(inspire).getByText('3 documents')).toBeVisible()
    expect(within(items[1]).getByText('1 document')).toBeVisible()
  })

  it('renders a System with no documents muted, as Coming soon, and not as a link', async () => {
    server.use(systemsHandler())
    renderPage()

    const folders = within(await screen.findByRole('list', { name: 'INTEGRATE Systems' }))
    const trust = folders.getAllByRole('listitem')[2]
    expect(within(trust).getByRole('heading', { name: 'Trust' })).toBeVisible()
    expect(within(trust).getByText('Coming soon')).toBeVisible()
    expect(within(trust).queryByRole('link')).not.toBeInTheDocument()
    expect(within(trust).queryByText(/documents?$/)).not.toBeInTheDocument()
  })

  it('shows an error when the library cannot be loaded', async () => {
    server.use(http.get('/api/library/systems', () => new HttpResponse(null, { status: 500 })))
    renderPage()

    expect(await screen.findByRole('alert')).toHaveTextContent(/couldn.t load the library/i)
  })
})
