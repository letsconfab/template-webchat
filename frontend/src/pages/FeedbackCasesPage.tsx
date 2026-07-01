import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, Loader2, MessageSquareWarning } from 'lucide-react'

import { Badge } from '../components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card'
import { api } from '../services/api'

interface CaseSummary {
  case_id: string
  status: 'awaiting_admin' | 'awaiting_user' | 'resolved'
  categories: string[]
  comment: string | null
  created_at: string
  updated_at: string
}

interface CaseDetail extends CaseSummary {
  rated_exchange: {
    user: { id: number; content: string; created_at: string } | null
    assistant: { id: number; content: string; created_at: string }
  }
  replies: Array<{
    id: number
    author_role: 'user' | 'admin'
    text: string
    created_at: string
  }>
}

const statusLabel = (status: CaseSummary['status']) => ({
  awaiting_admin: 'Awaiting admin',
  awaiting_user: 'Awaiting you',
  resolved: 'Resolved',
}[status])

export default function FeedbackCasesPage() {
  const { caseId } = useParams()
  const [cases, setCases] = useState<CaseSummary[]>([])
  const [detail, setDetail] = useState<CaseDetail | null>(null)
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [reply, setReply] = useState('')

  useEffect(() => {
    setLoading(true)
    if (caseId) {
      api.get(`/feedback-cases/${caseId}`)
        .then(response => setDetail(response.data))
        .finally(() => setLoading(false))
    } else {
      api.get('/feedback-cases')
        .then(response => {
          setCases(response.data.cases || [])
          setNextCursor(response.data.next_cursor || null)
        })
        .finally(() => setLoading(false))
    }
  }, [caseId])

  const loadMore = async () => {
    if (!nextCursor) return
    const response = await api.get('/feedback-cases', {
      params: { cursor: nextCursor },
    })
    setCases(previous => [...previous, ...(response.data.cases || [])])
    setNextCursor(response.data.next_cursor || null)
  }

  const submitReply = async () => {
    if (!caseId || !reply.trim()) return
    await api.post(`/feedback-cases/${caseId}/replies`, { text: reply })
    const response = await api.get(`/feedback-cases/${caseId}`)
    setDetail(response.data)
    setReply('')
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin" />
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b bg-card">
        <div className="mx-auto flex max-w-4xl items-center justify-between px-4 py-4">
          <div className="flex items-center gap-2">
            <MessageSquareWarning className="h-5 w-5" />
            <h1 className="text-xl font-semibold">Feedback cases</h1>
          </div>
          <Link to="/chat" className="text-sm text-primary hover:underline">
            Back to chat
          </Link>
        </div>
      </header>

      <main className="mx-auto max-w-4xl space-y-4 px-4 py-8">
        {caseId && detail ? (
          <>
            <Link to="/feedback" className="inline-flex items-center gap-1 text-sm text-primary hover:underline">
              <ArrowLeft className="h-4 w-4" />
              All cases
            </Link>
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between gap-4">
                  <CardTitle>Case {detail.case_id.slice(0, 8)}</CardTitle>
                  <Badge>{statusLabel(detail.status)}</Badge>
                </div>
              </CardHeader>
              <CardContent className="space-y-5">
                <div className="flex flex-wrap gap-2">
                  {detail.categories.map(category => (
                    <Badge key={category} variant="secondary">{category.replace('_', ' ')}</Badge>
                  ))}
                </div>
                {detail.comment && (
                  <section>
                    <h2 className="mb-1 text-sm font-semibold">Your comment</h2>
                    <p className="whitespace-pre-wrap text-sm">{detail.comment}</p>
                  </section>
                )}
                <section className="space-y-3">
                  <h2 className="text-sm font-semibold">Rated exchange</h2>
                  {detail.rated_exchange.user && (
                    <div className="rounded-lg bg-primary p-3 text-sm text-primary-foreground">
                      <p className="mb-1 text-xs font-semibold">You</p>
                      <p className="whitespace-pre-wrap">{detail.rated_exchange.user.content}</p>
                    </div>
                  )}
                  <div className="rounded-lg bg-muted p-3 text-sm">
                    <p className="mb-1 text-xs font-semibold">Assistant</p>
                    <p className="whitespace-pre-wrap">{detail.rated_exchange.assistant.content}</p>
                  </div>
                </section>
                <section className="space-y-3">
                  <h2 className="text-sm font-semibold">Correspondence</h2>
                  {detail.replies.map(caseReply => (
                    <div key={caseReply.id} className="rounded-lg border p-3 text-sm">
                      <p className="mb-1 text-xs font-semibold">
                        {caseReply.author_role === 'admin' ? 'Admin' : 'You'}
                      </p>
                      <p className="whitespace-pre-wrap">{caseReply.text}</p>
                    </div>
                  ))}
                  <textarea
                    value={reply}
                    onChange={event => setReply(event.target.value)}
                    maxLength={4000}
                    placeholder="Add a reply"
                    className="min-h-24 w-full rounded-md border bg-background p-3 text-sm"
                  />
                  <button
                    onClick={submitReply}
                    disabled={!reply.trim()}
                    className="rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground disabled:opacity-50"
                  >
                    Send reply
                  </button>
                </section>
              </CardContent>
            </Card>
          </>
        ) : (
          <>
            {cases.length === 0 ? (
              <Card>
                <CardContent className="py-10 text-center text-muted-foreground">
                  You have not opened any feedback cases.
                </CardContent>
              </Card>
            ) : cases.map(feedbackCase => (
              <Link key={feedbackCase.case_id} to={`/feedback/${feedbackCase.case_id}`}>
                <Card className="mb-3 transition-colors hover:bg-muted/50">
                  <CardContent className="flex items-start justify-between gap-4 p-5">
                    <div>
                      <p className="font-medium">
                        {feedbackCase.comment || 'Reported assistant answer'}
                      </p>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {new Date(feedbackCase.created_at).toLocaleString()}
                      </p>
                    </div>
                    <Badge>{statusLabel(feedbackCase.status)}</Badge>
                  </CardContent>
                </Card>
              </Link>
            ))}
            {nextCursor && (
              <button
                onClick={loadMore}
                className="rounded-md border px-4 py-2 text-sm hover:bg-muted"
              >
                Load more
              </button>
            )}
          </>
        )}
      </main>
    </div>
  )
}
