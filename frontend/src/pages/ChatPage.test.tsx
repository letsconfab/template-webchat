import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { server } from '../test/server'
import ChatPage from './ChatPage'

type Frame = Record<string, unknown>

const { FakeChatWebSocket, sockets, journeys } = vi.hoisted(() => {
  const sockets: InstanceType<typeof FakeChatWebSocket>[] = []

  class FakeChatWebSocket {
    private messageHandler: ((data: Record<string, unknown>) => void) | null = null
    private connectionHandler: ((connected: boolean) => void) | null = null
    sent: string[] = []

    constructor() {
      sockets.push(this)
    }
    connect() {
      queueMicrotask(() => this.connectionHandler?.(true))
    }
    disconnect() {}
    sendMessage(message: string) {
      this.sent.push(message)
    }
    onMessage(handler: (data: Record<string, unknown>) => void) {
      this.messageHandler = handler
    }
    onError() {}
    onConnection(handler: (connected: boolean) => void) {
      this.connectionHandler = handler
    }
    deliver(frame: Record<string, unknown>) {
      this.messageHandler?.(frame)
    }
  }

  const journeys = [
    {
      id: 1,
      title: 'Repairing trust',
      purpose: 'Start from a breach of trust on a team.',
      starter_prompt: 'How do teams repair trust?',
      icon: null,
      knowledge_source_labels: [],
    },
  ]

  return { FakeChatWebSocket, sockets, journeys }
})

type FakeSocket = InstanceType<typeof FakeChatWebSocket>

function emit(socket: FakeSocket, frame: Frame) {
  act(() => socket.deliver(frame))
}

const auth = vi.hoisted(() => ({
  user: { id: 2, email: 'member@example.com', role: 'user' },
  logout: () => {},
  isAdmin: false,
  features: {},
}))

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => auth,
}))

vi.mock('../services/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/api')>()
  return {
    ...actual,
    ChatWebSocket: FakeChatWebSocket,
    setSessionId: vi.fn(),
    listChatSessions: vi.fn(async () => [
      { client_uuid: 'session-1', title: 'First chat', updated_at: '2026-10-01T00:00:00Z' },
    ]),
    listActiveJourneys: vi.fn(async () => journeys),
  }
})

const libraryCitation = {
  id: 'lib_1',
  title: 'Practice One',
  type: 'LSP',
  systems: ['trust', 'engage'],
  url: '/api/library/documents/lib_1/file',
}
const referenceCitation = {
  id: 'ref_1',
  title: 'Sample Reference',
  type: 'Reference',
  systems: [],
  url: '/api/library/documents/ref_1/file',
}

beforeEach(() => {
  sockets.length = 0
  // jsdom has no layout, so it does not implement scrollIntoView.
  Element.prototype.scrollIntoView = vi.fn()
  server.use(
    http.get('*/api/settings/chat-config', () =>
      HttpResponse.json({ llm_provider: 'openai', llm_model: 'gpt-4o-mini' }),
    ),
    http.get('*/api/drive/status', () => HttpResponse.json({ connected: true })),
  )
})

afterEach(() => {
  vi.restoreAllMocks()
})

async function renderChat() {
  render(
    <MemoryRouter initialEntries={['/chat/session-1']}>
      <Routes>
        <Route path="/chat/:sessionId" element={<ChatPage />} />
      </Routes>
    </MemoryRouter>,
  )
  await waitFor(() => expect(sockets.length).toBeGreaterThan(0))
  const socket = sockets[sockets.length - 1]
  emit(socket, { type: 'history', messages: [] })
  return socket
}

function answer(socket: FakeSocket, frame: Frame) {
  emit(socket, { type: 'start' })
  emit(socket, { type: 'chunk', content: frame.content })
  emit(socket, { type: 'end', message_id: 9, ...frame })
}

describe('Ask the Librarian chat page', () => {
  it('is titled Ask the Librarian inside the library chrome', async () => {
    await renderChat()

    expect(screen.getByRole('heading', { level: 1, name: 'Ask the Librarian' })).toBeVisible()
    expect(
      screen.getAllByText(
        "Ask a question in plain language. Answers come only from the Consortium's own library.",
      )[0],
    ).toBeVisible()
    expect(document.title).toBe('Ask the Librarian')
    expect(screen.getByRole('link', { name: 'Resource Library home' })).toHaveAttribute(
      'href',
      '/library',
    )
  })

  it('keeps the conversation list one tap away on small screens', async () => {
    const user = userEvent.setup()
    await renderChat()

    expect(screen.queryByRole('button', { name: /new chat/i })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Conversations' }))

    expect(screen.getByRole('button', { name: /new chat/i })).toBeVisible()
    expect(screen.getByRole('button', { name: /First chat/ })).toBeVisible()
  })

  it('offers Journeys as starter-question cards in the empty state', async () => {
    const user = userEvent.setup()
    await renderChat()

    const card = await screen.findByRole('button', { name: /Repairing trust/ })
    await user.click(card)

    expect(screen.getByRole('textbox', { name: 'Ask the Librarian a question' })).toHaveValue(
      'How do teams repair trust?',
    )
  })

  it('labels answers as the Librarian and cites documents as chips', async () => {
    const user = userEvent.setup()
    const socket = await renderChat()
    answer(socket, {
      content: 'Teams build trust through repair.',
      citations: [libraryCitation, referenceCitation],
    })

    const reply = screen.getByRole('article', { name: 'Librarian' })
    expect(within(reply).getByText('Librarian')).toBeVisible()

    const sources = within(reply).getByRole('list', { name: 'Sources' })
    const [library, reference] = within(sources).getAllByRole('listitem')
    expect(within(library).getByRole('button', { name: /Practice One/ })).toBeVisible()
    expect(within(library).getByText('Trust')).toBeVisible()
    expect(within(library).getByText('Engage')).toBeVisible()
    expect(within(library).queryByText('Reference')).not.toBeInTheDocument()
    expect(within(reference).getByRole('button', { name: /Sample Reference/ })).toBeVisible()
    expect(within(reference).getByText('Reference')).toBeVisible()
    expect(within(reference).queryByText('Trust')).not.toBeInTheDocument()

    const requested: string[] = []
    server.use(
      http.get('*/api/library/documents/:id/file', ({ params, request }) => {
        requested.push(`${params.id} ${request.headers.get('authorization')}`)
        return new HttpResponse('%PDF', {
          headers: { 'Content-Type': 'application/pdf' },
        })
      }),
    )
    localStorage.setItem('token', 'member-token')
    const tab = { location: { href: '' }, close: vi.fn() }
    const open = vi.spyOn(window, 'open').mockReturnValue(tab as unknown as Window)
    URL.createObjectURL = vi.fn(() => 'blob:pdf')
    URL.revokeObjectURL = vi.fn()

    await user.click(within(library).getByRole('button', { name: /Practice One/ }))

    expect(open).toHaveBeenCalledWith('', '_blank')
    await waitFor(() => expect(tab.location.href).toBe('blob:pdf'))
    expect(requested).toEqual(['lib_1 Bearer member-token'])
  })

  it('closes the new tab and explains when a cited document cannot be opened', async () => {
    const user = userEvent.setup()
    const socket = await renderChat()
    answer(socket, { content: 'Teams build trust through repair.', citations: [libraryCitation] })
    server.use(
      http.get('*/api/library/documents/:id/file', () => new HttpResponse(null, { status: 404 })),
    )
    const tab = { location: { href: '' }, close: vi.fn() }
    vi.spyOn(window, 'open').mockReturnValue(tab as unknown as Window)
    vi.spyOn(console, 'error').mockImplementation(() => {})

    const reply = screen.getByRole('article', { name: 'Librarian' })
    await user.click(within(reply).getByRole('button', { name: /Practice One/ }))

    expect(await within(reply).findByRole('alert')).toHaveTextContent(/couldn.t open this document/i)
    expect(tab.close).toHaveBeenCalled()
  })

  it('follows a refusal with a link to browse the library', async () => {
    const socket = await renderChat()
    const refusal = 'I could not find that in the library.'
    answer(socket, { content: refusal, refusal: true })

    const reply = screen.getByRole('article', { name: 'Librarian' })
    expect(within(reply).getByText(refusal)).toBeVisible()
    expect(within(reply).getByRole('link', { name: 'Browse the Library' })).toHaveAttribute(
      'href',
      '/library/browse',
    )
  })

  it('does not offer the browse link on a grounded answer', async () => {
    const socket = await renderChat()
    answer(socket, { content: 'Teams build trust through repair.', citations: [libraryCitation] })

    const reply = screen.getByRole('article', { name: 'Librarian' })
    expect(within(reply).queryByRole('link', { name: 'Browse the Library' })).not.toBeInTheDocument()
  })
})
