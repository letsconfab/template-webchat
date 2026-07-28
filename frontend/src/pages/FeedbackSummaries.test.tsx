import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, http } from 'msw'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { FeedbackSummaryLibrary } from '../components/admin/FeedbackSummaryLibrary'
import { resolveMarkdownImageSrc } from '../components/Markdown'
import AdminFeedbackCasesPage from '../pages/AdminFeedbackCasesPage'
import AdminFeedbackSummaryPage from '../pages/AdminFeedbackSummaryPage'
import { server } from '../test/server'

vi.mock('mermaid', () => ({
  default: {
    initialize: vi.fn(),
    render: vi.fn(async (_id: string, chart: string) => ({
      svg: `<svg data-testid="mermaid-svg"><title>${chart}</title></svg>`,
    })),
  },
}))

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 1, email: 'admin@example.com', role: 'admin' },
    logout: vi.fn(),
    isAuthenticated: true,
    isAdmin: true,
    isLoading: false,
    featuresLoaded: true,
    features: {
      admin_replay_enabled: true,
      tester_correspondence_enabled: true,
      tester_email_notifications_enabled: true,
    },
  }),
}))

const indexPayload = {
  schema_version: 1,
  summaries: [
    {
      artifact_id: 'newer-summary',
      title: 'Newer Summary',
      generated_at: '2026-07-28T00:00:00Z',
      window_start: '2026-06-27T00:00:00Z',
      window_end: '2026-07-27T00:00:00Z',
      content_url:
        '/static/feedback-summaries/artifacts/newer-summary/abc/summary.md',
      asset_base_url: '/static/feedback-summaries/artifacts/newer-summary/abc/',
    },
    {
      artifact_id: 'older-summary',
      title: 'Older Summary',
      generated_at: '2026-07-01T00:00:00Z',
      window_start: '2026-05-31T00:00:00Z',
      window_end: '2026-06-30T00:00:00Z',
      content_url:
        '/static/feedback-summaries/artifacts/older-summary/def/summary.md',
      asset_base_url: '/static/feedback-summaries/artifacts/older-summary/def/',
    },
  ],
}

const summaryMarkdown = `## Executive summary

Themes only.

## Evidence snapshot

| Measure | Result |
|---|---:|
| Negative | 11 |

## Major themes

Paraphrased.

## Limitations and caveats

Small sample.

![Chart](assets/chart.svg)

\`\`\`mermaid
flowchart LR
  A --> B
\`\`\`
`

afterEach(() => {
  vi.unstubAllGlobals()
})

function stubStaticFetch(handlers: {
  index?: Response | null
  markdownByUrl?: Record<string, Response | null>
}) {
  const originalFetch = globalThis.fetch.bind(globalThis)
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url.includes('/static/feedback-summaries/index.json')) {
      if (handlers.index === null) throw new Error('network down')
      return (
        handlers.index ??
        new Response(JSON.stringify(indexPayload), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      )
    }
    if (handlers.markdownByUrl && url in handlers.markdownByUrl) {
      const value = handlers.markdownByUrl[url]
      if (value === null) throw new Error('network down')
      return value
    }
    if (url.includes('/static/feedback-summaries/') && url.includes('/summary.md')) {
      return new Response(summaryMarkdown, { status: 200 })
    }
    if (url.includes('/static/feedback-summaries/')) {
      return new Response('not found', { status: 404 })
    }
    return originalFetch(input, init)
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('FeedbackSummaryLibrary', () => {
  it('renders packaged summaries newest-first with evidence and generation dates', async () => {
    stubStaticFetch({})
    render(
      <MemoryRouter>
        <FeedbackSummaryLibrary />
      </MemoryRouter>,
    )

    const newer = await screen.findByRole('link', { name: /Newer Summary/i })
    const older = screen.getByRole('link', { name: /Older Summary/i })
    expect(newer.compareDocumentPosition(older) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(newer).toHaveAttribute(
      'href',
      '/admin/feedback/summaries/newer-summary',
    )
    expect(screen.getAllByText(/Evidence window:/i).length).toBe(2)
    expect(screen.getAllByText(/Generated/i).length).toBe(2)
  })

  it('shows the empty state without blocking the page', async () => {
    stubStaticFetch({
      index: new Response(
        JSON.stringify({ schema_version: 1, summaries: [] }),
        { status: 200 },
      ),
    })
    render(
      <MemoryRouter>
        <FeedbackSummaryLibrary />
      </MemoryRouter>,
    )
    expect(
      await screen.findByText('No feedback summaries available.'),
    ).toBeInTheDocument()
  })

  it('shows unavailable when the index cannot be loaded', async () => {
    stubStaticFetch({ index: null })
    render(
      <MemoryRouter>
        <FeedbackSummaryLibrary />
      </MemoryRouter>,
    )
    expect(
      await screen.findByText('Feedback summaries unavailable.'),
    ).toBeInTheDocument()
  })
})

describe('AdminFeedbackCasesPage list with summaries', () => {
  it('places the summary library above filters and still loads cases', async () => {
    stubStaticFetch({})
    server.use(
      http.get('/api/admin/feedback-cases', () =>
        HttpResponse.json({
          cases: [
            {
              case_id: 'case-1',
              status: 'awaiting_admin',
              categories: [],
              comment: 'Need clarity',
              comment_redaction_status: 'succeeded',
              account_email: 't***@example.test',
              created_at: '2026-07-04T12:00:00Z',
            },
          ],
        }),
      ),
    )

    render(
      <MemoryRouter initialEntries={['/admin/feedback']}>
        <Routes>
          <Route path="/admin/feedback" element={<AdminFeedbackCasesPage />} />
        </Routes>
      </MemoryRouter>,
    )

    const heading = await screen.findByText('Feedback summaries')
    const filter = await screen.findByDisplayValue('All statuses')
    expect(
      heading.compareDocumentPosition(filter) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy()
    expect(await screen.findByText('t***@example.test')).toBeInTheDocument()
  })

  it('does not show the summary library on a Feedback Case detail route', async () => {
    stubStaticFetch({})
    server.use(
      http.get('/api/settings/features', () =>
        HttpResponse.json({
          admin_replay_enabled: true,
          tester_correspondence_enabled: true,
          tester_email_notifications_enabled: true,
        }),
      ),
      http.get('/api/admin/feedback-cases/case-123/replay', () =>
        HttpResponse.json({
          case: {
            case_id: 'case-123',
            status: 'awaiting_admin',
            categories: [],
            comment: 'Please provide more detail.',
            comment_redaction_status: 'succeeded',
            account_email: 't***@example.test',
            created_at: '2026-07-04T12:00:00Z',
          },
          messages: [],
          replies: [],
          next_cursor: null,
        }),
      ),
    )

    render(
      <MemoryRouter initialEntries={['/admin/feedback/case-123']}>
        <Routes>
          <Route
            path="/admin/feedback/:caseId"
            element={<AdminFeedbackCasesPage />}
          />
        </Routes>
      </MemoryRouter>,
    )

    await screen.findByPlaceholderText('Reply to tester')
    expect(screen.queryByText('Feedback summaries')).not.toBeInTheDocument()
  })
})

describe('AdminFeedbackSummaryPage', () => {
  it('renders metadata, markdown, and relative images for a known artifact', async () => {
    stubStaticFetch({})
    render(
      <MemoryRouter initialEntries={['/admin/feedback/summaries/newer-summary']}>
        <Routes>
          <Route
            path="/admin/feedback/summaries/:artifactId"
            element={<AdminFeedbackSummaryPage />}
          />
        </Routes>
      </MemoryRouter>,
    )

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Newer Summary' }),
    ).toBeInTheDocument()
    expect(screen.getByText(/Evidence window:/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Feedback cases' })).toHaveAttribute(
      'href',
      '/admin/feedback',
    )
    await waitFor(() => {
      const img = screen.getByRole('img', { name: 'Chart' })
      expect(img).toHaveAttribute(
        'src',
        '/static/feedback-summaries/artifacts/newer-summary/abc/assets/chart.svg',
      )
    })
    expect(screen.getByRole('heading', { name: 'Executive summary' })).toBeInTheDocument()
  })

  it('renders the not-found state for an unknown artifact id', async () => {
    stubStaticFetch({})
    render(
      <MemoryRouter initialEntries={['/admin/feedback/summaries/missing']}>
        <Routes>
          <Route
            path="/admin/feedback/summaries/:artifactId"
            element={<AdminFeedbackSummaryPage />}
          />
        </Routes>
      </MemoryRouter>,
    )

    expect(await screen.findByText('Summary not found')).toBeInTheDocument()
    expect(
      screen.getByRole('link', { name: 'Return to feedback cases' }),
    ).toHaveAttribute('href', '/admin/feedback')
  })

  it('navigates from the library link to the detail route', async () => {
    stubStaticFetch({})
    const user = userEvent.setup()
    render(
      <MemoryRouter initialEntries={['/admin/feedback']}>
        <Routes>
          <Route path="/admin/feedback" element={<FeedbackSummaryLibrary />} />
          <Route
            path="/admin/feedback/summaries/:artifactId"
            element={<AdminFeedbackSummaryPage />}
          />
        </Routes>
      </MemoryRouter>,
    )

    await user.click(await screen.findByRole('link', { name: /Newer Summary/i }))
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Newer Summary' }),
    ).toBeInTheDocument()
  })
})

describe('resolveMarkdownImageSrc', () => {
  it('resolves relative images against assetBaseUrl and leaves absolute URLs alone', () => {
    expect(
      resolveMarkdownImageSrc(
        'assets/chart.svg',
        '/static/feedback-summaries/artifacts/x/hash/',
      ),
    ).toBe('/static/feedback-summaries/artifacts/x/hash/assets/chart.svg')
    expect(
      resolveMarkdownImageSrc('https://example.com/a.png', '/static/base/'),
    ).toBe('https://example.com/a.png')
    expect(resolveMarkdownImageSrc('assets/chart.svg')).toBe('assets/chart.svg')
    expect(
      resolveMarkdownImageSrc('../escape.svg', '/static/base/'),
    ).toBeUndefined()
  })
})
