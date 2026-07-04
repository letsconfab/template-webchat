import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, http } from 'msw'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import { server } from '../test/server'
import AdminFeedbackCasesPage from './AdminFeedbackCasesPage'

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

function replayHandler() {
  return http.get(`/api/admin/feedback-cases/${caseId}/replay`, () =>
    HttpResponse.json(replayResponse()),
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
