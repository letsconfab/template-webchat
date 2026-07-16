import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, http } from 'msw'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import { server } from '../test/server'
import AdminFeedbackCasesPage from './AdminFeedbackCasesPage'

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

const caseId = 'case-123'

function replayResponse() {
  return {
    case: {
      case_id: caseId,
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
  }
}

function renderCasePage() {
  return render(
    <MemoryRouter initialEntries={[`/admin/feedback/${caseId}`]}>
      <Routes>
        <Route
          path="/admin/feedback/:caseId"
          element={<AdminFeedbackCasesPage />}
        />
      </Routes>
    </MemoryRouter>,
  )
}

function featureHandler(correspondenceEnabled: boolean) {
  return http.get('/api/settings/features', () =>
    HttpResponse.json({
      admin_replay_enabled: true,
      tester_correspondence_enabled: correspondenceEnabled,
      tester_email_notifications_enabled: correspondenceEnabled,
    }),
  )
}

function replayHandler(overrides: Partial<ReturnType<typeof replayResponse>> = {}) {
  return http.get(`/api/admin/feedback-cases/${caseId}/replay`, () =>
    HttpResponse.json({ ...replayResponse(), ...overrides }),
  )
}

describe('AdminFeedbackCasesPage', () => {
  it('explains why correspondence actions are unavailable', async () => {
    server.use(featureHandler(false), replayHandler())

    renderCasePage()
    await screen.findByPlaceholderText('Reply to tester')

    expect(screen.getByRole('alert')).toHaveTextContent(
      'Correspondence is not enabled',
    )
    expect(screen.getByRole('button', { name: 'Send reply' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Resolve' })).toBeDisabled()
  })

  it('keeps the draft and shows an error when a reply cannot be sent', async () => {
    server.use(
      featureHandler(true),
      replayHandler(),
      http.post(`/api/admin/feedback-cases/${caseId}/replies`, () =>
        HttpResponse.json(
          { detail: 'Feature not enabled' },
          { status: 404 },
        ),
      ),
    )
    const user = userEvent.setup()

    renderCasePage()
    const draft = await screen.findByPlaceholderText('Reply to tester')
    await user.type(draft, 'Thanks for the feedback.')
    await user.click(screen.getByRole('button', { name: 'Send reply' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Reply could not be sent',
    )
    expect(draft).toHaveValue('Thanks for the feedback.')
    expect(screen.getByRole('button', { name: 'Send reply' })).toBeEnabled()
  })

  it('shows a sent reply and updated case status without reloading', async () => {
    let submittedText = ''
    let submitCount = 0
    server.use(
      featureHandler(true),
      replayHandler(),
      http.post(
        `/api/admin/feedback-cases/${caseId}/replies`,
        async ({ request }) => {
          submitCount += 1
          const payload = await request.json() as { text: string }
          submittedText = payload.text
          return HttpResponse.json(
            {
              id: 17,
              status: 'awaiting_user',
              created_at: '2026-07-04T12:05:00Z',
              notification: {
                id: 9,
                state: 'sent',
                safe_error_category: null,
              },
            },
            { status: 201 },
          )
        },
      ),
    )
    const user = userEvent.setup()

    renderCasePage()
    const draft = await screen.findByPlaceholderText('Reply to tester')
    await user.type(draft, 'Thanks for the feedback.')
    await user.click(screen.getByRole('button', { name: 'Send reply' }))

    expect(await screen.findByText('Reply sent.')).toBeVisible()
    expect(screen.getByText('Thanks for the feedback.')).toBeVisible()
    expect(screen.getByText('awaiting user')).toBeVisible()
    expect(draft).toHaveValue('')
    expect(submittedText).toBe('Thanks for the feedback.')
    expect(submitCount).toBe(1)
  })

  it('renders succeeded assistant replay content as Markdown, not raw text', async () => {
    server.use(
      featureHandler(false),
      replayHandler({
        messages: [
          {
            id: 1,
            role: 'assistant',
            content: '## Level 1\n\n**bold**\n\n| a | b |\n| - | - |\n| 1 | 2 |',
            redaction_status: 'succeeded',
            created_at: '2026-07-04T12:01:00Z',
            is_rated: false,
            is_post_feedback: false,
            execution_trace: null,
          },
        ],
      }),
    )

    const { container } = renderCasePage()
    await screen.findByPlaceholderText('Reply to tester')

    // Markdown is rendered to real DOM elements...
    expect(container.querySelector('h2')).toHaveTextContent('Level 1')
    expect(container.querySelector('strong')).toHaveTextContent('bold')
    expect(container.querySelector('table')).toBeInTheDocument()
    // ...and the literal syntax is gone.
    expect(screen.queryByText(/## Level 1/)).not.toBeInTheDocument()
    expect(screen.queryByText(/\| a \| b \|/)).not.toBeInTheDocument()
  })

  it('keeps unavailable replay content plain and does not render it as Markdown', async () => {
    server.use(
      featureHandler(false),
      replayHandler({
        messages: [
          {
            id: 2,
            role: 'assistant',
            content: null,
            redaction_status: 'pending',
            created_at: '2026-07-04T12:02:00Z',
            is_rated: false,
            is_post_feedback: false,
            execution_trace: null,
          },
        ],
      }),
    )

    const { container } = renderCasePage()
    await screen.findByPlaceholderText('Reply to tester')

    expect(
      screen.getByText('Content unavailable pending privacy processing'),
    ).toBeVisible()
    expect(container.querySelector('h2')).not.toBeInTheDocument()
  })

  it('shows an error when case resolution fails', async () => {
    server.use(
      featureHandler(true),
      replayHandler(),
      http.post(`/api/admin/feedback-cases/${caseId}/resolve`, () =>
        HttpResponse.json({ detail: 'Temporary failure' }, { status: 500 }),
      ),
    )
    const user = userEvent.setup()

    renderCasePage()
    await user.click(await screen.findByRole('button', { name: 'Resolve' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Case could not be resolved',
    )
    expect(screen.getByRole('button', { name: 'Resolve' })).toBeEnabled()
  })
})
