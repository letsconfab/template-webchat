import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, http } from 'msw'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { server } from '../test/server'
import LibrarySystemPage from './LibrarySystemPage'

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 2, email: 'member@example.com', role: 'user' },
    logout: vi.fn(),
  }),
}))

const documents = [
  {
    id: 'doc-a',
    title: 'Sample Practice Alpha',
    organization: 'Example Health',
    type: 'LSP',
    systems: ['inspire', 'nurture', 'engage'],
    modified_time: '2026-03-04T15:00:00.000Z',
  },
  {
    id: 'doc-b',
    title: 'Sample Field Guide Beta',
    organization: null,
    type: 'Field Guide',
    systems: ['inspire'],
    modified_time: null,
  },
]

function systemHandler(slug: string, docs = documents) {
  return http.get(`/api/library/systems/${slug}`, () =>
    HttpResponse.json({ slug, name: slug[0].toUpperCase() + slug.slice(1), documents: docs }),
  )
}

async function findDocumentRows() {
  const list = await screen.findByRole('list', { name: 'Documents' })
  return within(list)
    .getAllByRole('listitem')
    .filter((item) => item.parentElement === list)
}

function renderPage(slug: string) {
  return render(
    <MemoryRouter initialEntries={[`/library/browse/${slug}`]}>
      <Routes>
        <Route path="/library/browse/:slug" element={<LibrarySystemPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('INTEGRATE System folder', () => {
  it('shows the breadcrumb, the System heading and its tagline', async () => {
    server.use(systemHandler('inspire'))
    renderPage('inspire')

    const breadcrumb = within(screen.getByRole('navigation', { name: 'Breadcrumb' }))
    expect(breadcrumb.getByRole('link', { name: 'Resource Library' })).toHaveAttribute('href', '/library')
    expect(breadcrumb.getByRole('link', { name: 'Browse' })).toHaveAttribute('href', '/library/browse')
    expect(breadcrumb.getByText('Inspire')).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('heading', { level: 1, name: 'Inspire' })).toBeVisible()
    expect(screen.getByText('Leadership — from command to connection')).toBeVisible()
  })

  it('lists each document with its type, update date and other spotlighted Systems', async () => {
    server.use(systemHandler('inspire'))
    renderPage('inspire')

    const rows = await findDocumentRows()
    expect(rows).toHaveLength(2)

    const alpha = within(rows[0])
    expect(alpha.getByRole('heading', { name: 'Sample Practice Alpha' })).toBeVisible()
    expect(alpha.getByText('LSP')).toBeVisible()
    expect(alpha.getByText('Updated Mar 4, 2026')).toBeVisible()
    const chips = within(alpha.getByRole('list', { name: 'Also in' }))
    expect(chips.getAllByRole('listitem').map((chip) => chip.textContent)).toEqual(['Nurture', 'Engage'])

    const beta = within(rows[1])
    expect(beta.getByText('Field Guide')).toBeVisible()
    expect(beta.queryByText(/^Updated/)).not.toBeInTheDocument()
    expect(beta.queryByRole('list', { name: 'Also in' })).not.toBeInTheDocument()
  })

  it('says when a System has no documents yet', async () => {
    server.use(systemHandler('trust', []))
    renderPage('trust')

    expect(await screen.findByText(/no documents in Trust yet/i)).toBeVisible()
    expect(screen.queryByRole('list', { name: 'Documents' })).not.toBeInTheDocument()
  })

  it('invites the Member to ask the Librarian about the System', async () => {
    server.use(systemHandler('inspire'))
    renderPage('inspire')

    await findDocumentRows()
    const prompt = within(screen.getByRole('complementary', { name: 'Ask the Librarian' }))
    expect(prompt.getByText('Have a question about Inspire?')).toBeVisible()
    expect(prompt.getByRole('link', { name: 'Ask the Librarian' })).toHaveAttribute('href', '/chat')
  })

  it('shows a not-found message with a way back for an unknown System', () => {
    renderPage('not-a-system')

    expect(screen.getByRole('heading', { level: 1, name: 'Folder not found' })).toBeVisible()
    expect(screen.getByRole('link', { name: 'Back to Browse the Library' })).toHaveAttribute(
      'href',
      '/library/browse',
    )
  })

  it('shows an error when the documents cannot be loaded', async () => {
    server.use(http.get('/api/library/systems/inspire', () => new HttpResponse(null, { status: 500 })))
    renderPage('inspire')

    expect(await screen.findByRole('alert')).toHaveTextContent(/couldn.t load these documents/i)
  })

  describe('Open', () => {
    const { createObjectURL, revokeObjectURL } = URL

    afterEach(() => {
      vi.restoreAllMocks()
      URL.createObjectURL = createObjectURL
      URL.revokeObjectURL = revokeObjectURL
    })

    it("fetches the document's PDF with the Member's token and shows it in a new tab", async () => {
      localStorage.setItem('token', 'member-token')
      let authorization: string | null = null
      server.use(
        systemHandler('inspire'),
        http.get('/api/library/documents/doc-a/file', ({ request }) => {
          authorization = request.headers.get('Authorization')
          return new HttpResponse('%PDF-1.4', {
            headers: { 'Content-Type': 'application/pdf' },
          })
        }),
      )
      const tab = { location: { href: '' }, close: vi.fn() }
      const open = vi.spyOn(window, 'open').mockReturnValue(tab as unknown as Window)
      URL.createObjectURL = vi.fn(() => 'blob:library-document')
      URL.revokeObjectURL = vi.fn()
      renderPage('inspire')

      const [alpha] = await findDocumentRows()
      await userEvent.setup().click(within(alpha).getByRole('button', { name: /^Open/ }))

      expect(open).toHaveBeenCalledWith('', '_blank')
      await waitFor(() => expect(tab.location.href).toBe('blob:library-document'))
      expect(authorization).toBe('Bearer member-token')
    })

    it('closes the new tab and explains when the document cannot be opened', async () => {
      server.use(
        systemHandler('inspire'),
        http.get('/api/library/documents/doc-a/file', () => new HttpResponse(null, { status: 404 })),
      )
      const tab = { location: { href: '' }, close: vi.fn() }
      vi.spyOn(window, 'open').mockReturnValue(tab as unknown as Window)
      renderPage('inspire')

      const [alpha] = await findDocumentRows()
      await userEvent.setup().click(within(alpha).getByRole('button', { name: /^Open/ }))

      await waitFor(() => expect(tab.close).toHaveBeenCalled())
      expect(within(alpha).getByRole('alert')).toHaveTextContent(/couldn.t open this document/i)
    })

    it('names each Open button after its document', async () => {
      server.use(systemHandler('inspire'))
      renderPage('inspire')

      await findDocumentRows()
      expect(screen.getByRole('button', { name: 'Open Sample Practice Alpha' })).toBeVisible()
      expect(screen.getByRole('button', { name: 'Open Sample Field Guide Beta' })).toBeVisible()
    })

    it('asks the Member to allow pop-ups when the browser blocks the new tab', async () => {
      let requested = false
      server.use(
        systemHandler('inspire'),
        http.get('/api/library/documents/doc-a/file', () => {
          requested = true
          return new HttpResponse('%PDF-1.4')
        }),
      )
      vi.spyOn(window, 'open').mockReturnValue(null)
      renderPage('inspire')

      const [alpha] = await findDocumentRows()
      await userEvent.setup().click(within(alpha).getByRole('button', { name: /^Open/ }))

      expect(await within(alpha).findByRole('alert')).toHaveTextContent(/allow pop-ups/i)
      expect(requested).toBe(false)
    })
  })
})
