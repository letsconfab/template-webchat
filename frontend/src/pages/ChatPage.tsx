import { useState, useRef, useEffect, useCallback } from 'react'
import { useNavigate, Link, useParams } from 'react-router-dom'
import {
  Send,
  Loader2,
  Settings,
  LogOut,
  MessageSquare,
  ThumbsUp,
  ThumbsDown,
  CircleCheck,
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  Brain,
} from 'lucide-react'
import {
  ChatWebSocket,
  type Settings as ChatSettings,
  type ChatSessionSummary,
  type JourneySummary,
  setSessionId,
  clearSessionId,
  listChatSessions,
  createChatSession,
  renameChatSession,
  deleteChatSession,
  listActiveJourneys,
  api,
} from '../services/api'
import { useAuth } from '../contexts/AuthContext'
import { Badge } from '../components/ui/badge'
import { Textarea } from '../components/ui/textarea'
import { Markdown } from '../components/Markdown'
import { ChatSessionSidebar } from '../components/ChatSessionSidebar'
import { JourneyStarterGrid } from '../components/JourneyStarterGrid'

interface Message {
  role: 'user' | 'assistant'
  content: string
  feedback?: 'thumbs_up' | 'thumbs_down' | null
  thoughts?: string[]
  message_id?: number | null
  feedbackId?: number
  caseId?: string
  feedbackDetailed?: boolean
}

const FEEDBACK_CATEGORIES: { slug: string; label: string }[] = [
  { slug: 'inaccurate', label: 'Inaccurate' },
  { slug: 'incomplete', label: 'Incomplete' },
  { slug: 'off_topic', label: 'Off topic' },
  { slug: 'outdated', label: 'Outdated' },
  { slug: 'too_long', label: 'Too long' },
  { slug: 'other', label: 'Other' },
]

interface GraphRAGStatus {
  connected: boolean
  files_cached: number
  last_sync: string | null
  pipeline_running: boolean
  pipeline_last_update: string | null
  ready: boolean
}

export default function ChatPage() {
  const navigate = useNavigate()
  const { sessionId: routeSessionId } = useParams<{ sessionId?: string }>()
  const { user, logout, isAdmin, features } = useAuth()
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [isConnected, setIsConnected] = useState(false)
  const [isStreaming, setIsStreaming] = useState(false)
  const [currentResponse, setCurrentResponse] = useState('')
  const [settings, setSettings] = useState<ChatSettings | null>(null)
  const [graphragStatus, setGraphragStatus] = useState<GraphRAGStatus | null>(null)
  const [thinkingLines, setThinkingLines] = useState<string[]>([])
  const [expandedThoughts, setExpandedThoughts] = useState<Set<number>>(new Set())
  const [openPanelIdx, setOpenPanelIdx] = useState<number | null>(null)
  const [panelCategories, setPanelCategories] = useState<string[]>([])
  const [panelComment, setPanelComment] = useState('')
  const [panelSubmitting, setPanelSubmitting] = useState(false)
  const [sessions, setSessions] = useState<ChatSessionSummary[]>([])
  const [journeys, setJourneys] = useState<JourneySummary[]>([])
  const [followups, setFollowups] = useState<string[]>([])
  const [activeJourneyId, setActiveJourneyId] = useState<number | null>(null)
  const [activeSessionId, setActiveSessionId] = useState<string | null>(
    routeSessionId ?? null,
  )
  const MAX_THINKING_LINES = 4

  const currentResponseRef = useRef('')
  const thinkingLinesRef = useRef<string[]>([])
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const wsRef = useRef<ChatWebSocket | null>(null)

  const refreshSessions = useCallback(async () => {
    try {
      const items = await listChatSessions()
      setSessions(items)
      return items
    } catch (error) {
      console.error('Failed to load chat sessions:', error)
      return [] as ChatSessionSummary[]
    }
  }, [])

  useEffect(() => {
    if (!user) {
      navigate('/login')
      return
    }
    void (async () => {
      const items = await refreshSessions()
      try {
        setJourneys(await listActiveJourneys())
      } catch (error) {
        console.error('Failed to load journeys:', error)
      }

      let target = routeSessionId
      if (!target) {
        if (items.length > 0) {
          target = items[0].client_uuid
        } else {
          const created = await createChatSession()
          target = created.client_uuid
          await refreshSessions()
        }
        navigate(`/chat/${target}`, { replace: true })
        return
      }
      setActiveSessionId(target)
      setSessionId(target)
    })()
  }, [user, routeSessionId, navigate, refreshSessions])

  useEffect(() => {
    if (!user || !activeSessionId || !settings) {
      return
    }
    setMessages([])
    setFollowups([])
    setActiveJourneyId(null)
    setCurrentResponse('')
    currentResponseRef.current = ''
    wsRef.current?.disconnect()
    connectWebSocket(settings, activeSessionId)
    return () => {
      wsRef.current?.disconnect()
    }
    // Intentionally reconnect when the selected session changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, activeSessionId, settings?.provider, settings?.model])

  useEffect(() => {
    if (!user) return
    void loadChatSettings()
  }, [user])

  useEffect(() => {
    if (!user) {
      return
    }

    let active = true

    const loadGraphRAGStatus = async () => {
      try {
        const token = localStorage.getItem('token')
        const response = await api.get('/drive/status', {
          headers: { Authorization: `Bearer ${token}` },
        })
        if (active) {
          const d = response.data
          setGraphragStatus({
            connected: d.connected,
            files_cached: d.sync?.file_count ?? 0,
            last_sync: d.sync?.last_sync ?? null,
            pipeline_running: d.pipeline?.running ?? false,
            pipeline_last_update: d.pipeline?.last_update ?? null,
            ready: d.connected && (d.sync?.file_count ?? 0) > 0,
          })
        }
      } catch (error) {
        console.error('Failed to load GraphRAG status:', error)
        if (active) {
          setGraphragStatus(null)
        }
      }
    }

    loadGraphRAGStatus()
    const timer = window.setInterval(loadGraphRAGStatus, 10000)

    return () => {
      active = false
      window.clearInterval(timer)
    }
  }, [user])

  useEffect(() => {
    scrollToBottom()
  }, [messages, currentResponse, followups])

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  const loadChatSettings = async () => {
    try {
      const response = await fetch('/api/settings/chat-config', {
        headers: {
          Authorization: `Bearer ${localStorage.getItem('token')}`,
        },
      })
      if (response.ok) {
        const data = await response.json()
        setSettings({
          provider: data.llm_provider || 'openai',
          model: data.llm_model || 'gpt-4o-mini',
          apiKey: '',
        })
      } else {
        setSettings({
          provider: 'openai',
          model: 'gpt-4o-mini',
          apiKey: '',
        })
      }
    } catch (error) {
      console.error('Failed to load settings:', error)
      setSettings({
        provider: 'openai',
        model: 'gpt-4o-mini',
        apiKey: '',
      })
    }
  }

  const connectWebSocket = (chatSettings: ChatSettings, sessionId: string) => {
    wsRef.current = new ChatWebSocket()
    wsRef.current.connect(chatSettings, sessionId)

    wsRef.current.onMessage((data) => {
      if (data.type === 'status') {
        console.log('System status:', data.message)
      } else if (data.type === 'history') {
        setMessages(
          (data.messages || []).map((m: any) => ({
            role: m.role,
            content: m.content,
            message_id: m.id ?? null,
          })),
        )
      } else if (data.type === 'start') {
        setIsStreaming(true)
        setFollowups([])
        setCurrentResponse('')
        currentResponseRef.current = ''
        thinkingLinesRef.current = []
        setThinkingLines([])
      } else if (data.type === 'think') {
        thinkingLinesRef.current = [...thinkingLinesRef.current, data.content]
        setThinkingLines((prev) => {
          const lines = [...prev, data.content]
          if (lines.length > MAX_THINKING_LINES) {
            return lines.slice(lines.length - MAX_THINKING_LINES)
          }
          return lines
        })
      } else if (data.type === 'chunk') {
        const newResponse = currentResponseRef.current + data.content
        currentResponseRef.current = newResponse
        setCurrentResponse(newResponse)
      } else if (data.type === 'end') {
        const finalResponse =
          typeof data.content === 'string' && data.content
            ? data.content
            : currentResponseRef.current
        const savedThoughts = thinkingLinesRef.current
        setMessages((prev) => [
          ...prev,
          {
            role: 'assistant',
            content: finalResponse,
            thoughts: savedThoughts,
            message_id: data.message_id ?? null,
          },
        ])
        if (Array.isArray(data.followups)) {
          setFollowups(data.followups.slice(0, 3))
        }
        void refreshSessions()
        setTimeout(() => {
          setCurrentResponse('')
          currentResponseRef.current = ''
          thinkingLinesRef.current = []
          setIsStreaming(false)
          setThinkingLines([])
        }, 0)
      } else if (data.type === 'error') {
        setMessages((prev) => [
          ...prev,
          { role: 'assistant', content: `Error: ${data.message}` },
        ])
        setIsStreaming(false)
        setCurrentResponse('')
        currentResponseRef.current = ''
        thinkingLinesRef.current = []
        setThinkingLines([])
      }
    })

    wsRef.current.onError((error) => {
      console.error('WebSocket error:', error)
    })

    wsRef.current.onConnection((connected) => {
      setIsConnected(connected)
    })
  }

  const handleSend = (override?: string) => {
    const text = (override ?? input).trim()
    if (!text || !settings) return

    setMessages((prev) => [...prev, { role: 'user', content: text }])
    setFollowups([])
    wsRef.current?.sendMessage(text, activeJourneyId)
    setInput('')
  }

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const handleNewChat = async () => {
    const created = await createChatSession()
    await refreshSessions()
    setSessionId(created.client_uuid)
    navigate(`/chat/${created.client_uuid}`)
  }

  const handleSelectSession = (uuid: string) => {
    setSessionId(uuid)
    navigate(`/chat/${uuid}`)
  }

  const handleRenameSession = async (uuid: string, title: string) => {
    await renameChatSession(uuid, title)
    await refreshSessions()
  }

  const handleDeleteSession = async (uuid: string) => {
    await deleteChatSession(uuid)
    const remaining = await refreshSessions()
    if (uuid === activeSessionId) {
      if (remaining.length > 0) {
        setSessionId(remaining[0].client_uuid)
        navigate(`/chat/${remaining[0].client_uuid}`)
      } else {
        clearSessionId()
        const created = await createChatSession()
        setSessionId(created.client_uuid)
        await refreshSessions()
        navigate(`/chat/${created.client_uuid}`)
      }
    }
  }

  const handleJourneySelect = (journey: JourneySummary) => {
    setActiveJourneyId(journey.id)
    setInput(journey.starter_prompt)
  }

  const handleFeedback = async (
    messageIndex: number,
    feedbackType: 'thumbs_up' | 'thumbs_down',
  ) => {
    const token = localStorage.getItem('token')
    if (!token) return

    const msg = messages[messageIndex]
    try {
      const payload: Record<string, any> = {
        feedback_type: feedbackType,
        rating: feedbackType === 'thumbs_up' ? 5 : 1,
      }
      if (msg?.message_id != null) {
        payload.chat_message_id = msg.message_id
      }
      const response = await api.post('/feedback', payload)
      const feedbackId: number | undefined = response.data?.id
      const caseId: string | undefined = response.data?.case_id

      setMessages((prev) =>
        prev.map((m, idx) =>
          idx === messageIndex
            ? { ...m, feedback: feedbackType, feedbackId, caseId }
            : m,
        ),
      )

      if (feedbackType === 'thumbs_down' && feedbackId) {
        setOpenPanelIdx(messageIndex)
        setPanelCategories([])
        setPanelComment('')
      }
    } catch (error) {
      console.error('Failed to submit feedback:', error)
    }
  }

  const togglePanelCategory = (slug: string) => {
    setPanelCategories((prev) =>
      prev.includes(slug) ? prev.filter((c) => c !== slug) : [...prev, slug],
    )
  }

  const closeFeedbackPanel = () => {
    setOpenPanelIdx(null)
    setPanelCategories([])
    setPanelComment('')
    setPanelSubmitting(false)
  }

  const submitFeedbackDetails = async (messageIndex: number) => {
    const msg = messages[messageIndex]
    if (!msg?.feedbackId) {
      closeFeedbackPanel()
      return
    }

    setPanelSubmitting(true)
    try {
      const payload: Record<string, any> = {}
      if (panelCategories.length > 0) payload.categories = panelCategories
      if (panelComment.trim()) payload.message = panelComment.trim()

      if (Object.keys(payload).length > 0) {
        await api.patch(`/feedback/${msg.feedbackId}`, payload)
      }
      setMessages((prev) =>
        prev.map((m, idx) =>
          idx === messageIndex ? { ...m, feedbackDetailed: true } : m,
        ),
      )
      closeFeedbackPanel()
    } catch (error) {
      console.error('Failed to submit feedback details:', error)
      setPanelSubmitting(false)
    }
  }

  const status = graphragStatus
  const isReady = Boolean(status?.ready)
  const isProcessing = Boolean(status?.pipeline_running)
  const statusLabel = !status
    ? 'Knowledge base status unavailable'
    : isReady
      ? 'Knowledge base ready'
      : isProcessing
        ? 'Indexing documents...'
        : status?.connected
          ? 'Knowledge base initializing'
          : 'Knowledge base not connected'

  if (!user) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin" />
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-background flex">
      <ChatSessionSidebar
        sessions={sessions}
        activeUuid={activeSessionId}
        onSelect={handleSelectSession}
        onNew={() => void handleNewChat()}
        onRename={(uuid, title) => void handleRenameSession(uuid, title)}
        onDelete={(uuid) => void handleDeleteSession(uuid)}
      />

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="border-b border-border bg-card px-4 py-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-semibold">AI Chat</h1>
              <span className="text-sm text-muted-foreground ml-2">
                ({user.email})
              </span>
            </div>
            <div className="flex items-center gap-2">
              {isAdmin && (
                <Link to="/admin/settings">
                  <button className="p-2 hover:bg-muted rounded-lg transition-colors">
                    <Settings className="w-5 h-5" />
                  </button>
                </Link>
              )}
              {features.tester_correspondence_enabled && (
                <Link to="/feedback">
                  <button
                    className="p-2 hover:bg-muted rounded-lg transition-colors"
                    title="Feedback cases"
                  >
                    <ThumbsDown className="w-5 h-5" />
                  </button>
                </Link>
              )}
              {isAdmin && (
                <Link to="/admin/dashboard">
                  <button
                    className="p-2 hover:bg-muted rounded-lg transition-colors"
                    title="Admin dashboard"
                  >
                    <MessageSquare className="w-5 h-5" />
                  </button>
                </Link>
              )}
              <button
                onClick={handleLogout}
                className="p-2 hover:bg-muted rounded-lg transition-colors"
              >
                <LogOut className="w-5 h-5" />
              </button>
            </div>
          </div>
        </header>

        {status && (
          <div className="border-b border-slate-200 bg-slate-50">
            <div className="mx-auto max-w-4xl px-4 py-3">
              <div
                className={`rounded-2xl border px-4 py-3 shadow-sm ${
                  isReady
                    ? 'border-emerald-200 bg-emerald-50 text-emerald-900'
                    : isProcessing
                      ? 'border-amber-200 bg-amber-50 text-amber-900'
                      : 'border-slate-200 bg-white text-slate-900'
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2 text-sm font-semibold">
                      {isReady ? (
                        <CircleCheck className="h-4 w-4 text-emerald-600" />
                      ) : isProcessing ? (
                        <Loader2 className="h-4 w-4 animate-spin text-amber-600" />
                      ) : status?.connected ? (
                        <AlertTriangle className="h-4 w-4 text-amber-500" />
                      ) : (
                        <AlertTriangle className="h-4 w-4 text-slate-500" />
                      )}
                      <span>{statusLabel}</span>
                    </div>
                    <div className="mt-1 text-xs text-slate-600">
                      {isReady
                        ? 'Answers are grounded in your Google Drive documents.'
                        : isProcessing
                          ? 'Documents are being indexed into the knowledge graph.'
                          : status?.connected
                            ? 'Documents synced, waiting for indexing.'
                            : 'Connect Google Drive in admin settings to enable grounded answers.'}
                    </div>
                  </div>
                  <Badge
                    className={
                      isReady
                        ? 'border-emerald-200 bg-white text-emerald-800'
                        : isProcessing
                          ? 'border-amber-200 bg-white text-amber-800'
                          : 'border-slate-200 bg-white text-slate-700'
                    }
                  >
                    {isReady
                      ? 'Ready'
                      : isProcessing
                        ? 'Indexing'
                        : status?.connected
                          ? 'No files'
                          : 'Offline'}
                  </Badge>
                </div>
              </div>
            </div>
          </div>
        )}

        <main className="flex-1 max-w-4xl mx-auto w-full p-4">
          <div className="h-[calc(100vh-180px)] flex flex-col">
            <div className="flex-1 overflow-y-auto space-y-4 pb-4">
              {messages.length === 0 && !isStreaming && (
                <JourneyStarterGrid
                  journeys={journeys}
                  onSelect={handleJourneySelect}
                  disabled={!isConnected || isStreaming}
                />
              )}

              {messages.map((msg, idx) => (
                <div
                  key={idx}
                  className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                >
                  <div
                    className={`max-w-[80%] rounded-lg p-4 ${
                      msg.role === 'user'
                        ? 'bg-primary text-primary-foreground'
                        : 'bg-muted'
                    }`}
                  >
                    {msg.role === 'assistant' &&
                      msg.thoughts &&
                      msg.thoughts.length > 0 && (
                        <div className="mb-2">
                          <button
                            onClick={() => {
                              setExpandedThoughts((prev) => {
                                const next = new Set(prev)
                                if (next.has(idx)) next.delete(idx)
                                else next.add(idx)
                                return next
                              })
                            }}
                            className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-600 transition-colors"
                          >
                            {expandedThoughts.has(idx) ? (
                              <ChevronDown className="w-3 h-3" />
                            ) : (
                              <ChevronRight className="w-3 h-3" />
                            )}
                            <Brain className="w-3 h-3" />
                            {expandedThoughts.has(idx)
                              ? 'Hide thoughts'
                              : `${msg.thoughts.length} thoughts`}
                          </button>
                          {expandedThoughts.has(idx) && (
                            <div className="mt-1 pl-4 space-y-0.5 border-l-2 border-border/30">
                              {msg.thoughts.map((line, i) => (
                                <div
                                  key={i}
                                  className="text-xs text-gray-400 whitespace-pre-wrap font-mono leading-relaxed"
                                >
                                  {line}
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}

                    <Markdown
                      className={`prose prose-sm max-w-none ${
                        msg.role === 'user'
                          ? 'prose-invert'
                          : 'dark:prose-invert'
                      }`}
                    >
                      {msg.content}
                    </Markdown>

                    {msg.role === 'assistant' && (
                      <>
                        <div className="flex items-center gap-2 mt-3 pt-2 border-t border-border/50">
                          {msg.feedback ? (
                            <span className="text-xs text-muted-foreground">
                              {msg.feedback === 'thumbs_up'
                                ? '👍 Thanks!'
                                : msg.feedbackDetailed
                                  ? '👎 Thanks for the details'
                                  : '👎 Sorry about that'}
                            </span>
                          ) : (
                            <>
                              <button
                                onClick={() => handleFeedback(idx, 'thumbs_up')}
                                className="p-1 hover:bg-secondary rounded transition-colors"
                                title="Helpful"
                              >
                                <ThumbsUp className="w-4 h-4 text-muted-foreground" />
                              </button>
                              <button
                                onClick={() => handleFeedback(idx, 'thumbs_down')}
                                className="p-1 hover:bg-secondary rounded transition-colors"
                                title="Not helpful"
                              >
                                <ThumbsDown className="w-4 h-4 text-muted-foreground" />
                              </button>
                            </>
                          )}
                        </div>
                        {msg.caseId && (
                          <Link
                            to={`/feedback/${msg.caseId}`}
                            className="mt-2 inline-block text-xs text-primary hover:underline"
                          >
                            View feedback case
                          </Link>
                        )}
                        {openPanelIdx === idx && (
                          <div className="mt-2 p-3 rounded-lg border border-border bg-background/60 space-y-2">
                            <p className="text-xs font-medium text-muted-foreground">
                              What went wrong? (optional)
                            </p>
                            <div className="flex flex-wrap gap-1.5">
                              {FEEDBACK_CATEGORIES.map((cat) => (
                                <button
                                  key={cat.slug}
                                  onClick={() => togglePanelCategory(cat.slug)}
                                  className={`px-2.5 py-1 rounded-full text-xs border transition-colors ${
                                    panelCategories.includes(cat.slug)
                                      ? 'bg-primary text-primary-foreground border-primary'
                                      : 'bg-background text-muted-foreground border-border hover:bg-secondary'
                                  }`}
                                >
                                  {cat.label}
                                </button>
                              ))}
                            </div>
                            <Textarea
                              value={panelComment}
                              onChange={(e) => setPanelComment(e.target.value)}
                              placeholder="Tell us more (optional)..."
                              maxLength={2000}
                              className="min-h-[60px] text-xs"
                            />
                            <div className="flex items-center gap-2">
                              <button
                                onClick={() => submitFeedbackDetails(idx)}
                                disabled={panelSubmitting}
                                className="px-3 py-1.5 text-xs rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                              >
                                {panelSubmitting ? 'Submitting...' : 'Submit'}
                              </button>
                              <button
                                onClick={closeFeedbackPanel}
                                disabled={panelSubmitting}
                                className="px-3 py-1.5 text-xs rounded-lg text-muted-foreground hover:bg-secondary disabled:opacity-50"
                              >
                                Skip
                              </button>
                            </div>
                          </div>
                        )}
                      </>
                    )}
                  </div>
                </div>
              ))}

              {isStreaming && (thinkingLines.length > 0 || currentResponse) && (
                <div className="flex justify-start">
                  <div className="max-w-[80%] rounded-lg bg-muted">
                    {thinkingLines.length > 0 && (
                      <div className="px-4 pt-3 pb-1 space-y-0.5 border-b border-border/30">
                        {thinkingLines.map((line, i) => (
                          <div
                            key={i}
                            className="text-xs text-gray-400 whitespace-pre-wrap font-mono leading-relaxed"
                          >
                            {line}
                          </div>
                        ))}
                      </div>
                    )}
                    {currentResponse && (
                      <Markdown className="px-4 py-3 prose prose-sm max-w-none dark:prose-invert">
                        {currentResponse}
                      </Markdown>
                    )}
                    {!currentResponse && thinkingLines.length > 0 && (
                      <div className="px-4 pb-3">
                        <Loader2 className="w-4 h-4 animate-spin text-gray-400" />
                      </div>
                    )}
                  </div>
                </div>
              )}

              {!isStreaming && followups.length > 0 && (
                <div className="flex flex-wrap gap-2 pt-1">
                  {followups.map((q) => (
                    <button
                      key={q}
                      type="button"
                      onClick={() => setInput(q)}
                      className="rounded-full border border-border bg-card px-3 py-1.5 text-left text-xs text-foreground hover:border-primary/50 hover:bg-muted/50"
                    >
                      {q}
                    </button>
                  ))}
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>

            <div className="border-t border-border pt-4">
              <div className="flex gap-2">
                <input
                  type="text"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyPress={handleKeyPress}
                  placeholder="Type your message..."
                  disabled={isStreaming || !isConnected}
                  className="flex-1 p-3 border border-border rounded-lg bg-background disabled:opacity-50"
                />
                <button
                  onClick={() => handleSend()}
                  disabled={!input.trim() || isStreaming || !isConnected}
                  className="p-3 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50"
                >
                  <Send className="w-5 h-5" />
                </button>
              </div>
              {!isConnected && (
                <p className="text-sm text-muted-foreground mt-2">
                  {isStreaming
                    ? 'Connecting...'
                    : 'Disconnected. Please refresh to reconnect.'}
                </p>
              )}
            </div>
          </div>
        </main>
      </div>
    </div>
  )
}
