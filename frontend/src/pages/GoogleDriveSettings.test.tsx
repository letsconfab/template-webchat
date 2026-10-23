import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, http } from 'msw'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import { server } from '../test/server'
import GoogleDriveSettings from './GoogleDriveSettings'

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 1, email: 'admin@example.com', role: 'admin' },
    logout: vi.fn(),
    isAuthenticated: true,
    isAdmin: true,
    isLoading: false,
  }),
}))

const SYSTEMS = [
  ['inspire', 'Inspire'],
  ['nurture', 'Nurture'],
  ['trust', 'Trust'],
  ['embody', 'Embody'],
  ['guide', 'Guide'],
  ['regulate', 'Regulate'],
  ['align', 'Align'],
  ['transcend', 'Transcend'],
  ['engage', 'Engage'],
].map(([slug, name]) => ({ slug, name }))

function driveStatus() {
  return {
    connected: true,
    root_folder_id: 'folder_0123456789',
    library_manifest_file_id: 'sheet_0123456789',
    library: { document_count: 3, synced_at: '2026-10-01T00:00:00', issues: [] },
    sync: { file_count: 0, last_sync: null, running: false, error: null },
    files: [],
    pipeline: { running: false, last_update: null, error: null },
  }
}

function doc(fileId: string, title: string, type: string, systems: string[]) {
  return {
    file_id: fileId,
    title,
    organization: 'Example Org',
    type,
    systems,
    status: 'ok',
  }
}

function adminLibrary() {
  return {
    manifest_file_id: 'sheet_0123456789',
    manifest_url: 'https://docs.google.com/spreadsheets/d/sheet_0123456789/edit',
    synced_at: '2026-10-01T00:00:00',
    systems: SYSTEMS,
    documents: [
      doc('doc_a', 'Sample Practice One', 'LSP', ['trust', 'inspire']),
      doc('doc_b', 'Sample Practice Two', 'Field Guide', ['inspire']),
      doc('ref_c', 'Sample Reference', 'Reference', []),
    ],
    issues: [
      { row: null, code: 'manifest_unreachable', detail: 'HttpError', file_id: null, title: null, link: null },
      { row: 3, code: 'bad_link', detail: 'x', file_id: null, title: 'Linkless Row', link: null },
      {
        row: 5,
        code: 'missing_title',
        detail: 'x',
        file_id: 'doc_d',
        title: null,
        link: 'https://drive.google.com/file/d/doc_d/view',
      },
      {
        row: 7,
        code: 'unreachable',
        detail: 'Google Drive returned HTTP 404',
        file_id: 'doc_e',
        title: 'Sample Practice Three',
        link: 'https://drive.google.com/file/d/doc_e/view',
      },
      { row: 8, code: 'bad_type', detail: 'x', file_id: 'doc_f', title: 'Sample Practice Four', link: null },
    ],
  }
}

function useHandlers(library = adminLibrary) {
  let libraryReads = 0
  server.use(
    http.get('/api/drive/status', () => HttpResponse.json(driveStatus())),
    http.get('/api/admin/library', () => {
      libraryReads += 1
      return HttpResponse.json(library())
    }),
    http.post('/api/drive/sync-now', () => HttpResponse.json({ status: 'ok' })),
  )
  return () => libraryReads
}

function renderPage() {
  return render(
    <MemoryRouter>
      <GoogleDriveSettings />
    </MemoryRouter>,
  )
}

describe('Library contents on the admin Knowledge page', () => {
  it('groups documents by INTEGRATE System in canonical order, then References, with counts', async () => {
    useHandlers()
    renderPage()

    const section = await screen.findByRole('region', { name: 'Library contents' })
    const groups = await within(section).findAllByTestId('library-group')
    expect(groups.map(g => g.querySelector('summary')?.textContent)).toEqual([
      'Inspire2',
      'Nurture0',
      'Trust1',
      'Embody0',
      'Guide0',
      'Regulate0',
      'Align0',
      'Transcend0',
      'Engage0',
      'References1',
    ])
    // A document appears under every System it spotlights.
    expect(within(groups[0]).getByText('Sample Practice One')).toBeInTheDocument()
    expect(within(groups[2]).getByText('Sample Practice One')).toBeInTheDocument()
    expect(within(groups[9]).getByText('Sample Reference')).toBeInTheDocument()
  })

  it('lists Needs attention with manifest row, title or link, and a plain-language reason', async () => {
    useHandlers()
    renderPage()

    const list = await screen.findByRole('list', { name: 'Needs attention' })
    const items = within(list).getAllByRole('listitem')
    expect(items).toHaveLength(5)

    expect(items[0]).toHaveTextContent(/Library Manifest could not be read/)
    expect(items[1]).toHaveTextContent('Row 3')
    expect(items[1]).toHaveTextContent('Linkless Row')
    expect(items[1]).toHaveTextContent(/not a Google Doc or Drive file link/)
    expect(items[2]).toHaveTextContent('Row 5')
    expect(within(items[2]).getByRole('link')).toHaveAttribute('href', 'https://drive.google.com/file/d/doc_d/view')
    expect(items[2]).toHaveTextContent(/Title cell is empty/)
    // Drive failures keep the actual cause next to the plain-language reason.
    expect(items[3]).toHaveTextContent(/could not be opened/)
    expect(items[3]).toHaveTextContent('Google Drive returned HTTP 404')
    expect(items[4]).toHaveTextContent(/Type is not LSP, Field Guide, or Reference/)
  })

  it('links to the manifest sheet', async () => {
    useHandlers()
    renderPage()

    const link = await screen.findByRole('link', { name: /Open the Library Manifest/ })
    expect(link).toHaveAttribute('href', 'https://docs.google.com/spreadsheets/d/sheet_0123456789/edit')
  })

  it('shows no Needs attention list when the sync found nothing wrong', async () => {
    useHandlers(() => ({ ...adminLibrary(), issues: [] }))
    renderPage()

    await screen.findByRole('region', { name: 'Library contents' })
    expect(screen.queryByRole('list', { name: 'Needs attention' })).not.toBeInTheDocument()
  })

  it('reloads the library contents after Sync now', async () => {
    const libraryReads = useHandlers()
    renderPage()
    await screen.findByRole('region', { name: 'Library contents' })
    const before = libraryReads()

    await userEvent.click(screen.getByRole('button', { name: /Sync Now/ }))

    await waitFor(() => expect(libraryReads()).toBeGreaterThan(before))
  })
})
